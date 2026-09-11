# Checkpoint 0016 — 2026-09-11

Status: **duel-testing resumed and a critical held-out policy-evaluation bug was fixed.** Prior A/Bs that used a `SparsePolicy` subclass did not preserve the subclass at evaluation time, so previous chain-context conclusions are invalid until corrected reruns finish. **No strongest deck has been established yet.**

Read full details in `checkpoints/0016.md` and obey repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt`, exact pool/source corrections, current Reborn banlist, latest-card-text requirement, and the no-human-meta rule.

## Critical correction

`pilot_eval.run_eval_game` used to rebuild every frozen treatment as base `SparsePolicy`, silently disabling treatment-specific feature generators during held-out games.

Fixed by preserving `frozen_policy.__class__` in frozen evaluation.

Regression coverage:
- `solver/tests/test_pilot_eval_policy_class.py`

Prior chain-context A/B and replication results must not be used for promotion/rejection decisions.

## Active duel work

1. **Training Volume A/B**
   - 16 vs 64 self-play training duels per block
   - 6 blocks
   - paired held-out mirror evaluation
   - unaffected by the subclass bug because both arms are base `SparsePolicy`

2. **Corrected Scalar Context A/B**
   - coarse public scalar state x option interactions
   - no known-card context or human strategy priors
   - corrected rerun triggered after policy-class fix

3. **Corrected Chain Context A/B**
   - previous evidence invalidated
   - clean subclass-preserving rerun triggered

4. **Paired-seat payoff matrix infrastructure**
   - same frozen policy controls both seats
   - both seat orientations on identical seeds
   - information-safe observation checks
   - unsupported/timeouts/fallbacks invalidate certification
   - still reports `deck_ranking_evidence: false` until pilot-skill promotion

## Resume

1. Finish the three controlled duel experiments.
2. Promote a pilot only from corrected held-out evidence.
3. Run the first real head-to-head paired-seat payoff matrix.
4. Use duel outcomes to drive adversarial mutation/crossover search and double-oracle iteration.
5. Keep pilot-skill evidence separate from deck-strength evidence.
6. Never claim #1 prematurely.
