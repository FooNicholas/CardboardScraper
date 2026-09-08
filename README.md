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

The official English source currently covers releases through the product list
it publishes. A Japanese retailer can list a newer set first. Add a reviewed
mapping for those cards rather than translating in the Telegram request path:

1. Copy the shape in `data/catalogue.example.json` to a new JSON file.
2. Use the Japanese print identifier from the retailer, its reviewed English
   name, and useful alternate spellings in `aliases`.
3. Import it into the same local catalogue:

   ```sh
   scraperbot-import your-reviewed-cards.json
   ```

The importer upserts an exact `(set code, collector number, rarity)` record,
so reviewed mappings can replace provisional information without changing bot
code.

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
