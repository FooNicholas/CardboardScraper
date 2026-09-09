"""Small local web interface sharing the Telegram bot's catalogue and stores."""

from __future__ import annotations

import argparse
import asyncio
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.config import Settings
from scraperbot.connectors.bigweb import BigWebConnector
from scraperbot.connectors.yuyutei import YuyuTeiConnector
from scraperbot.models import CardPrint, ComparisonResult, StoreOffer
from scraperbot.query import parse_name_query
from scraperbot.services.comparison import ComparisonService


MAX_QUERY_LENGTH = 120
MAX_CHOICES = 12


class LocalPriceCheckWeb:
    """Application-facing operations used by the local HTTP handler."""

    def __init__(self, catalogue: CatalogueRepository, comparison: ComparisonService) -> None:
        self.catalogue = catalogue
        self.comparison = comparison

    def search(self, raw_query: str) -> dict[str, Any]:
        query, rarity = parse_name_query(raw_query[:MAX_QUERY_LENGTH])
        if not query:
            raise ValueError("Enter a card name to search.")
        cards = self.catalogue.search(query, rarity=rarity, limit=MAX_CHOICES, japanese_only=True)
        return {
            "query": query,
            "rarity": rarity,
            "cards": [self._card_payload(card) for card in cards],
        }

    async def compare(self, print_id: int, *, refresh: bool = False) -> dict[str, Any]:
        card = self.catalogue.get(print_id, japanese_only=True)
        if not card:
            raise LookupError("That Japanese-market card print is no longer available for comparison.")
        result = await self.comparison.compare(card, refresh=refresh)
        return self._comparison_payload(result)

    @staticmethod
    def _card_payload(card: CardPrint) -> dict[str, Any]:
        return {
            "id": card.id,
            "english_name": card.english_name,
            "japanese_name": card.japanese_name,
            "set_code": card.set_code,
            "collector_number": card.collector_number,
            "rarity": card.rarity,
            "display_code": card.display_code,
            "source": card.source,
        }

    @classmethod
    def _comparison_payload(cls, result: ComparisonResult) -> dict[str, Any]:
        return {
            "card": cls._card_payload(result.card),
            "offers": [cls._offer_payload(offer) for offer in result.offers],
            "no_active_listing_stores": list(result.no_active_listing_stores),
            "unavailable_stores": list(result.unavailable_stores),
            "failed_stores": list(result.failed_stores),
        }

    @staticmethod
    def _offer_payload(offer: StoreOffer) -> dict[str, Any]:
        listing_url = offer.listing_url
        if listing_url and not listing_url.startswith(("https://", "http://")):
            listing_url = None
        return {
            "store_id": offer.store_id,
            "store_name": offer.store_name,
            "raw_name": offer.raw_name,
            "price_yen": offer.price_yen,
            "price_display": offer.price_display,
            "availability": offer.availability.value,
            "listing_url": listing_url,
            "match_confidence": offer.match_confidence.value,
            "condition": offer.condition,
        }


class LocalWebRequestHandler(BaseHTTPRequestHandler):
    """Same-origin, GET-only handler for a localhost UI."""

    application: LocalPriceCheckWeb

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        request = urlsplit(self.path)
        if request.path == "/":
            self._send_html(INDEX_HTML)
            return
        if request.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        parameters = parse_qs(request.query, keep_blank_values=True)
        if request.path == "/api/search":
            try:
                self._send_json(HTTPStatus.OK, self.application.search(parameters.get("q", [""])[0]))
            except ValueError as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        if request.path == "/api/compare":
            try:
                print_id = int(parameters.get("id", [""])[0])
                refresh = parameters.get("refresh", ["0"])[0] == "1"
                payload = asyncio.run(self.application.compare(print_id, refresh=refresh))
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "A valid card selection is required."})
            except LookupError as error:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
            except Exception:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"error": "Store comparison is temporarily unavailable. Please try again."},
                )
            else:
                self._send_json(HTTPStatus.OK, payload)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Only read-only requests are supported."})

    def log_message(self, _: str, *args: object) -> None:
        """Keep ordinary browser requests out of the terminal."""

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self._send_common_headers("text/html; charset=utf-8", len(encoded))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._send_common_headers("application/json; charset=utf-8", len(encoded))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_common_headers(self, content_type: str, content_length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )


def build_web_application(settings: Settings | None = None) -> LocalPriceCheckWeb:
    """Create the shared catalogue/store services without requiring Telegram."""
    settings = settings or Settings.from_environment()
    return LocalPriceCheckWeb(
        CatalogueRepository(settings.catalogue_db),
        ComparisonService((YuyuTeiConnector(), BigWebConnector())),
    )


def serve(application: LocalPriceCheckWeb, *, host: str = "127.0.0.1", port: int = 8787) -> None:
    """Serve the UI locally. The default address is inaccessible from a network."""
    handler = type("BoundLocalWebRequestHandler", (LocalWebRequestHandler,), {"application": application})
    server = HTTPServer((host, port), handler)
    print(f"PriceCheck is running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPriceCheck stopped.")
    finally:
        server.server_close()
        application.catalogue.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local PriceCheck browser interface.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: local computer only)")
    parser.add_argument("--port", type=int, default=8787, help="Local port (default: 8787)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    serve(build_web_application(), host=args.host, port=args.port)


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PriceCheck</title>
  <style>
    :root { color-scheme: dark; --ink:#f7f7fb; --muted:#a8acc0; --panel:#171927; --line:#2b2e42; --accent:#ad8cff; --accent-2:#66e3c4; --danger:#ff9b9b; }
    * { box-sizing:border-box } body { margin:0; min-height:100vh; background:radial-gradient(circle at 12% 0%, #30225a, transparent 37rem), #0d0e17; color:var(--ink); font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    main { width:min(1180px, calc(100% - 32px)); margin:0 auto; padding:64px 0 80px; } h1 { margin:0; font-size:clamp(2.2rem,7vw,4.4rem); letter-spacing:-.06em; } .eyebrow { color:var(--accent-2); font-weight:700; letter-spacing:.12em; font-size:.76rem; text-transform:uppercase; margin-bottom:10px; } .intro { max-width:610px; color:var(--muted); margin:14px 0 32px; } .workspace { display:grid; grid-template-columns:minmax(290px,.8fr) minmax(0,1.4fr); gap:32px; align-items:start; margin-top:16px; } .print-panel,.price-panel { min-width:0; } .price-panel { position:sticky; top:26px; min-height:180px; } .panel-label { color:var(--muted); font-size:.78rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase; margin:0 0 10px; }
    form { display:flex; gap:10px; background:var(--panel); border:1px solid var(--line); padding:10px; border-radius:16px; box-shadow:0 18px 60px #0005; } input { min-width:0; flex:1; border:0; border-radius:10px; color:var(--ink); background:#0e101a; padding:14px 16px; font:inherit; outline:none; } input:focus { box-shadow:0 0 0 2px var(--accent); } button { border:0; border-radius:10px; padding:12px 18px; color:#150d2c; background:var(--accent); font:700 15px inherit; cursor:pointer; } button:hover { filter:brightness(1.1) } button:disabled { cursor:wait; opacity:.6; }
    .hint { color:var(--muted); font-size:.88rem; margin:12px 0 18px; } .hint button { color:var(--muted); background:transparent; border:1px solid var(--line); padding:4px 9px; margin-left:5px; font-size:.8rem; }
    #status { min-height:1.5em; color:var(--muted); margin-bottom:12px; } #status.error { color:var(--danger) } .result-list { display:grid; gap:10px; } .card { width:100%; text-align:left; color:var(--ink); background:var(--panel); border:1px solid var(--line); padding:17px; border-radius:14px; display:flex; gap:16px; align-items:center; } .card:hover { border-color:var(--accent); } .card.active { border-color:var(--accent-2); background:linear-gradient(115deg,#20273b,#1a1b2d); box-shadow:0 0 0 1px #66e3c440; } .card.active .code { color:var(--accent-2); } .card h2 { font-size:1.05rem; margin:0 0 4px; } .card p { margin:0; color:var(--muted); font-size:.9rem; } .card .code { margin-left:auto; text-align:right; color:var(--accent-2); font-size:.84rem; white-space:nowrap; }
    #comparison { margin-top:28px; } .comparison-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; border-bottom:1px solid var(--line); padding-bottom:13px; margin-bottom:12px; } .comparison-head h2 { margin:0; font-size:1.35rem; } .comparison-head p { margin:3px 0 0; color:var(--muted); } .comparison-head button { background:transparent; color:var(--muted); border:1px solid var(--line); padding:7px 10px; font-size:.8rem; }
    .offer { display:grid; grid-template-columns:minmax(110px,1fr) auto auto; gap:14px; align-items:center; padding:14px 0; border-bottom:1px solid var(--line); } .offer a { color:var(--ink); font-weight:700; text-decoration:none; } .offer a:hover { color:var(--accent-2) } .offer small { display:block; color:var(--muted); } .price { font-weight:800; color:var(--accent-2); } .sold { color:var(--muted); } .tag { color:var(--muted); font-size:.75rem; text-align:right; } .notice { color:var(--muted); font-size:.9rem; margin:12px 0; }
    @media (max-width:780px) { main { padding-top:42px } .workspace { grid-template-columns:1fr; gap:24px; } .price-panel { position:static; } form { padding:7px } button { padding:11px 13px } .card { align-items:flex-start } .card .code { white-space:normal } .offer { grid-template-columns:1fr auto; } .tag { grid-column:1 / -1; text-align:left; } }
  </style>
</head>
<body><main>
  <div class="eyebrow">Local card price comparison</div><h1>PriceCheck</h1>
  <p class="intro">Search by English card name—even partially spelled—and choose the exact Japanese-market printing before checking stores.</p>
  <form id="search-form"><input id="query" type="search" maxlength="120" autocomplete="off" placeholder="Try: Youthberk, Haughty Peerage FFR" autofocus><button id="search-button">Search</button></form>
  <div class="hint">Optional rarity at the end: <button type="button" data-query="Youthberk FFR">Youthberk FFR</button><button type="button" data-query="Chronojet">Chronojet</button></div>
  <div id="status" aria-live="polite"></div><div class="workspace"><section class="print-panel"><p class="panel-label">Matching printings</p><section id="results" class="result-list"></section></section><section class="price-panel"><p class="panel-label">Price comparison</p><section id="comparison"></section></section></div>
</main><script>
const query = document.querySelector('#query'), form = document.querySelector('#search-form'), searchButton = document.querySelector('#search-button'), status = document.querySelector('#status'), results = document.querySelector('#results'), comparison = document.querySelector('#comparison');
let selectedId = null;
function setStatus(message, isError=false) { status.textContent = message; status.className = isError ? 'error' : ''; }
function clear(node) { node.replaceChildren(); }
function text(tag, value, className) { const node=document.createElement(tag); node.textContent=value || ''; if (className) node.className=className; return node; }
async function readJson(response) { const data=await response.json(); if (!response.ok) throw new Error(data.error || 'Something went wrong.'); return data; }
async function search(raw) { const value=(raw || query.value).trim(); if (!value) { setStatus('Enter a card name to search.', true); return; } query.value=value; clear(results); clear(comparison); selectedId=null; setStatus('Finding matching prints…'); searchButton.disabled=true; try { const data=await readJson(await fetch('/api/search?q='+encodeURIComponent(value))); if (!data.cards.length) { setStatus('No Japanese-market print matched that name. Try a shorter spelling.'); return; } setStatus(data.cards.length+' matching print'+(data.cards.length===1?'':'s')+' — choose one to compare stores.'); for (const card of data.cards) { const button=document.createElement('button'); button.type='button'; button.className='card'; button.dataset.printId=card.id; const copy=document.createElement('div'); copy.append(text('h2',card.english_name), text('p',card.japanese_name)); button.append(copy,text('div',card.display_code,'code')); button.addEventListener('click',()=>compare(card.id)); results.append(button); } } catch (error) { setStatus(error.message,true); } finally { searchButton.disabled=false; } }
function safeLink(url) { try { const parsed=new URL(url); return ['https:','http:'].includes(parsed.protocol) ? parsed.href : null; } catch { return null; } }
function highlightSelection() { document.querySelectorAll('.card[data-print-id]').forEach(card=>card.classList.toggle('active',Number(card.dataset.printId)===selectedId)); }
function renderComparison(data) { highlightSelection(); clear(comparison); const head=document.createElement('div'); head.className='comparison-head'; const copy=document.createElement('div'); copy.append(text('h2',data.card.english_name),text('p',(data.card.japanese_name ? data.card.japanese_name+' · ' : '')+data.card.display_code)); const refresh=document.createElement('button'); refresh.textContent='Refresh prices'; refresh.addEventListener('click',()=>compare(data.card.id,true)); head.append(copy,refresh); comparison.append(head); if (!data.offers.length) comparison.append(text('p','No active store listing is available for this exact print right now.','notice')); for (const offer of data.offers) { const row=document.createElement('div'); row.className='offer'; const store=document.createElement(offer.listing_url ? 'a' : 'div'); store.textContent=offer.store_name; if (offer.listing_url) { const href=safeLink(offer.listing_url); if (href) { store.href=href; store.target='_blank'; store.rel='noopener noreferrer'; } } const detail=text('small',offer.raw_name); const storeWrap=document.createElement('div'); storeWrap.append(store,detail); const state=offer.availability==='sold_out' ? 'sold out' : offer.availability.replaceAll('_',' '); row.append(storeWrap,text('div',offer.price_display,offer.availability==='in_stock'?'price':'sold'),text('div',state+' · '+offer.match_confidence.replaceAll('_',' '),'tag')); comparison.append(row); } const notices=[]; if (data.no_active_listing_stores.length) notices.push('No active listing (sold out or not stocked): '+data.no_active_listing_stores.join(', ')); if (data.unavailable_stores.length) notices.push('Set not listed: '+data.unavailable_stores.join(', ')); if (data.failed_stores.length) notices.push('Could not check: '+data.failed_stores.join(', ')); if (notices.length) comparison.append(text('p',notices.join(' · '),'notice')); }
async function compare(id, refresh=false) { selectedId=id; highlightSelection(); setStatus('Checking stores…'); comparison.replaceChildren(text('p','Comparing exact-print listings…','notice')); try { const data=await readJson(await fetch('/api/compare?id='+encodeURIComponent(id)+(refresh?'&refresh=1':''))); renderComparison(data); setStatus(''); } catch (error) { clear(comparison); setStatus(error.message,true); } }
form.addEventListener('submit',event=>{ event.preventDefault(); search(); }); document.querySelectorAll('[data-query]').forEach(button=>button.addEventListener('click',()=>search(button.dataset.query)));
</script></body></html>"""
