# Checkpoint 0007 — 2026-09-07

Status: the episode-credit-normalization A/B completed and rejected the `1/N` equal-total-credit treatment. The canonical learner remains unchanged. Engine mapping remains **2,269 / 2,273**, and pilot generalization remains insufficient for deck-ranking certification. **No strongest deck has been established yet.**

Read full details in `checkpoints/0007.md` and obey repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt` before continuing.

## Canonical verified solver baseline

Solver Verify run **#116** (`run_id=34100241620`) on commit `62cd69512f30624f42110662ad6f00f075fc3458` passed the complete canonical pipeline.

Engine coverage:
- exact pool: 2,273
- mapped: 2,269
- unmapped: 4
- exact-title mappings: 2,251
- reviewed identity aliases: 18
- exact official/engine text equality: 1,938
- non-exact text comparisons requiring audit: 331
- missing required scripts among mapped cards: 0

Unresolved: `Level Down!`, `Long Nose`, `Red-Eyes Black Chick`, `Worm Warrior`. Never fuzzy-map them.

## Pilot baseline

6-block held-out mirror benchmark: 144/144 completed, zero fallbacks, **76-60-8** learned vs stochastic-legal. First 3 blocks were 47-25; added 3 blocks were only 29-35-8. Pilot remains uncertified for deck ranking.

## Rejected credit-normalization experiment

Credit Normalization AB run #1 (`run_id=34103794357`, head `196f373f6cef92689d16f2aee15f7af8c1cd37eb`) completed successfully with 96 identical held-out games per arm.

Control `1/sqrt(N)`:
- 49 wins / 43 losses / 4 draws
- score rate: **53.125%**

Treatment `1/N`:
- 42 wins / 51 losses / 3 draws
- score rate: **45.3125%**

Treatment delta: **-7.8125 percentage points** score rate.
Paired outcomes: 14 improved / 22 degraded / 60 unchanged / 0 unavailable.
Both arms had zero fallbacks; all training/evaluation completed and policies stayed frozen.

**Reject the `1/N` treatment. Do not modify the canonical learner.**

## Resume

1. Preserve the no-human-meta strategy rule.
2. Keep canonical learner unchanged; both tested counterfactual and `1/N` credit treatments have failed A/B.
3. Resolve final 4 card mappings from authoritative identity evidence only.
4. Continue 331-text/latest-errata audit.
5. Improve pilot generalization via isolated, controlled A/B experiments without human card heuristics.
6. Add Extra Deck generation/optimization.
7. Only then run certified payoff matrices and adversarial/double-oracle deck search.
8. Never claim a strongest deck prematurely.
