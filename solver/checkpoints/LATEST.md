# Checkpoint 0004 — 2026-09-06/07

Status: complete-duel protocol/observation coverage is live-verified under the
user-confirmed YGO Reborn rules profile, and the first zero-prior learning smoke
completes full games and updates a policy. **No strongest deck has been
established yet.**

Read the full checkpoint at `checkpoints/0004.md` and the durable duel findings at
`reports/DUEL_OBSERVATIONS.md` before continuing.

## Current verified milestone

GitHub Actions `Solver Verify` run **#42** (`run_id=34070493121`) rebuilt the exact
pinned engine dependencies and passed all strict gates:

- **41/41 unit tests passed**
- conservative correctness: **8/8 games**, **2,983 decisions**, with a filtered
  observation and filtered prompt audit on all 2,983 decisions
- paired stochastic coverage: **8/8 games**, **8,096 decisions**, with all 8,096
  observation/prompt audits passing
- zero-prior learning smoke: **8/8 games**, **9,132 decisions**, **8,634 learned
  decisions**, **498 legality-fallback decisions**, **1,463 nonzero weights**

Pinned dependency heads:

- core `b8c05dff14da0b13608950a73906287dc0b601f9`
- scripts `49b0af044cebcb92f3f23211ef436971e1fc16fb`
- database `9d7f8da324417ec7913b47c52273906c9ae3333b`

Artifact id: `10000303579`; digest:
`sha256:a96eecb6fcb7ad80ec242395993a43a0d47fba91b0b19aaf31b3f1f583a73c38`.

## Rules/profile authority

The solver now uses `reborn` by default. The user confirmed the implemented
current-TCG/MR5-style profile matches YGO Reborn: 8,000 LP, 5-card opening hand,
normal draw 1, no first-turn draw, and the current pinned-core field/TCG SEGOC
flags already used by the project.

Latest official card text/errata remains a separate binding requirement and must
always be used.

## Important invalidated evidence

Do **not** reuse run #31 (`run_id=34069085396`) as a successful result. Its GitHub
job was green but stochastic/learning reports were 0/8 because filtered prompt
objects were routed into a pilot path expecting viewer observations. That bug is
fixed, regression-tested and strict probes now fail CI if requested games do not
all complete. Run #42 is the post-fix replacement.

## Engine/text audit still open

- exact Reborn pool: 2,273 titles
- engine mapped: 2,251
- engine-name mismatches: 22
- mapped scripts: 1,880
- scriptless Normal Monsters: 370
- strict missing-script effect card: Red-Eyes Darkness Metal Dragon
- exact official/engine text matches: 1,938
- non-exact text comparisons to audit: 313

Do not silently fall back to historical/pre-errata scripts.

## Evidence boundary

The completed games establish engine/protocol/privacy/learning data flow, **not
deck strength**. Stochastic winners and learning-smoke winners are debug-only.
There is still no certified deck win-rate table, no certified payoff matrix, no
validated strongest pilot and no #1 deck.

## Resume

1. Build **frozen-policy held-out evaluation**: train on one seed set, freeze,
   evaluate against the zero-prior stochastic baseline on disjoint seeds with
   paired seats. This measures pilot skill only.
2. Improve the pilot if it does not show held-out improvement; do not promote
   weak self-play results into deck rankings.
3. Add safe learned action enumeration for complex fallback decisions.
4. Reconcile the 22 engine-name mismatches, 313 text differences and the
   Red-Eyes Darkness Metal Dragon latest-errata script-path blocker.
5. Add Extra Deck construction/optimization.
6. Once pilot skill and interaction coverage are sufficient, create certified
   paired-seat payoff data for adversarial best-response/double-oracle deck search.
7. Preserve the project constraints: exact 2,273-card pool, Reborn banlist,
   actual rules, latest errata always, and no human/community/metagame priors.
