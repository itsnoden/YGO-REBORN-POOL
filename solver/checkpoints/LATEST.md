# Checkpoint 0014 — 2026-09-07

Status: **2,273 / 2,273 effective Reborn cards are mapped**, canonical duel verification is green with three reviewed simulator corrections active, and the hash-bound errata gate is down to **133 unresolved lexical behavior rows** after **53 accepted reviews**. Canonical pilot remains uncertified for deck ranking. **No strongest deck has been established yet.**

Read full details in `checkpoints/0014.md` and obey repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt`, `solver/data/source_corrections.json`, the current BANLIST authority, and current errata ledgers/batches before continuing.

## Verified behavior baseline

Solver Verify **#220** (`run_id=34184137985`, commit `9c0238ae82160458d7b01723c0a439d8312cc116`) passed the complete canonical pipeline with the Formation Union correction active and hash-bound.

- effective pool: **2,273**
- mapped: **2,273 / 2,273**
- unmapped: **0**
- missing scripts: **0**
- `Double Summon` absent; `reborn-0530` is `Dragged Down into the Grave`
- CardScripts pin: `14064037f42d0ae0bb9f8577d7eba2baad95e633`
- Reborn-affecting upstream script drift after pin: **0**

Text Difference Audit **#49** (`run_id=34184684557`, commit `015d5d474a38dfbfd0d12a5b3a01afcb1e7ef89e`) passed:
- raw lexical effect rows: **186**
- accepted reviews: **53**
  - wording: **41**
  - implementation: **12**
- stale/invalid: **0**
- orphan: **0**
- unresolved behavior blockers: **133**

## Confirmed simulator corrections

1. `Dimension Jar` — monster-only selection correction. Override SHA-256 `60678ac2489585d9b4d2b94601ca16c7d50c1123469721235123dacb9be062a4`.
2. `Fushioh Richie` — blocks generic later Special Summons while preserving Great Dezard's intended hand/Deck summon. Override SHA-256 `8ffa8da98d282cf02f8cd12b00b946d7dcbfc38c5c27fd98d67ef5181508b0b3`.
3. `Formation Union` — mode 1 targets only the Union monster; equip recipient is chosen at resolution; mode 2 is non-targeting. Override SHA-256 `23475e45fbc91dd47c8d793d378fb76ce0447949772bbf7f891d0ca40d463af8`.

## Resume

1. Keep `Double Summon` out of every Reborn candidate/simulation.
2. Next behavior-changing task: implement the **TCG-specific Poison Draw Frog correction** for the face-down-when-attacked battle exception, add regression tests, hash-bind it, and require a full Solver Verify before declaring correction #4.
3. Continue the **133 unresolved** behavior rows using only official text/rulings plus pinned executable behavior; never clear ambiguity by similarity alone.
4. Keep upstream script-drift checks mandatory.
5. Canonical pilot remains separate from deck-strength evidence and is not yet deck-ranking authority.
6. Add Extra Deck optimization only after errata/pilot gates strengthen.
7. Only then run certified payoff matrices/adversarial deck search.
8. Never claim a strongest deck prematurely.
