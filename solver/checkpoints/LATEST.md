# Checkpoint 0012 — 2026-09-07

Status: **100% of the effective 2,273-card Reborn pool is mapped**, the canonical simulator is green with reviewed `Dimension Jar` and `Fushioh Richie` corrections active, and the hash-bound errata gate is down to **146 unresolved lexical behavior rows** after **40 accepted reviews**. Canonical pilot remains uncertified for deck ranking. **No strongest deck has been established yet.**

Read full details in `checkpoints/0012.md` and obey repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt`, `solver/data/source_corrections.json`, the current BANLIST authority, and current errata ledgers/batches before continuing.

## Verified baseline

Solver Verify #204 (`run_id=34182224605`, commit `694253a7801326daa984b14550692c82a9546ac0`) passed the complete canonical pipeline with the Fushioh Richie override active.

- effective pool: **2,273**
- mapped: **2,273 / 2,273**
- unmapped: **0**
- missing scripts: **0**
- `Double Summon` absent; `reborn-0530` is `Dragged Down into the Grave`
- CardScripts pin: `14064037f42d0ae0bb9f8577d7eba2baad95e633`
- Reborn-affecting upstream drift after pin: **0**

Text Difference Audit #37 (`run_id=34182785825`, commit `c7740159eb1006561c813a45e498e478ad2e6667`) passed:
- raw lexical effect rows: **186**
- accepted reviews: **40**
  - wording: **32**
  - implementation: **8**
- stale/invalid: **0**
- orphan: **0**
- unresolved behavior blockers: **146**

## Confirmed simulator corrections

1. `Dimension Jar` — restricts selected GY cards to monsters. Override SHA-256 `60678ac2489585d9b4d2b94601ca16c7d50c1123469721235123dacb9be062a4`.
2. `Fushioh Richie` — cannot be generically revived after Great Dezard; only the intended Great Dezard hand/Deck summon remains legal. Override SHA-256 `8ffa8da98d282cf02f8cd12b00b946d7dcbfc38c5c27fd98d67ef5181508b0b3`.

## Resume

1. Keep `Double Summon` out of every Reborn candidate/simulation.
2. Continue reviewing the **146 unresolved** behavior-text rows, prioritizing real engine mismatches.
3. Do not guess on `Scroll of Bewitchment`, `Mushroom Man #2`, `Metalsilver Armor`, `Hero Barrier`, or `Prohibition`; they need deeper interaction/ruling verification.
4. For real mismatches, use narrow overrides + regression tests + script-hash-bound implementation reviews.
5. Keep upstream script-drift checking mandatory.
6. Canonical pilot is not yet deck-ranking authority.
7. Add Extra Deck generation/optimization only after errata/pilot gates strengthen.
8. Only then run certified payoff matrices/adversarial deck search.
9. Never claim a strongest deck prematurely.
