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

## Known defects

- **BUG-PR-001 — Corrected for the current local D-PR catalogue.** The report
  at [Card Rush product 37326](https://www.cardrush-vanguard.jp/product/37326)
  was caused by the official-English linker treating equal Japanese and English
  `D-PR` serials as identical. They are independent regional sequences:
  Japanese `D-PR/953` is the Leuhan foil, while English `D-PR/953EN` is a
  different card. D-PR and campaign-print official English records now live in
  an internal reference store; they cannot overwrite or appear as Japanese
  search results. The repair rebuilt the local D-PR catalogue from direct
  Fandom evidence and unambiguous exact-Japanese-name matches. Remaining
  unmapped promos are withheld from English-name search until reviewed, rather
  than being given an unsafe match.

## Implementation plan and outstanding work

| Stage | Status | Outcome |
| --- | --- | --- |
| Core catalogue and comparison | Complete | English fuzzy search, Japanese-print selection, local browser and Telegram interfaces, and exact-print comparisons from Yuyu-Tei, BigWeb, Card Rush, and VanHappy. |
| Cross-print links | Complete | A Fandom card page can link an English reprint to a Japanese printing with a different serial; `DZ-BT12/Re07EN` → `D-PR/1247` is the verified example. |
| Promo mapping audit and correction | Implemented for current D-PR data | Equal-serial official promo links are blocked and archived as internal English references. The local D-PR repair cleared 1,694 prior search records, archived 1,103 English references, and restored direct Fandom and exact Japanese-name matches. Energy, Energy Generator, and Quick Shield mappings are explicitly on hold. `D-PR/953` → Leuhan is covered by regression tests. |
| Promo catalogue ingestion | Complete for current Yuyu-Tei scan | `scraperbot-import-yuyutei-promos --all` discovered every current numeric D-Promo group and stored 1,444 exact D-PR entries (numeric serials `1–1757`) from actual Yuyu-Tei listings. It preserves page slug, Japanese name, listing URL, and retailer product ID without creating an English mapping. Empty range groups remain eligible for later refresh. |
| Promo identity enrichment | In progress | The safe automatic D-PR repair is complete. 1,180 current D-PR prints still lack an unambiguous reviewed English name and require explicit Fandom evidence or a review decision before they enter user search. |
| One-time translation review | Planned | Translate only unresolved playable or Energy names during import; persist the approved English search name and provenance locally. No user search may trigger a translation. |
| Serial-number search | Planned | Add Japanese-print serial normalisation, exact reference lookup, ambiguity handling for bare numbers, and Japanese serial result labels. English serials remain internal mapping data only. |
| Multi-store promo lookup | In progress | Yuyu-Tei now uses the stored D-Promo range page for a selected D-PR serial and verifies its exact reference. Card Rush, VanHappy, and BigWeb still need explicit promo catalogue locations or serial-first lookup paths. |
| Hosting | Deferred | Keep the Telegram bot and browser interface local-first until hosting is explicitly requested. |
| Dorasuta | Deferred | Do not add the Dorasuta connector at this time. |

### Planned promo implementation sequence

1. **Complete:** identical Japanese and English promo serials are no longer
   cross-region identity evidence for `D-PR` or campaign print families. Exact
   reference linking remains for release families whose regional numbering is
   explicitly shared.
2. **Complete:** `scraperbot-repair-promo-mappings` archives the conflicting
   English promo records and rebuilds Japanese D-PR search mappings. Its
   regression fixture requires `D-PR/953` to resolve to Leuhan rather than the
   unrelated English `D-PR/953EN` card.
3. **Complete:** the repair builds its mapping index from existing direct
   Fandom mappings and explicit Fandom cross-print links, keeping provenance
   for every accepted result.
4. **Complete:** a promo is mapped automatically only when its exact Japanese
   name has one verified English candidate. Energy, Energy Generator, and
   Quick Shield mappings are held pending a dedicated utility-card workflow.
5. **Next:** put ambiguous, missing, or conflicting Japanese names into a review queue.
   A one-time translation is allowed only for these entries; save the approved
   English name, source, reviewer decision, and timestamp. Never overwrite a
   reviewed mapping merely because another region reuses its serial number.
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
   and playable entries without giving either an English mapping. **In
   complete:** `--all` discovers and backfills the retailer's exposed numeric
   D-Promo page groups, recording only pages that currently contain exact
   listings. The current Yuyu-Tei scan found 1,444 entries through numeric
   serial `1757`; it never assumes a range label means every serial exists.
9. Enrich each promo with official Japanese data and explicit cross-print
   evidence. Send only still-unresolved names to the one-time translation
   review queue.
10. Add Japanese serial normalisation and exact lookup to the catalogue search
   API, the Telegram handler, and the browser UI. Formatted serials resolve
   directly; ambiguous bare numbers prompt for a set family. English serials
   are used only by the import/mapping layer and never appear in user results.
11. **In progress:** Yuyu-Tei reads the exact saved range page for a selected
   promo print. Add equivalent catalogue-location or serial-first metadata for
   Card Rush, VanHappy, BigWeb, and later stores; they still receive the same
   canonical `D-PR/1247` reference.
12. Backfill promo ranges incrementally, verify exact-print offers and stock
   indicators against live listings, then mark each range complete in the
   import checkpoint.

### Explicit non-goals for this work

- No accessory catalogue or accessory search.
- No per-search translation.
- No loose retailer-name matching in place of an exact serial match.
- No hosting work unless separately requested.
