# Checkpoint 0008 — 2026-09-07

Status: refreshed latest-official text coverage improved, and the first minimal chain-context pilot A/B was promising but is **not yet strong enough to promote**. The canonical learner remains unchanged. **No strongest deck has been established yet.**

Read full details in `checkpoints/0008.md` and obey repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt` before continuing.

## Engine / official-text state

- exact Reborn pool: **2,273**
- engine mapped: **2,269**
- engine unmapped: **4** — `Level Down!`, `Long Nose`, `Red-Eyes Black Chick`, `Worm Warrior`
- latest-official records matched after refresh: **2,257 / 2,273**
- missing latest-official records: **16**
- exact official/engine text matches: **1,952**
- remaining text differences: **317**
- missing scripts among mapped cards: 0

Never fuzzy-map unresolved identities.

## Pilot state

Canonical 6-block pilot baseline remains uncertified for deck ranking: **76-60-8** over 144 held-out mirror games with zero fallbacks, but the last three blocks were only 29-35-8.

Rejected experiments remain rejected:
- counterfactual treatment
- equal-total-credit `1/N`
- broad contextual/card-identity expansion

## Promising chain-context experiment

Chain Context AB run #1 (`run_id=34105414843`) completed 96 held-out games per arm.

Control: **39-52-5**, score rate **43.229%**.
Treatment (only phase/turn-side/chain-depth x action on chain prompts): **46-44-6**, score rate **51.042%**.
Delta: **+7.812 percentage points** score rate.
Paired: **22 improved / 14 degraded / 60 unchanged**.

Promising, but not decisive (paired two-sided p ≈ 0.243). **Do not promote yet. Replicate on a disjoint candidate cohort with new seeds.**

## Resume

1. Preserve the no-human-meta strategy rule.
2. Replicate minimal chain-context A/B on disjoint candidates and seeds.
3. Resolve remaining 16 missing latest-official records from authoritative identity evidence only.
4. Continue the 317-text/latest-errata audit.
5. Resolve final 4 engine mappings without fuzzy substitution.
6. Improve pilot generalization before any deck ranking.
7. Add Extra Deck generation/optimization after pilot/errata gates.
8. Only then run certified payoff matrices and adversarial/double-oracle deck search.
9. Never claim a strongest deck prematurely.
