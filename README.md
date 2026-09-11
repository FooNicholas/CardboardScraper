# JP Price Checker

A local-first Cardfight!! Vanguard price-comparison Telegram bot. Users search
by English card name (including partial names and reasonable typos), choose a
matching print, and receive offers from the enabled Japanese stores.

The current and planned product requirements are recorded in
[REQUIREMENTS.md](REQUIREMENTS.md), including promo serial-number search across
all store connectors.

It does not translate while a user waits. The English card mapping lives in a
local SQLite database and store connectors use the selected print identifier
only after the user has chosen it.

## What is implemented

- Local FTS and fuzzy English-name search, including aliases and optional
  trailing rarity: `/price Youthberk FFR`.
- Explicitly labelled print finishes are kept separate from rarity. For
  example, a Yuyu-Tei D-PR title ending in `H仕様` is recorded against that
  exact Japanese serial as a holo finish, while preserving the original label
  for display and exact-listing checks.
- Filter a search with browser controls, or in Telegram/API text with
  `rarity:FFR,SEC` and `finish:holo`. A finish filter intentionally retains
  prints whose finish is not yet labelled rather than guessing they are
  standard.
- Use the far-right “Sort by lowest” filter-style button to order listed
  offers immediately, including when a card has only one Japanese printing.
  Offers remain labelled with their own print code, rarity, finish, stock, and
  availability.
- An importable official English catalogue, including lazy-loaded result pages,
  retained as reference-only data for a future reviewed cross-region feature.
- Concurrent exact-print comparison from Yuyu-Tei, BigWeb, Card Rush,
  VanHappy, Card Shop Olta, Manzokuya, and Mana Source. Olta, Manzokuya, and
  Mana Source search every selected Japanese printing by its Japanese serial;
  Card Rush, VanHappy, and BigWeb do the same for D-PR cards. All connectors
  require an exact printed reference before reporting a price.
- Card Shop Olta preserves its per-condition SKU price and exact quantity.
  Manzokuya preserves a numeric quantity when shown (or a circle/cross stock
  state), and Mana Source preserves its listed quantity or sold-out state.
- English search is identity-first: a name and its aliases resolve to one
  canonical Japanese card name, then return every linked Japanese printing.
  Main-set, Special Series and D-PR reprints sharing that exact Japanese name
  can be narrowed by rarity or finish. Japanese-name equality is the only
  active grouping rule; English print serials are retained but never used as
  mapping or equality evidence.
- Per-store failures are isolated: one unavailable retailer does not prevent
  the other price from being returned.
- A local Telegram long-polling runner. Deployment/webhook hosting is
  deliberately not included yet.

## Local setup

The project uses its own Conda environment at `.conda`; it does not need to
install Python packages globally.

```sh
conda activate "/Users/foonicholas/Documents/ChatGPT/PriceCheck Scraper/ScraperBot/.conda"
python -m pip install --no-build-isolation .
pytest -q
```

This installs only JP Price Checker into that Conda environment; all project
dependencies are already isolated there. Use this normal local install rather
than an editable install because the project path contains spaces.

The full official English catalogue has already been built in the local,
ignored `data/catalogue.sqlite3`. It is retained as reference-only data; its
serials do not attach English names to Japanese prints. To refresh it later:

```sh
scraperbot-import-official --all
```

For a smaller refresh, target individual official set codes:

```sh
scraperbot-import-official --set DZ-BT15 --set D-BT06
```

The importer is polite, sequential, retried on transient failures, and resumes
completed expansions when rerun.

Create `.env` from `.env.example`, insert the token created with Telegram's
BotFather, then run locally:

```sh
scraperbot
```

Example user messages:

```text
/price Youthberk
chronojet ffr
blastr blade
```

The number and rarity shown in selection buttons identify the chosen print;
users never need to remember or type them.

## Use it in a browser

Run the local browser interface in one terminal, then open
`http://127.0.0.1:8787` on this computer:

```sh
scraperbot-web
```

It uses the same local database, natural-language search, and store comparison
services as Telegram. It does not need a Telegram token and is bound to this
computer only by default. You can run `scraperbot` in another terminal to use
Telegram at the same time.

For now, Telegram and the browser show only prints with a Japanese store-search
name. The full English catalogue remains in the database as reference data,
while Fandom-backed or reviewed English names map to Japanese names for search.
English-only printings are hidden because Yuyu-Tei does not stock them.

## Japanese-only and newly released cards

Japanese releases can arrive before Bushiroad publishes their official English
card names. Refresh those cards in two explicit, local-only steps:

```sh
scraperbot-import-japanese --set DZ-BT16
scraperbot-map-fandom --set DZ-BT16
```

To build the complete current-Standard Japanese print master, including
Japanese editions of English releases, use the resumable D/DZ-era import. It
excludes base V-series and older formats, while retaining the D-era `D-PS`,
`D-PV`, and `D-VS` product families because some of their cards remain
current-format playable:

```bash
scraperbot-import-japanese --all
scraperbot-map-fandom --all
scraperbot-derive-japanese-names
scraperbot-repair-regional-mappings
```

The first command imports the official Japanese print master: Japanese name,
set code, collector number, and the official card URL. The second reads the
trusted Cardfight!! Vanguard Wiki Fandom set page through its public API and applies its English
names as `provisional` mappings. A base-card Fandom name is safely propagated
to its parallel prints only when the official Japanese name is identical.
The bulk Fandom command only visits sets with remaining unmapped Japanese
prints; it keeps going if a page is unavailable and reports those sets for
review. The final repair rebuilds D-PR/CP and D/DZ Special Series mappings
from Fandom's Japanese-set pages. No English serial is used for equality in
any set family.

To see what remains before a refresh or mapping review, use the local-only
catalogue report. It makes no store or web requests:

```sh
scraperbot-catalogue-status
```

To run the approved-source refresh for newly published catalogue data, use:

```sh
scraperbot-refresh-catalogue --apply
```

Add `--refresh-promos` to re-read every saved Yuyu-Tei D-Promo range, or
`--repair-regional` after importing a D-PR/CP or D/DZ Special Series batch
whose regional mappings need a full Fandom rebuild. The command never visits
Cloudflare-protected store pages.

Some English reprints correspond to a Japanese promo with a different card
number. Map those declared relationships for each relevant English set:

```sh
scraperbot-map-cross-prints --set DZ-BT12
```

This only accepts Japanese counterparts listed beside that exact English print
on its Fandom card page; it never guesses from translated names or similar
numbers.

Finally, the derivation command resolves reprints only when the exact Japanese
name has one unambiguous existing English mapping. It never uses machine
translation or guesses from similar names.

### Japanese promo repair

Japanese promo identity is now verified against Bushiroad's dedicated
[official PR table](https://cf-vanguard.com/cardlist/card_pr). Run:

```sh
scraperbot-import-official-promos
```

This reads the table's pagination sequentially with a one-second pause between
pages, validates the complete download, and updates Japanese D-PR serials and
names before rebuilding English mappings locally. It also runs as part of
`scraperbot-refresh-catalogue --apply`. No card-search request triggers it.
The table is re-read on each explicit refresh because listings change within
existing pages. A failed page prevents that snapshot from being applied.

`official_promo_identities` stores the official name, detail URL, distribution
information, any upcoming availability date, and verification timestamp.
Upcoming cards are catalogue entries, not evidence of store availability.
Only D-PR rows are imported; older PR/V-PR families are excluded. Existing
rarity and finish annotations are preserved. Cards absent from the table are
not deleted. A later general Japanese import respects the verified PR name.

If an official Japanese name changes, the old English mapping is cleared and
must be resolved again. Otherwise approved review mappings and explicit
cross-print evidence survive repair; remaining English names come from one
unambiguous exact Japanese-name Fandom match in non-promo data. Playable holo
PRs inherit that English name and retain their own
Japanese serial and finish. Energy, Energy Generator, Quick Shield, and Persona
Shield need Japanese serial search only; English mapping is not planned for
them. Yuyu-Tei still supplies retailer locations and explicit finish labels.

`D-PR` is different: Japanese and English promo serials have separate regional
sequences, so an equal number cannot identify the same card. After importing
or updating the catalogue, rebuild Japanese promo name mappings with:

```sh
scraperbot-repair-regional-mappings --set D-PR
```

The command removes stale Japanese-facing D-PR search records, preserves the
official English promo catalogue only as internal reference data, and first
reads only the Fandom page's explicitly Japanese D-Promo section. It stops
before the English section, so an English `D-PR/061EN` cannot overwrite the
Japanese `D-PR/061`. It then restores approved reviews, explicit Fandom
cross-print links, and unambiguous exact-Japanese-name mappings. Utility
printings remain searchable by Japanese serial without English-name mapping.

### Japanese promo catalogue locations

Store pages are a source of Japanese serials and listing locations, not English
names. Import a specific Yuyu-Tei D-Promo page locally with:

```sh
scraperbot-import-yuyutei-promos --page dpromo-1200
```

The import is resumable per page. Re-run it with `--refresh` when a page's
listings need to be checked again. It records the canonical Japanese serial,
Japanese name, page slug, retailer product ID, and product URL without adding
or changing an English search mapping.

To discover every D-Promo navigation group currently exposed by Yuyu-Tei and
import only the exact promo entries it actually lists, run:

```sh
scraperbot-import-yuyutei-promos --all
```

The retailer's range labels are not treated as proof that every serial in the
range exists. Empty groups stay uncheckpointed so a later run can pick up new
listings.

For a selected Japanese D-Promo, Card Rush and VanHappy search its printed serial
(for example `D-PR/953`) directly, then retains only listings carrying that
same exact reference. This works even when the promo is awaiting an English
name review.

BigWeb discovers the store's D-PR set identifier from its public catalogue,
then uses the public product search's `name=D-PR/953` filter. Despite the
parameter name, the store also searches printed references. Promo searches
do not need a Japanese/English name or a separate rarity-catalogue request.
Every returned listing must still carry the exact Japanese serial, and any
explicitly conflicting finish is rejected. Prices remain visible for sold-out
listings, with numeric stock retained where supplied.

BigWeb promo pagination is capped at three pages. If the store reports more,
the connector reports that it is unavailable rather than downloading the
whole D-PR catalogue or displaying a partial price comparison. It does not
retry with a broad name/set query. Live spot checks verify D-PR/953; this is
connector support, not a claim that every promo is stocked by every retailer.

### Japanese serial search

The browser and Telegram bot also accept an exact Japanese print serial:
`D-PR/953`, `DPR953`, or `D-PR 953`. Serial search never uses English serials
and never needs an English mapping: an unmapped Japanese print can still be
selected for exact-print price comparison. Bare numbers remain unsupported to
avoid ambiguity across product families.

### Promo name review queue

Export only Yuyu-Tei-listed D-PR prints that still lack a safe English mapping:

```sh
scraperbot-promo-review export data/dpr-promo-name-review-fresh.json
```

Use a new filename each time: export refuses to overwrite existing reviews.
The version-2 queue records the current canonical Japanese name and source,
the official PR identity where available, and the retailer title separately.
It includes exact-name candidate evidence from the same Fandom-backed sources
used by the automatic repair. Conflicting candidates
are shown together; none is automatically selected or translated.

Review the JSON locally. Keep the identity fields unchanged. Set an entry's `status` to `approved`, fill in its
English name, optional aliases, and (when available) the Fandom source URL.
Then apply it with:

```sh
scraperbot-promo-review apply data/dpr-promo-name-review-fresh.json
```

Only approved records that match a stored Yuyu-Tei D-PR entry are imported.
Each approval must still match the current Japanese identity and source, and
the Japanese card identity must remain unmapped. An approved name attaches to
every Japanese printing with that exact canonical Japanese name; it never uses
English serial equality or loose name similarity. Stale/missing identities, official-name
conflicts, duplicate approvals, invalid names/aliases and already-resolved
prints are skipped with a reason. Legacy version-1 files require a matching
`japanese_name`; re-export older files that lack it. Imports affect the
reviewed Japanese card identity and its exact-name printings, not merely one
serial or similarly named cards. General automatic
name repair remains a separate workflow. An existing mapping cannot be
replaced by this unresolved-name review command.
Energy, Energy Generator, Quick Shield, and Persona Shield entries are marked
`held` (intentionally serial-only). Their English mapping is not required.

The local `data/dpr-promo-name-review-2026-09-12-v5.json` snapshot contains
291 entries: 168 playable prints without eligible evidence, 8 with conflicting
candidates, and 115 serial-only utility prints. It is an unapproved review
artifact, not a new mapping import; prior review files are preserved.

When Bushiroad later publishes an English print, its serial and name remain in
the reference archive. They do not modify Japanese-card equality or search
mapping without a future explicit reviewed cross-print link. There is still no
translation request in the Telegram price path.

For a correction or a source that is not on Fandom, copy the shape in
`data/catalogue.example.json`, add aliases for alternate spellings, and import
it with:

```sh
scraperbot-import your-reviewed-cards.json
```

## Add another retailer

Create a connector under `scraperbot/connectors/` that implements
`StoreConnector.search(card)`. It must return only offers matching the selected
print reference—not a loose name match—and should raise `StoreUnavailableError`
when the set is not listed or the store declines the request. Register it in
both `scraperbot/main.py` and `scraperbot/web.py`; the comparison service will
then query it concurrently.

## Design

```text
English name → local SQLite search → chosen print → exact store lookups → sorted offers
```

The SQLite catalogue, environment, browser artifacts, and test output are all
ignored by Git. Local commits are safe; no remote push is performed by this
project workflow.
