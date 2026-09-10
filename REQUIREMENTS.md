# JP Price Checker requirements

## Catalogue scope

- Cover current Standard-era Japanese prints, including D and DZ promo cards.
- Catalogue only two item types: playable cards and Energy cards.
- Keep each physical printing distinct by its printed set code and collector
  number, even when the Japanese and English releases use different codes.
- Store the official Japanese name, an English search name when known, mapping
  provenance, and any retailer-specific catalogue location needed to retrieve
  that print accurately.

## Search requirements

- English name search must support partial names and reasonable spelling
  variation.
- Japanese name search must work where a Japanese name is known.
- Exact serial-number search is required for every print, especially promos.
  It must accept conventional forms such as `D-PR/1247`, `DPR1247`, and
  `D-PR 1247`.
- Serial search is Japanese-print-only. It resolves the Japanese serial used
  by the stores and returns only that Japanese listing.
- English serials are internal cross-print evidence used to record an English
  search name against the Japanese print. They are not a user-facing search
  mode, a selectable result, or a displayed serial.
- Serial-number search is store-independent: it selects the canonical print
  before querying Yuyu-Tei, Card Rush, VanHappy, BigWeb, or any later store.
  A serial must never be tied to only the retailer that supplied its catalogue
  entry.
- A bare collector number is only accepted after the user narrows the set
  family, because the same number can occur in more than one product.

## Promo and cross-print mapping

- A card may be a Japanese promo but an English set inclusion, box topper, or
  other reprint. Different print codes do not mean different cards.
- Cross-print links require an explicit, reviewable source—for example, the
  print references declared on the trusted Fandom card page. The app must not
  guess from translated names or neighbouring collector numbers.
- When an English mapping is unavailable, translation happens once during a
  catalogue import or review step. The approved English search name is stored
  locally with its provenance and is never translated while a user waits.

## Store comparison

- Every store connector receives the selected canonical print and verifies an
  exact printed reference in its result before reporting a price.
- Preserve displayed price, availability, stock count when listed, condition,
  and the retailer product link.
- Retailer catalogue pages can seed Japanese names and serials, but are not the
  canonical identity source for a print.

## Implementation plan and outstanding work

| Stage | Status | Outcome |
| --- | --- | --- |
| Core catalogue and comparison | Complete | English fuzzy search, Japanese-print selection, local browser and Telegram interfaces, and exact-print comparisons from Yuyu-Tei, BigWeb, Card Rush, and VanHappy. |
| Cross-print links | Complete | A Fandom card page can link an English reprint to a Japanese printing with a different serial; `DZ-BT12/Re07EN` → `D-PR/1247` is the verified example. |
| Promo catalogue ingestion | Planned | Crawl Yuyu-Tei D Promo catalogue pages, including their serial ranges and product locations, into a resumable local import. |
| Promo identity enrichment | Planned | Match imported promo prints to official Japanese data, explicit Fandom cross-print links, and an editable review queue for unresolved names. |
| One-time translation review | Planned | Translate only unresolved playable or Energy names during import; persist the approved English search name and provenance locally. No user search may trigger a translation. |
| Serial-number search | Planned | Add Japanese-print serial normalisation, exact reference lookup, ambiguity handling for bare numbers, and Japanese serial result labels. English serials remain internal mapping data only. |
| Multi-store promo lookup | Planned | Pass the selected canonical serial to every connector, use each store's catalogue location when needed, and verify the exact reference before showing an offer. |
| Hosting | Deferred | Keep the Telegram bot and browser interface local-first until hosting is explicitly requested. |
| Dorasuta | Deferred | Do not add the Dorasuta connector at this time. |

### Planned promo implementation sequence

1. Add a `promo_catalogue_entries` import store keyed by Japanese serial. Save
   the Yuyu-Tei catalogue page and listing URL separately from the canonical
   card identity so another retailer can use the same print.
2. Add an import command for a specified promo range, starting with pages such
   as `dpromo-1200`. It must resume safely, retain Energy and playable items,
   and produce an unresolved-name report rather than discarding entries.
3. Enrich each promo with official Japanese data and explicit cross-print
   evidence. Send only still-unresolved names to the one-time translation
   review queue.
4. Add Japanese serial normalisation and exact lookup to the catalogue search
   API, the Telegram handler, and the browser UI. Formatted serials resolve
   directly; ambiguous bare numbers prompt for a set family. English serials
   are used only by the import/mapping layer and never appear in user results.
5. Add connector metadata for retailer-specific promo locations. Yuyu-Tei may
   require a page such as `dpromo-1200`; Card Rush, VanHappy, BigWeb, and later
   stores still receive the same canonical `D-PR/1247` reference.
6. Backfill promo ranges incrementally, verify exact-print offers and stock
   indicators against live listings, then mark each range complete in the
   import checkpoint.

### Explicit non-goals for this work

- No accessory catalogue or accessory search.
- No per-search translation.
- No loose retailer-name matching in place of an exact serial match.
- No hosting work unless separately requested.
