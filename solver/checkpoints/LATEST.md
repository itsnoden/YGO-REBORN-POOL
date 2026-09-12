# Checkpoint 0017 — 2026-09-11

Status: corrected duel testing has rejected Chain Context and Scalar Context as reliable promoted pilot improvements. Training volume alone gives only a small gain. Paired-seat payoff and duel-guided challenger infrastructure now complete cleanly, but **no strongest deck has been established yet**.

Read full details in `checkpoints/0017.md`. Obey repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt`, exact 2,273-card pool/source corrections, current Reborn banlist, latest official card text/errata, and the no-human-meta rule.

## Current pilot conclusions

- 16 -> 64 training duels/block: **+3.125 score-rate points**, not enough to promote.
- corrected Chain Context:
  - first six-block run: **+7.8125 points**
  - corrected 12-block replication: **+1.0417 points**
  - 64-game training run: **0 points**
  - **not promoted**
- corrected Scalar Context:
  - first six-block run: **+8.333 points**
  - fully disjoint replication: **-2.083 points**
  - **rejected for promotion**

The evaluator must always preserve the exact trained policy subclass during held-out evaluation.

## Duel-search infrastructure

- exploratory paired-seat payoff matrix: **40/40 duels completed**, both seat orientations, zero unsupported/timeouts/fallbacks.
- exploratory duel-guided challenger screen: **96/96 duels completed**, legal mutation/crossover generation, zero unsupported/timeouts/fallbacks.
- exploratory best challenger went **12-4** against a small adversary set, but this is **not deck-ranking evidence** because pilot competence is not yet certified.

## Active next experiments

1. **Phase Turn Context AB**
   - phase + turn-side interactions across all decision families
   - narrower than failed Scalar Context

2. **Discounted Terminal AB**
   - canonical 1/sqrt(N) normalization retained
   - terminal credit half-life = 256 learned decisions
   - generic RL credit-assignment experiment

## Resume

1. Finish both active pilot A/Bs.
2. Any apparent winner must pass a fully disjoint replication before promotion.
3. Promote nothing from one cohort.
4. After a pilot survives replication, run the paired-seat payoff matrix with that exact policy.
5. Expand duel-guided legal mutation/crossover into iterative best-response/double-oracle search.
6. Add Extra Deck generation/optimization before final strongest-deck certification.
7. Never claim #1 prematurely.
