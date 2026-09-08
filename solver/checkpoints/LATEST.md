# Checkpoint 0015 — 2026-09-08

Status: **2,273 / 2,273 effective Reborn cards are mapped**, canonical duel verification is green with four reviewed simulator corrections active, and the hash-bound errata gate is down to **132 unresolved lexical behavior rows** after **54 accepted reviews**. Canonical pilot remains uncertified for deck ranking. **No strongest deck has been established yet.**

Read full details in `checkpoints/0015.md` and obey repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt`, `solver/data/source_corrections.json`, the current BANLIST authority, and current errata ledgers/batches before continuing.

## Verified behavior baseline

Solver Verify **#230** (`run_id=34185025295`, commit `8f3d8c31edd0bdf4b5c51e2950c66276c1306124`) passed the complete canonical pipeline with the TCG-specific Poison Draw Frog correction active and hash-bound.

- effective pool: **2,273**
- mapped: **2,273 / 2,273**
- unmapped: **0**
- missing scripts: **0**
- `Double Summon` absent; `reborn-0530` is `Dragged Down into the Grave`
- CardScripts pin: `14064037f42d0ae0bb9f8577d7eba2baad95e633`
- Reborn-affecting upstream script drift after pin: **0**
- canonical pilot benchmark: **76-60-8 / 144**, zero fallbacks; still not deck-ranking certification

Text Difference Audit **#52** (`run_id=34185025294`, same commit) passed:
- raw lexical effect rows: **186**
- accepted reviews: **54**
  - wording: **41**
  - implementation: **13**
- stale/invalid: **0**
- orphan: **0**
- unresolved behavior blockers: **132**

## Confirmed simulator corrections

1. `Dimension Jar` — monster-only selection correction. Override SHA-256 `60678ac2489585d9b4d2b94601ca16c7d50c1123469721235123dacb9be062a4`.
2. `Fushioh Richie` — blocks generic later Special Summons while preserving Great Dezard's intended hand/Deck summon. Override SHA-256 `8ffa8da98d282cf02f8cd12b00b946d7dcbfc38c5c27fd98d67ef5181508b0b3`.
3. `Formation Union` — correct mode-dependent targeting. Override SHA-256 `23475e45fbc91dd47c8d793d378fb76ce0447949772bbf7f891d0ca40d463af8`.
4. `Poison Draw Frog` — current TCG face-down-when-attacked battle exception. Override SHA-256 `99ed3e7a3a19c0a2a015342b07d817cdd99b26eee7b6b2333f12b8527bc43687`.

## Resume

1. Keep `Double Summon` out of every Reborn candidate/simulation.
2. Continue the **132 unresolved** behavior rows using only current official text/rulings plus pinned executable behavior; never clear ambiguity by similarity alone.
3. For genuine mismatches, use narrow overrides + regression tests + script-hash-bound implementation reviews.
4. Keep upstream script-drift checking mandatory.
5. Canonical pilot remains separate from deck-strength evidence and is not yet deck-ranking authority.
6. Improve the pilot only through controlled no-human-prior A/B experiments.
7. Add Extra Deck optimization only after errata/pilot gates strengthen.
8. Only then run certified payoff matrices/adversarial deck search.
9. Never claim a strongest deck prematurely.
