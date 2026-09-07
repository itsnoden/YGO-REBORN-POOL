# Checkpoint 0009 — 2026-09-07

Status: corrected pool identities are enforced end-to-end and Solver Verify **#154** passed. `Double Summon` is absent from the effective pool; stable row `reborn-0530` is corrected to `Dragged Down into the Grave`. `Worm Warrior` is corrected to `Wow Warrior`. Reviewed overlays cover `Red-Eyes Black Chick` and non-TCG `Level Down!`. Only **Long Nose** remains unmapped. Canonical pilot remains uncertified for deck ranking. **No strongest deck has been established yet.**

Read full details in `checkpoints/0009.md` and obey repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt` plus `solver/data/source_corrections.json` before continuing.

## Canonical verified baseline

Solver Verify #154 (`run_id=34116624958`, commit `c26b73a7135719a8d5d1176a59298e285744ebb4`) passed the full pipeline.

- effective pool: **2,273**
- mapped: **2,272 / 2,273**
- unmapped: **Long Nose only**
- missing scripts among mapped cards: **0**
- source correction `reborn-0530`: `Double Summon` -> `Dragged Down into the Grave`
- source correction `reborn-2083`: `Worm Warrior` -> `Wow Warrior`
- canonical pilot benchmark: **76-60-8 / 144**, zero fallbacks; still not deck-ranking certification

## Pilot experiment conclusion

The minimal chain-context feature looked strong in the first cohort but did not replicate materially across 192 games per arm: control **98-91-3**, treatment **100-89-3**. Do **not** promote it.

## Resume

1. Keep `Double Summon` out of every Reborn deck/candidate/simulation; use `Dragged Down into the Grave` at row 530.
2. Resolve `Long Nose` from authoritative identity evidence only; never collapse it into `Great Long Nose`, which is a separate pool entry.
3. Continue the latest-errata/text audit (current canonical non-exact queue: 322).
4. Improve pilot generalization only via controlled A/B tests with no human strategy priors.
5. Add Extra Deck generation/optimization once pilot/errata gates are strong enough.
6. Only then run certified payoff matrices and adversarial/double-oracle deck search.
7. Never claim a strongest deck prematurely.
