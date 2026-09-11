# JP Price Checker requirements

## Catalogue scope

- Cover current Standard-era Japanese prints, including D and DZ promo cards.
- Catalogue playable cards and Japanese utility cards (Energy, Energy Generator,
  Quick Shield, and Persona Shield). Utility cards need Japanese serial search
  only; their English-name mapping is not outstanding implementation work.
- Keep each physical printing distinct by its printed set code and collector
  number, even when the Japanese and English releases use different codes.
- Preserve English print serials and names as internal reference data, but do
  not use any English set/collector value for Japanese card equality, mapping,
  grouping, or name propagation. Japanese equality is decided only by the
  exact canonical Japanese name from the Japanese catalogue.
- Keep finish separate from rarity. Capture an explicitly shown foil/holo
  treatment such as `H仕様` for `PR 焔の巫女 シンディ(H仕様)`, retain the
  retailer's original annotation, and expose a normalised `holo` flag. Do not
  infer finish from `PR`, a collector number, or a price.
- Store the official Japanese name, an English search name when known, mapping
  provenance, and any retailer-specific catalogue location needed to retrieve
  that print accurately.
- Model a card separately from a printing. A shared card identity is keyed by
  its canonical Japanese name and holds its English search name/aliases; all
  physical Japanese main-set, Special Series and PR printings link to it.
  Conflicting English names for one Japanese identity remain unresolved until
  reviewed.

## Search requirements

- English name search must support partial names and reasonable spelling
  variation.
- Japanese name search must work where a Japanese name is known.
- Exact serial-number search is required for every print, especially promos.
  It must accept conventional forms such as `D-PR/1247`, `DPR1247`, and
  `D-PR 1247`.
- Serial search is Japanese-print-only. It resolves the Japanese serial used
  by the stores and returns only that Japanese listing.
- English serials are retained internal reference data only. They are not
  equality evidence, a user-facing search mode, a selectable result, or a
  displayed serial.
- Serial-number search is store-independent: it selects the canonical print
  before querying Yuyu-Tei, Card Rush, VanHappy, BigWeb, or any later store.
  A serial must never be tied to only the retailer that supplied its catalogue
  entry.
- A bare collector number is only accepted after the user narrows the set
  family, because the same number can occur in more than one product.
- After a name search, users must be able to filter the matching Japanese
  printings by rarity and finish. Rarity filtering must work in the browser
  interface and Telegram, without requiring users to remember the printed
  number. Existing trailing-rarity text is a shortcut, not the only interface.

## Promo and cross-print mapping

- Use the official Japanese PR table at `https://cf-vanguard.com/cardlist/card_pr`
  as the D-PR serial/name authority. Preserve distribution, upcoming availability
  dates, and source provenance separately from English-name mappings.
- Import the complete paginated snapshot before applying changes. Explicit
  refreshes re-read existing pages sequentially with a one-second delay. A
  failed download must not apply a partial snapshot. Never remove a local print
  merely because it is absent from this table.
- Preserve approved English reviews when Japanese identity is unchanged;
  invalidate English evidence if the authoritative Japanese name changes.
- Review exports must use canonical Japanese identities, retain retailer titles
  separately, and include regional-safe exact-name evidence without choosing
  between conflicts. Never overwrite a prior review file. Apply only explicit
  approvals for still-unmapped Japanese identities whose canonical name is unchanged;
  reject stale identities, duplicate approvals and invalid values with reasons.
- Keep utility cards searchable by Japanese serial without an English mapping;
  those shared names must not seed playable-card matches. Existing internal
  `held` flags mean intentionally excluded from translation, not pending work.
- Playable promo reprints, including holo variants, must inherit an English
  search name when their exact Japanese name resolves unambiguously to a
  Fandom-backed mapped main-set or Special Series card. Conflicting names remain
  unresolved. Keep the Japanese serial, rarity, and finish distinct.
- Once an exact Japanese card identity has an accepted English name, attach
  every Japanese printing with that exact name—including D-PR and Special
  Series reprints—without using English serial equality. Rarity/finish filters
  apply after that identity lookup.

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
- Provide a separate all-printings comparison for a named card: gather offers
  for every verified Japanese reprint of that canonical card, retain the
  print code, rarity, and finish on each offer, and sort by the lowest current
  price. The existing exact-print comparison remains the default.

## Known defects

- **BUG-REVIEW-001 — Corrected.** Review export formerly used retailer titles,
  and apply did not verify the reviewed Japanese name against the current
  master. A stale file could therefore restore an incorrect mapping after an
  official identity correction. Version-2 exports retain canonical identity
  and evidence; apply validates identity/source under the same transaction as
  its writes, rejects already-mapped targets, and maps only approved serials.
  Null English names are no longer coerced into the literal string `None`.

- **BUG-IDENTITY-001 — Corrected.** English search names used to be attached
  independently to physical Japanese prints. A mapped main printing could fail
  to expose its D-PR or Special Series reprints. `card_identities` now owns the
  English name and links all exact-name Japanese printings. Inconsistent legacy
  translations are left unlinked rather than selecting a name by import order.

- **BUG-REGION-001 — Corrected globally.** Earlier code treated a matching
  Japanese/English set and collector number as the same card. That made
  `D-PR/953` appear as an unrelated English card, `DZ-SS10/018`
  (`ケッパー・コンパニオン`) appear as Vital Blaze Blast, and Japanese
  `D-BT09/Re06` (Burning Flail Dragon) appear as Trickmoon. All legacy
  English-number mapping claims are archived for future review. The active
  identity model now uses only exact canonical Japanese names, so no English
  serial can overwrite, group, or appear in Japanese price-search results.

## Implementation plan and outstanding work

| Stage | Status | Outcome |
| --- | --- | --- |
| Core catalogue and comparison | Complete | English fuzzy search, Japanese-print selection, local browser and Telegram interfaces, and exact-print comparisons from Yuyu-Tei, BigWeb, Card Rush, VanHappy, Card Shop Olta, Manzokuya, and Mana Source. |
| Shared Japanese card identity | Implemented | English names/aliases belong to a canonical Japanese card identity, and physical Japanese prints link below it only when their exact Japanese name matches. Main, D-PR and Special Series prints can return together and be filtered by rarity/finish. English serials are reference-only and cannot affect this grouping. |
| Responsive local search during price checks | Implemented | The local browser now serves searches independently of an in-progress store comparison. A slow retailer response can delay that comparison, but it cannot make a new local catalogue search wait behind it. |
| Cross-print links | Complete | A Fandom card page can link an English reprint to a Japanese printing with a different serial; `DZ-BT12/Re07EN` → `D-PR/1247` is the verified example. |
| Official Japanese PR identity import | Implemented | `scraperbot-import-official-promos` imports the dedicated official D-PR table, then rebuilds English mappings. Integrated into the catalogue refresh before mapping. Local scan verified 1,806 identities, including upcoming D-PR/1839, and retained 37 existing D-PR records absent from the table. Preserves reviewed names unless Japanese identity changes, retains finish/rarity, and records upcoming releases separately from store stock. |
| Promo mapping audit and correction | Implemented for current D-PR data | English serial links and generic English D-Promo-list links cannot identify Japanese promos. Repair retains approved reviews and explicit Fandom cross-print evidence, then uses an unambiguous exact Japanese-name Fandom match. Utility cards intentionally use serial search only. `D-PR/953` → Guard Running Through The Earth, Leuhan is covered by regression tests. |
| English-reference equality audit | Complete | All legacy mapping rows inferred from English printed references are archived, while the English serial/name records remain available for future reviewed features. `DZ-SS10/018` resolves to Caper Companion and Japanese `D-BT09/Re06` no longer resolves to Trickmoon. |
| D-era P/V mapping scope | Complete | Automatic Fandom refresh includes the D-era `D-PS`, `D-PV`, and `D-VS` product families because some cards remain current-format playable. They use the same exact-Japanese-name identity rule as every other supported Japanese print. |
| Promo catalogue ingestion | Complete for current Yuyu-Tei scan | `scraperbot-import-yuyutei-promos --all` discovered every current numeric D-Promo group and stored 1,444 exact D-PR entries (numeric serials `1–1757`) from actual Yuyu-Tei listings. It preserves page slug, Japanese name, listing URL, and retailer product ID without creating an English mapping. Empty range groups remain eligible for later refresh. |
| Japanese-section D-Promo name deconfliction | Implemented and applied | The Fandom parser now reads only the page's labelled Japanese D-Promo section and stops before its English section, so `D-PR/061` resolves to Flinty Slasher rather than the unrelated `D-PR/061EN` card. A local rebuild applied 731 direct Japanese-list mappings, reduced all playable D-PR records awaiting review from 494 to 270, and increased English-searchable Japanese prints from 15,300 to 15,560. |
| Promo identity enrichment | Review workflow complete — content review pending | Current Yuyu-Tei scope: 1,444 entries, 1,153 English-mapped, 176 unresolved playable, and 115 intentionally serial-only utility entries. `data/dpr-promo-name-review-2026-09-12-v5.json` is the fresh unapproved queue; `apply` accepts explicit approvals with provenance. |
| One-time translation review | Ready for reviewed input | Current D-PR data has 270 unresolved playable/upcoming prints. In the current 1,444-entry Yuyu-Tei scope, 168 have no eligible evidence and 8 have conflicting candidates; the remaining unresolved official PR entries are not in the current retailer scope. Review only playable cards; 210 utility prints intentionally require no English mapping. No user search may trigger a translation. |
| Evidence-backed review and stale-approval protection | Implemented | Version-2 review exports use canonical/official Japanese identity, separate retailer titles, and Fandom-backed exact-name candidate evidence. Export preserves existing files; apply rejects stale/duplicate/invalid approvals and resolved targets with reasons. The fresh local Yuyu-Tei queue has 168 no-candidate playable prints, 8 conflicting-candidate playable prints, and 115 intentionally serial-only utility prints. No entries are approved. |
| Serial-number search | Implemented | Browser and Telegram accept formatted Japanese serials such as `D-PR/953`, `DPR953`, and `D-PR 953`. A serial can select an unmapped Japanese print for exact comparison without creating an English mapping. Bare numbers are rejected; English serials remain internal only. |
| Finish / holo metadata | Implemented | Canonical Japanese prints and store offers retain raw finish text plus a normalised holo/standard/unknown value. A Yuyu-Tei D-PR title marked `H仕様` enriches that exact Japanese serial's local print record as holo and is displayed in search results; an explicitly conflicting retailer finish is excluded from an exact-print comparison. |
| Rarity and finish filters | Implemented | The browser offers multi-select rarity and finish controls; Telegram and the search API accept `rarity:FFR,SEC` and `finish:holo`. The trailing-rarity shortcut remains supported. Unknown-finish printings stay visible when filtering by holo or standard. |
| Aggregate card prints / comparison sorting | Implemented | The far-right filter-bar action is labelled `Aggregate card prints` and has a hover explanation that it compares every verified Japanese printing of the card, including a one-printing card. Every price-comparison box—one selected print or the aggregated card-print view—has a single-click three-line up/down sort toggle. It reorders only the offers already displayed, instantly: in-stock rows remain first, then sold-out and unknown-stock rows; each group sorts by price in the shown direction and unavailable prices stay last. |
| Catalogue maintenance report | Implemented | `scraperbot-catalogue-status` is a read-only local report of Japanese search coverage, unmapped promo workload, held utility cards, Special Series coverage, and saved Yuyu-Tei D-Promo entries. It supports planning a refresh without contacting any retailer. |
| Approved-source catalogue refresh | Implemented | `scraperbot-refresh-catalogue --apply` checks the official Japanese and English catalogues, keeps English data reference-only, applies Fandom mappings and safe Japanese-name derivation, and refreshes Yuyu-Tei D-Promo locations. It is opt-in, supports a full promo reread and regional rebuild, and never contacts protected price-store pages. |
| Multi-store promo lookup | Implemented | Yuyu-Tei uses the stored D-Promo range page; Card Rush and VanHappy use `D-PR/number` as their public search keyword. BigWeb discovers its D-PR set ID and applies the public `name` filter to the same serial, without a rarity lookup. Exact references and explicit finish conflicts are checked. BigWeb stops overbroad responses before pagination (maximum three pages), with no broad fallback. D-PR/953 was spot-checked live; wider retailer coverage remains to be audited. |
| Olta, Manzokuya, and Mana Source | Implemented | Each connector performs one public exact-Japanese-serial lookup for the selected print—no catalogue crawl or detection bypass. Olta reads its normal storefront product response and retains per-condition price and numeric quantity. Manzokuya reads the product-list price plus its numeric/circle/cross stock signal. Mana Source retains a numeric quantity, an in-stock/sold-out label, and a displayed price when available. All three reject any result whose printed serial or explicit finish conflicts with the selected print. |
| Candidate store connectors | Planned — discovery and permission review | Add only after confirming a permitted, narrow exact-Japanese-serial lookup and the store's price/stock fields. Backlog: TCG Noah, PAOtcg, Cardshop Isei, ゲーマーズ, C-labo, Amenity Dream, Square Bushiroad, Torecolo, Hobby Station, 193net, FullAhead-VG, Advantage TCG, Cardshop Avalon, Card Max, Card Museum, Toreca Plaza, Realize TCG, Masters Guild, G Project TCG, Pachipachi TCG, and Ryuunoshippo. Each connector must validate the printed serial and explicit finish before an offer can be displayed. |
| Cloudflare-protected stores | On hold | Do not bypass protection or evade detection. Add a connector only after the store supplies a permitted API, data export, partner access, or explicit allowlisting for this app. |
| Hosting | Deferred | Keep the Telegram bot and browser interface local-first until hosting is explicitly requested. |
| Dorasuta | On hold | Do not add the Dorasuta connector at this time. Reassess only if a permitted, narrow exact-serial integration path is available; no detection bypass. |

### Planned promo implementation sequence

Current database snapshot after archiving English-number equality claims:
16,219 Japanese prints overall; 7,295 canonical Japanese-name identities link
15,560 physical printings. The 11,079 former English-number mapping claims are
in the local archive, alongside retained English serial/name reference data.
1,844 promo prints include 270 playable records awaiting Fandom-backed or
reviewed English names; 210 utility prints remain intentionally serial-only.
Of 1,736 Special Series prints across 27 sets, only 44 remain unmapped because
exact Japanese-name Fandom evidence links the rest. Counts describe print
records, not distinct card names.

1. **Complete:** Japanese/English printed serial equality is never card
   identity evidence, for any set family. Legacy claims are archived; the
   English serial data itself is retained for later reviewed extensions.
2. **Complete:** `scraperbot-repair-promo-mappings` archives the conflicting
   English promo records and rebuilds Japanese D-PR search mappings. Its
   regression fixture requires `D-PR/953` to resolve to Leuhan rather than the
   unrelated English `D-PR/953EN` card.
3. **Complete:** the official PR table establishes Japanese serial/name identity.
   The repair retains approved reviews and explicit Fandom cross-print links,
   then uses non-promo Fandom Japanese-name matches. Generic English promo-list
   serials are not Japanese identity evidence. Provenance is retained.
4. **Complete:** playable PRs inherit one unambiguous Fandom-backed English
   candidate through the exact Japanese name of a main-set or Special Series
   printing. Holo finish and Japanese serial remain distinct. Utility-card
   serial search is sufficient; English mapping is not planned for them.
5. **Complete:** export ambiguous, missing, or conflicting Japanese names into
   a Yuyu-Tei-scoped review queue. A one-time translation is allowed only for
   explicitly approved entries; save the English name and source. Energy,
   Energy Generator, and shield records remain serial-only. Never overwrite
   a reviewed mapping merely because another region reuses its serial number.
   **Hardened:** version-2 exports include current canonical identity and
   exact-name evidence; imports reject stale approvals and do not overwrite
   newly resolved mappings. **Complete:** an accepted English name now belongs
   to a shared canonical Japanese card identity, so every exact-name Japanese
   printing is returned by one English search; the association never uses an
   English serial.
6. Add regression tests for corrected, rejected, and ambiguous D-PR mappings,
   including a Card Rush exact-print fixture for the reported product. The
   audit must pass before any bulk promo import writes user-searchable English
   names.
7. **Complete:** `promo_catalogue_entries` is a local import store keyed by
   Japanese serial. It saves the Yuyu-Tei page, product URL, product ID, and
   Japanese name separately from canonical card identity so later retailers
   can use the same print.
8. **Complete:** `scraperbot-import-yuyutei-promos --page dpromo-1200` imports
   a specified page with an atomic completion checkpoint. It retains Energy
   and playable entries without giving either an English mapping. **Complete:**
   `--all` discovers and backfills the retailer's exposed numeric
   D-Promo page groups, recording only pages that currently contain exact
   listings. The current Yuyu-Tei scan found 1,444 entries through numeric
   serial `1757`; it never assumes a range label means every serial exists.
9. **Ready for content review:** official PR-table identities are imported
   before English mapping. Remaining playable names still need explicit
   cross-print evidence or reviewed, one-time translation. The Fandom reader
   now uses only its labelled Japanese D-Promo section, never its English
   regional sequence. The fresh `data/dpr-promo-name-review-2026-09-12-v5.json`
   queue contains 176 unresolved playable retailer entries (168 no eligible
   candidate, 8 conflicts) and 115 intentionally serial-only utility entries. No entries
   are approved.
10. **Complete:** Japanese serial normalisation and exact lookup work in the
   catalogue search API, Telegram handler, and browser UI. Formatted serials
   resolve directly; bare numbers are rejected as ambiguous. An unmapped
   Japanese print can still be selected for exact comparison without creating
   an English mapping. English serials are reference-only data.
11. **Complete:** Yuyu-Tei reads the exact saved range page; Card Rush and
   VanHappy search by Japanese promo serial. BigWeb discovers its D-PR set and
   uses the public product `name` filter for the serial, preserving that filter
   across at most three result pages. An overbroad/failed response never triggers
   a full promo-catalogue fallback. Offline tests cover unmapped promos, serial
   boundaries, finish conflicts, stock/OOS prices, and bounded pagination.
   Live D-PR/953 spot checks verified both new paths on 2026-09-11.
12. Backfill promo ranges incrementally, verify exact-print offers and stock
   indicators against live listings, then mark each range complete in the
   import checkpoint.

### Planned print-variant and card-level comparison sequence

1. **Complete:** extend the canonical Japanese printing and store-offer
   schemas with a raw finish annotation and a normalised finish type. `H仕様`
   imports as holo while retaining the original text for display and later
   rules.
2. **Complete:** update each store parser and exact-reference matcher to
   capture finish independently from rarity. A tested Yuyu-Tei fixture proves
   a declared standard variant cannot be returned for a selected holo print.
3. **Complete:** add a multi-select rarity/finish filter layer to browser
   search results and Telegram commands. Filtering narrows results only; it
   never changes a card's identity or hides a result merely because finish
   data is unknown.
4. **Complete:** introduce a verified card-family relation that groups
   Japanese reprints only when their exact canonical Japanese name and
   normalised mapped English name agree. Names that merely look alike remain
   separate.
5. **Complete:** add an opt-in “lowest price across printings” comparison.
   Each family member is retrieved through the existing exact-print
   connectors; priced in-stock offers sort ascending while every row keeps its
   print, rarity, finish, availability, and stock.
6. **Complete:** add browser and Telegram presentation for the aggregate
   view. In the browser, every unambiguous card result—including one with a
   single printing—exposes the action at the far right of its filter bar
   without requiring a selection; selected-print comparison otherwise remains
   the default.

### Explicit non-goals for this work

- No accessory catalogue or accessory search.
- No per-search translation.
- No loose retailer-name matching in place of an exact serial match.
- No hosting work unless separately requested.
