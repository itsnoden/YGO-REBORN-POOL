# Checkpoint 0013 — 2026-09-07

Status: **2,273 / 2,273 effective Reborn cards are mapped**, canonical duel verification is green with reviewed `Dimension Jar` and `Fushioh Richie` corrections active, and the hash-bound errata gate is down to **144 unresolved lexical behavior rows** after **42 accepted reviews**. Canonical pilot remains uncertified for deck ranking. **No strongest deck has been established yet.**

Read full details in `checkpoints/0013.md` and obey repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt`, `solver/data/source_corrections.json`, the current BANLIST authority, and current errata ledgers/batches before continuing.

## Verified baseline

Solver Verify #204 (`run_id=34182224605`, commit `694253a7801326daa984b14550692c82a9546ac0`) passed the complete canonical pipeline with both reviewed behavior overrides active.

- effective pool: **2,273**
- mapped: **2,273 / 2,273**
- unmapped: **0**
- missing scripts: **0**
- `Double Summon` absent; `reborn-0530` is `Dragged Down into the Grave`
- CardScripts pin: `14064037f42d0ae0bb9f8577d7eba2baad95e633`
- Reborn-affecting upstream drift after pin: **0**

Text Difference Audit #38 (`run_id=34182948452`, commit `339444c3be7b7cb40ee98e346c381196ced96e0f`) passed:
- raw lexical effect rows: **186**
- accepted reviews: **42**
  - wording: **32**
  - implementation: **10**
- stale/invalid: **0**
- orphan: **0**
- unresolved behavior blockers: **144**

## Confirmed simulator corrections

1. `Dimension Jar` — Monster-only selection correction. Override SHA-256 `60678ac2489585d9b4d2b94601ca16c7d50c1123469721235123dacb9be062a4`.
2. `Fushioh Richie` — blocks generic later Special Summons while preserving Great Dezard's intended hand/Deck summon. Override SHA-256 `8ffa8da98d282cf02f8cd12b00b946d7dcbfc38c5c27fd98d67ef5181508b0b3`.

## Resume

1. Keep `Double Summon` out of every Reborn candidate/simulation.
2. Continue the **144 unresolved** behavior rows, prioritizing deterministic interaction tests and real engine mismatches.
3. Do not guess on `Scroll of Bewitchment`, `Mushroom Man #2`, `Metalsilver Armor`, `Hero Barrier`, `Prohibition`, `Poison Draw Frog`, or `Arcana Force 0 - The Fool`.
4. For real mismatches, use narrow overrides + regression tests + script-hash-bound implementation reviews.
5. Keep upstream script-drift checking mandatory.
6. Canonical pilot is not yet deck-ranking authority.
7. Add Extra Deck optimization only after errata/pilot gates strengthen.
8. Only then run certified payoff matrices/adversarial deck search.
9. Never claim a strongest deck prematurely.
