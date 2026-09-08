# Checkpoint 0011 — 2026-09-07

Status: **100% of the effective 2,273-card Reborn pool is mapped**, the canonical solver is green, and the hash-bound errata gate is down to **167 unresolved lexical behavior rows** after 19 accepted reviews. One genuine simulator bug (`Dimension Jar`) has been corrected with a script-hash-bound reviewed override. Canonical pilot remains uncertified for deck ranking. **No strongest deck has been established yet.**

Read full details in `checkpoints/0011.md` and obey repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt`, `solver/data/source_corrections.json`, the current BANLIST authority, and the current errata review ledgers/batches before continuing.

## Canonical verified baseline

Solver Verify #197 (`run_id=34128941415`, commit `324cf91bef3d18274eeceb36c3e051a580866059`) passed the complete pipeline.

- effective pool: **2,273**
- mapped: **2,273 / 2,273**
- unmapped: **0**
- missing scripts: **0**
- `Double Summon` absent; `reborn-0530` is `Dragged Down into the Grave`
- current CardScripts pin: `14064037f42d0ae0bb9f8577d7eba2baad95e633`
- upstream Reborn-affecting script drift after pin: **0**
- canonical pilot benchmark: **76-60-8 / 144**, zero fallbacks; still not deck-ranking certification

## Text / errata gate

Text Difference Audit #27 (`run_id=34181714664`, commit `8dd17ba38b9df14bd68966aa497f6d427946ed0a`) passed:
- raw lexical effect rows: **186**
- accepted reviews: **19**
  - wording-equivalence: **18**
  - implementation-behavior: **1**
- stale/invalid reviews: **0**
- orphan reviews: **0**
- unresolved lexical behavior blockers: **167**

`Dimension Jar` is the first confirmed real simulator-behavior mismatch found by this audit. Its reviewed override is bound to script SHA-256 `60678ac2489585d9b4d2b94601ca16c7d50c1123469721235123dacb9be062a4` and Solver Verify #197 passed with the override active.

Review batches under `solver/data/errata_review_batches/**` now automatically trigger the specialized Text Difference Audit.

## Resume

1. Keep `Double Summon` out of every Reborn candidate/simulation.
2. Continue direct review of the **167 unresolved lexical behavior rows**, prioritizing high-risk rows and hunting actual implementation mismatches.
3. Use wording-equivalence reviews only when directly justified; use narrow overrides + regression tests + script-hash-bound implementation reviews for genuine simulator bugs.
4. Keep upstream script-drift checking mandatory.
5. Canonical pilot is still not certified for deck ranking; improve it only via controlled no-human-prior A/B tests.
6. Add Extra Deck generation/optimization after errata/pilot gates are strong enough.
7. Only then run certified payoff matrices and adversarial/double-oracle deck search.
8. Never claim a strongest deck prematurely.
