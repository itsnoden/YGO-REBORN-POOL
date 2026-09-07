# YGO Reborn solver — durable duel observations

Updated: 2026-09-06/07

This file is a durable handoff for **engine/pilot observations**, not a deck tier
list. Winner fields from correctness, stochastic-coverage, and learning-smoke
runs are debug-only unless a later experiment is explicitly certified for deck
strength. Do not feed the results below into deck ranking, mutation fitness, or
the double oracle.

## Current strict verification milestone

GitHub Actions `Solver Verify` run **#42** (`run_id=34070493121`) used the exact
pinned dependencies:

- core: `b8c05dff14da0b13608950a73906287dc0b601f9`
- CardScripts: `49b0af044cebcb92f3f23211ef436971e1fc16fb`
- BabelCDB: `9d7f8da324417ec7913b47c52273906c9ae3333b`

Artifact: `solver-verification-8dd1c7ae222aaade93542cb551024c166b4e9658`
artifact id `10000303579`, digest
`sha256:a96eecb6fcb7ad80ec242395993a43a0d47fba91b0b19aaf31b3f1f583a73c38`.

All strict gates passed under the user-confirmed `reborn` rules profile.

### Unit tests

- **41/41 tests passed**.
- The suite covers pool/banlist import legality, shared-name limits, protocol
  parsing/encoding, announce-card expressions, privacy-safe observations,
  prompt-code filtering, stochastic legal responses, learner updates and Reborn
  rules-profile certification.

### Conservative full-duel correctness probe

- attempted: **8**
- completed: **8**
- engine decisions: **2,983**
- filtered observation checks: **2,983**
- filtered policy-prompt checks: **2,983**
- no strict blocker, retry or privacy-filter failure

Interpretation: this establishes that the pinned engine, current protocol layer,
privacy-safe observation layer and conservative legal-response path can traverse
these eight generated candidate matchups end-to-end. It is not win-rate evidence.

### Paired-seat stochastic adversarial-coverage probe

- attempted: **8** games / 4 candidate pairs with seats swapped
- completed: **8**
- engine decisions: **8,096**
- filtered observation checks: **8,096**
- filtered policy-prompt checks: **8,096**
- decisions per game: **551–1,437**, mean **1,012**
- process steps per game: **1,164–2,939**, mean **2,075.5**

Decision-family coverage:

- chain: **5,535**
- idle/main-phase command: **1,545**
- select place/zone: **361**
- battle command: **316**
- select card: **199**
- select/unselect: **81**
- tribute: **39**
- position: **9**
- option: **4**
- effect yes/no: **4**
- announce race: **2**
- select sum: **1**

The games also emitted real summon, special-summon, flip-summon, chain,
selection, draw, damage, recovery, LP-cost, attack, battle, coin-toss and other
engine events. Chain-response decisions dominate the interaction surface, so
future pilot-search efficiency work should pay special attention to chain choice
quality and branching.

Interpretation: this is broad **rules/interaction coverage**, not proof that the
random pilot plays well. Do not convert the debug winners into deck records.

### First from-scratch learning smoke

After fixing observation routing and making incomplete probes fail CI:

- attempted: **8**
- completed: **8**
- total engine decisions: **9,132**
- decisions handled by learned policy: **8,634**
- legal fallback decisions: **498**
- resulting nonzero sparse policy weights: **1,463**
- external strategy priors: **none**
- policy: `sparse_softmax_reinforce_v1`
- training seed: `20260906`

Decision-family coverage:

- chain: **6,260**
- idle/main-phase command: **1,747**
- select place: **435**
- battle: **294**
- select card: **216**
- select/unselect: **102**
- tribute: **48**
- position: **13**
- disable field: **5**
- effect yes/no: **5**
- yes/no: **3**
- option: **2**
- announce race: **1**
- select sum: **1**

This proves that information-safe state/prompt data can drive complete Reborn
self-play and produce nonzero policy updates. It does **not** prove the learned
policy is better than random, generalizes to held-out games, or is ready to rank
decks. The next required pilot milestone is frozen-policy held-out evaluation.

The exact smoke policy is retained in run #42's CI artifact as
`reports/learned_policy_reborn_smoke.json`; individual early weights must not be
interpreted as intrinsic card power.

## Invalidated run that must not be reused

GitHub Actions run **#31** (`run_id=34069085396`) had a green workflow job, but
its generated stochastic and learning reports showed **0/8 completed**. The
blocker was:

`UnsupportedInteraction: pilot observation belongs to wrong player`

Cause: after the filtered prompt boundary was introduced, the filtered prompt
was mistakenly passed to `StochasticLegalPilot.choose`, whose privacy assertion
expects the information-safe observation. `LearningPilot` made the same mistake
in its complex-prompt fallback.

Fixes:

- stochastic probe now passes `observation` to `StochasticLegalPilot`;
- learning fallback now passes `observation` as well;
- regression test added for the learning fallback path;
- conservative/stochastic/learning probes now exit nonzero when requested games
  do not all complete;
- learning smoke additionally requires nonzero learned decisions and weights.

Run #42 is the strict post-fix replacement. Never cite run #31 as successful duel
or learning evidence merely because its GitHub Actions job was green.

## Current engine/text coverage that remains separate from duel-flow success

Current engine-coverage report from run #42:

- Reborn pool: **2,273** exact titles
- mapped to engine IDs: **2,251**
- unmapped engine names: **22**
- mapped official Lua scripts: **1,880**
- scriptless Normal Monsters: **370**
- mapped effect card with missing strict script path: **1**
  (`Red-Eyes Darkness Metal Dragon` errata/path blocker)
- exact official/engine text equality: **1,938**
- non-exact text comparisons requiring audit: **313**

A successful duel-flow probe does not erase those audit tasks. Latest official
card text/errata remains binding, and the solver must not silently use a
historical/pre-errata implementation.

## Rules profile

The solver now uses profile `reborn` by default. The user confirmed the already
implemented current-TCG/MR5-style profile matches YGO Reborn:

- 8,000 LP
- 5-card opening hand
- draw 1 per normal draw
- no first-turn draw
- current/MR5 field mechanics represented by the pinned core flags
- TCG SEGOC flags already used by the project

This gameplay-rules confirmation is separate from the standing requirement to
use **latest official errata/card text always**.

## Next pilot/search work

1. Build a **frozen-policy held-out evaluation**: train on one seed set, freeze,
   compare against the zero-prior stochastic baseline on disjoint seeds with
   paired seats. This measures pilot improvement only, not deck strength.
2. Add safe learned action-set enumeration for complex prompts currently sent to
   fallback (multi-card selections, tribute combinations, sum/counter/place
   choices) so the learner controls a larger fraction of strategic decisions.
3. Reconcile the 22 engine-name mismatches, 313 text differences and the strict
   Red-Eyes Darkness Metal Dragon latest-errata script blocker.
4. Add Extra Deck construction/optimization; it is not yet a searched dimension.
5. After the pilot demonstrates held-out improvement and interaction coverage is
   strong, begin paired-seat **certified payoff** experiments and adversarial
   best-response/double-oracle deck search.

There is still **no established strongest deck, no certified deck win-rate table,
and no #1 deck claim**.
