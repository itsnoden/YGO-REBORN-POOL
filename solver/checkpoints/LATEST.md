# Checkpoint 0010 — 2026-09-07

Status: **100% of the effective 2,273-card Reborn pool is mapped**, current Project Ignis CardScripts behavior is pinned and fully re-verified, and the behavior-text audit is down to **186 unresolved lexical effect rows**. Canonical pilot remains uncertified for deck ranking. **No strongest deck has been established yet.**

Read full details in `checkpoints/0010.md` and obey repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt`, `solver/data/source_corrections.json`, and the current BANLIST authority before continuing.

## Canonical verified baseline

Solver Verify #185 (`run_id=34122051457`, commit `e89bc1af711b68bb949519b6b777393bab9908d3`) passed the complete pipeline.

- effective pool: **2,273**
- mapped: **2,273 / 2,273**
- unmapped: **0**
- missing scripts: **0**
- `Double Summon` absent; `reborn-0530` is `Dragged Down into the Grave`
- `reborn-2083`: `Wow Warrior`
- `reborn-1117`: `Longnose Blue Mammoth`
- current CardScripts pin: `14064037f42d0ae0bb9f8577d7eba2baad95e633`
- upstream Reborn-affecting script drift after pin: **0**
- canonical pilot benchmark: **76-60-8 / 144**, zero fallbacks; still not deck-ranking certification

## Text / errata gate

Text Difference Audit #18 (`run_id=34122051459`) passed:
- exact current-text matches: **2,017**
- unresolved lexical behavior rows: **186**
- review priority: **110 high / 29 medium / 47 low**
- presentation-only: **44**
- rules-terminology-only: **17**
- Normal Monster lore-only: **7**
- reviewed non-TCG exact provenance: **2**
- missing-official behavior blockers: **0**

A hash-bound errata review ledger is mandatory. No row may be cleared from similarity alone; accepted reviews bind the exact Reborn ID/passcode/current official-text hash/engine-text hash and automatically become stale if text changes.

## Resume

1. Keep `Double Summon` out of every Reborn candidate/simulation.
2. Start direct card-by-card review of the **110 high-risk lexical rows** using current official text plus current pinned Project Ignis behavior.
3. Save only evidence-backed implementation fixes or hash-bound equivalence reviews; re-run audits after each batch.
4. Continue upstream script-drift checks as Project Ignis advances.
5. Canonical pilot is still not certified for deck ranking; improve it only via controlled no-human-prior A/B tests.
6. Add Extra Deck generation/optimization after errata/pilot gates are strong enough.
7. Only then run certified payoff matrices and adversarial/double-oracle deck search.
8. Never claim a strongest deck prematurely.
