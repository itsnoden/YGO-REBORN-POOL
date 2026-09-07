# YGO Reborn solver — durable duel observations

Updated: 2026-09-06/07 — checkpoint 0005

This file is a durable handoff for **engine and pilot observations**, not a deck
tier list. Do not feed correctness/stochastic/smoke results into deck ranking,
mutation fitness, payoff matrices or the double oracle unless a later experiment
explicitly qualifies as certified deck-strength evidence.

There is still **no established strongest deck and no certified deck win-rate
table**.

## Canonical strict verification — run #60

GitHub Actions `Solver Verify` run **#60** (`run_id=34072551222`), commit
`599d96ae47aa4280df00afb49ca280491e8d0e52`.

Artifact:
- id `10000962499`
- digest `sha256:bf4dea9e46d381050f367d6e1b0237ade23b9ecfa705b911a2bc9f100322fa4b`

Pinned dependencies:
- core `b8c05dff14da0b13608950a73906287dc0b601f9`
- CardScripts `49b0af044cebcb92f3f23211ef436971e1fc16fb`
- BabelCDB `9d7f8da324417ec7913b47c52273906c9ae3333b`

All strict gates passed under the user-confirmed `reborn` profile.

### Unit tests

- **44/44 passed**.
- Includes the prior pool/banlist, protocol, privacy, learning and rules tests plus
  explicit reviewed-script-override presence, precedence and fallback tests.

### Conservative full-duel correctness

- attempted/completed: **8/8**
- decisions: **2,983**
- safe observation checks: **2,983**
- filtered policy-prompt checks: **2,983**

This proves the tested engine/protocol/privacy path completes. It is not win-rate
evidence.

### Stochastic interaction coverage

- attempted/completed: **8/8**
- decisions: **8,096**
- safe observation/prompt checks: **8,096 / 8,096**

Decision-family coverage:
- chain 5,535
- idle 1,545
- select place 361
- battle 316
- select card 199
- select/unselect 81
- tribute 39
- position 9
- option 4
- effect yes/no 4
- announce race 2
- select sum 1

These are broad rules/interaction observations from a random legal pilot, not deck
strength. Chain choice remains by far the largest strategic branching surface.

### Learning smoke

- attempted/completed: **8/8**
- learned decisions: **8,634**
- legal fallback decisions: **498**
- resulting nonzero weights: **1,463**
- external strategy priors: none

This continues to prove only that information-safe self-play and policy updates
work end-to-end.

## Double Spell deterministic stack-overflow — diagnosed and fixed

The first held-out evaluator repeatedly failed at exactly:
- candidate `593df70fb35282f5`
- seed `21101`
- learned seat `1`
- process call `2105`

The detailed crash probe preserved the last decisions and referee-only diagnostic
state. Immediately before failure, player 0 had **Double Spell** in hand and
player 1's GY contained **Double Spell** and **Salvage**. The engine log showed a
hundreds-level recursive stack alternating through:

- `c24096228.lua` — Double Spell
  - `CheckActivateEffect`
  - `Duel.IsExistingTarget`
- `c96947648.lua` — Salvage target legality

The failure was therefore a deterministic script-legality recursion, not a
learning-policy/privacy error.

### Reviewed solver override

Added `solver/script_overrides/c24096228.lua`.

The override preserves the existing Double Spell cost/target/operation behavior
and adds a guard only while checking whether a GY Double Spell is itself a usable
Double Spell target. This breaks cyclic legality probing while still allowing a
GY Double Spell to be considered when a real non-cyclic downstream Spell is
available.

`reborn/ocgcore.py` resolves scripts in this order:
1. reviewed solver override
2. pinned CardScripts root
3. pinned CardScripts `official/`

The dependency pin itself remains unchanged. Current Project Ignis master was
checked and still contains the recursive implementation, so merely advancing the
CardScripts checkout would not have removed this exact blocker.

### Post-fix reproducer

Run #60's deterministic reproducer completed with:
- status stored by the diagnostic as `unexpected_completion` (meaning the old
  expected crash did **not** occur)
- process calls: **2,625**
- blocker: none

The original held-out evaluator then completed all requested games, which is the
real regression gate.

### Numbering observation

A temporary apparent mapping discrepancy was resolved. The public share file is
alphabetically numbered, while the solver's canonical `MASTER.txt` is in the
reconstructed/video order used to generate `reborn-####` IDs. Candidate IDs must
be interpreted against solver MASTER, not against the public alphabetical line
number. In solver MASTER, `reborn-0529` is Double Spell, so the failing candidate
legitimately contained the card. This observation does **not** establish a new
engine-mapping problem.

## First valid frozen held-out pilot-skill evaluation

Purpose: isolate pilot quality from deck quality.

Training:
- **16/16** games completed
- four generated training candidates:
  - `160dbfa8dc27352a`
  - `977eddb411cb6266`
  - `0bfbdae3659b6159`
  - `22af860e3c963100`
- seeds begin at `11000`
- learned decisions: **15,425**
- fallback decisions: **843**
- frozen policy weights: **891**

Held-out evaluation:
- mirror candidates:
  - `6bcc971e0d0af3ef`
  - `593df70fb35282f5`
- different/disjoint seeds beginning at `21000`
- two paired seeds per mirror deck
- learned pilot swapped between seat 0 and seat 1
- **8/8 completed**, **0 blocked**
- policy remained frozen
- safe observation checks: **10,402**
- filtered policy-prompt checks: **10,402**
- learned pilot: **2 wins, 6 losses, 0 draws**
- raw held-out win rate vs zero-prior stochastic legal pilot: **25%**
- Wilson 95% lower bound: ~**7.15%**

Held-out decision coverage:
- chain 7,176
- idle 1,897
- select place 463
- battle 412
- select card 303
- select/unselect 62
- tribute 58
- position 14
- effect yes/no 9
- option 4
- yes/no 4

### What the held-out result means

This is the first clean **pilot-skill** measurement, and it is a negative result
for `sparse_softmax_reinforce_v1`. On this small held-out mirror test the learned
pilot performed worse than the zero-prior stochastic legal baseline.

Therefore the present policy is **not qualified to rank decks**. Do not convert
the 2-6 result into any statement about the two mirror decks, and do not start a
certified deck payoff matrix with this policy.

The correct next goal is to improve the pilot and repeat disjoint paired-seat
mirror evaluation until improvement is repeatable.

## Invalidated historical run

Run **#31** (`run_id=34069085396`) must still never be reused as successful duel
or learning evidence. Its GitHub job was green while stochastic/learning reports
were 0/8 because a filtered prompt was routed to a pilot path expecting an
observation. That routing bug was fixed and later probes hard-fail on incomplete
batches.

## Engine/text audit remains independent

Current standing audit:
- Reborn pool: **2,273** exact titles
- mapped engine IDs: **2,251**
- unmapped/name mismatches: **22**
- exact official/engine text equality: **1,938**
- non-exact comparisons requiring audit: **313**
- Red-Eyes Darkness Metal Dragon strict latest-errata script-path blocker remains

A successful duel does not certify every card effect. Do not silently use
historical/pre-errata scripts. Double Spell should remain in the reviewed
latest-text behavior audit because the current override intentionally fixes the
recursion only; it does not by itself certify every Double Spell edge case.

## Rules profile

Profile `reborn` is user-confirmed as matching YGO Reborn:
- 8,000 LP
- opening hand 5
- draw 1 normally
- no first-turn draw
- current/MR5-style field rules represented by the pinned core flags
- current TCG SEGOC flags used by the project

Latest official card text/errata remains a separate binding requirement.

## Next work

1. Improve pilot skill before deck ranking.
2. Safely enumerate complex action sets currently handled by random fallback:
   multi-card selection, tribute combinations, counters, sums, place decisions
   and select/unselect sequences.
3. Improve zero-prior credit assignment/state representation, then repeat frozen
   held-out paired-seat mirror tests on disjoint seeds.
4. Continue the 22-name/313-text/latest-errata audit, including REDMD and Double
   Spell behavior.
5. Add Extra Deck generation/optimization.
6. Only after pilot competence and errata/interaction coverage are strong enough,
   create certified paired-seat payoff data and begin adversarial best-response /
   double-oracle deck search.
