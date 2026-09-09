# ScraperBot

A local-first Cardfight!! Vanguard price-comparison Telegram bot. Users search
by English card name (including partial names and reasonable typos), choose a
matching print, and receive offers from the enabled Japanese stores.

It does not translate while a user waits. The English card mapping lives in a
local SQLite database and store connectors use the selected print identifier
only after the user has chosen it.

## What is implemented

- Local FTS and fuzzy English-name search, including aliases and optional
  trailing rarity: `/price Youthberk FFR`.
- An importable official English catalogue, including lazy-loaded result pages.
- Concurrent exact-print comparison from Yuyu-Tei and BigWeb.
- Per-store failures are isolated: one unavailable retailer does not prevent
  the other price from being returned.
- A local Telegram long-polling runner. Deployment/webhook hosting is
  deliberately not included yet.

## Local setup

The project uses its own Conda environment at `.conda`; it does not need to
install Python packages globally.

```sh
conda activate "/Users/foonicholas/Documents/ChatGPT/PriceCheck Scraper/ScraperBot/.conda"
pytest -q
```

The full official English catalogue has already been built in the local,
ignored `data/catalogue.sqlite3`. To rebuild it later:

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

## Japanese-only and newly released cards

Japanese releases can arrive before Bushiroad publishes their official English
card names. Refresh those cards in two explicit, local-only steps:

```sh
scraperbot-import-japanese --set DZ-BT16
scraperbot-link-official-japanese
scraperbot-map-fandom --set DZ-BT16
```

To build the complete current-Standard Japanese print master, including
Japanese editions of English releases, use the resumable D/DZ-era import. It
deliberately excludes V-series and older formats:

```bash
scraperbot-import-japanese --all
scraperbot-link-official-japanese
scraperbot-map-fandom --all
scraperbot-derive-japanese-names
```

The first command imports the official Japanese print master: Japanese name,
set code, collector number, and the official card URL. The second matches the
official English catalogue by exact printed reference to link names that exist
in both languages. The third reads the trusted Cardfight!!
Vanguard Wiki Fandom set page through its public API and applies its English
names as `provisional` mappings. A base-card Fandom name is safely propagated
to its parallel prints only when the official Japanese name is identical.
The bulk Fandom command only visits sets with remaining unmapped Japanese
prints; it keeps going if a page is unavailable and reports those sets for
review.

Finally, the derivation command resolves reprints only when the exact Japanese
name has one unambiguous existing English mapping. It never uses machine
translation or guesses from similar names.

When Bushiroad later publishes an English print, the official-English importer
always preserves that name rather than replacing it with a Fandom mapping.
There is still no translation request in the Telegram price path.

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
when the set is not listed. Register it alongside Yuyu-Tei and BigWeb in
`scraperbot/main.py`; the comparison service will then query it concurrently.

## Design

```text
English name → local SQLite search → chosen print → exact store lookups → sorted offers
```

The SQLite catalogue, environment, browser artifacts, and test output are all
ignored by Git. Local commits are safe; no remote push is performed by this
project workflow.
