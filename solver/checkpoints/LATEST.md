# Checkpoint 0005 — 2026-09-06/07

Status: the first frozen-policy held-out pilot evaluation now completes cleanly
under the user-confirmed YGO Reborn rules profile. The deterministic Double Spell
stack-overflow blocker is fixed through a reviewed solver-side override. The
current sparse learner **is not strong enough to rank decks**. **No strongest
deck has been established yet.**

Read the full checkpoint at `checkpoints/0005.md` and the durable duel findings at
`reports/DUEL_OBSERVATIONS.md` before continuing.

## Canonical strict run

GitHub Actions `Solver Verify` run **#60** (`run_id=34072551222`) on commit
`599d96ae47aa4280df00afb49ca280491e8d0e52` passed the full pipeline.

- **44/44 unit tests passed**
- conservative correctness: **8/8**, **2,983** decisions with 2,983 safe
  observation/prompt audits
- stochastic coverage: **8/8**, **8,096** decisions with all privacy audits
- learning smoke: **8/8**, **8,634 learned decisions**, **498 fallbacks**,
  **1,463 nonzero weights**
- deterministic Double Spell reproducer: completed with no blocker after
  **2,625 process calls**
- held-out pilot evaluation: **8/8**, **10,402 privacy-checked decisions**,
  zero blockers, frozen policy unchanged

Artifact id: `10000962499`
Digest: `sha256:bf4dea9e46d381050f367d6e1b0237ade23b9ecfa705b911a2bc9f100322fa4b`

Pinned heads remain:
- core `b8c05dff14da0b13608950a73906287dc0b601f9`
- CardScripts `49b0af044cebcb92f3f23211ef436971e1fc16fb`
- BabelCDB `9d7f8da324417ec7913b47c52273906c9ae3333b`

## Double Spell blocker resolved

Previous held-out runs failed deterministically on candidate
`593df70fb35282f5`, seed `21101`, learned seat 1, with `C stack overflow`.
Detailed diagnostics isolated the recursion to `c24096228.lua` (**Double Spell**)
re-entering `CheckActivateEffect` while testing a GY Double Spell, with
`c96947648.lua` (**Salvage**) in the state.

Added `solver/script_overrides/c24096228.lua` with a narrow recursion guard and
changed `ocgcore.py` to prefer reviewed solver overrides before pinned upstream
scripts. Ordinary scripts still fall back to the exact pinned CardScripts tree.
Three regression tests cover override presence/precedence/fallback.

Do not treat this as blanket certification of every Double Spell edge case; its
latest-errata behavior remains part of the text/behavior audit.

## Held-out pilot result

Training: 16/16 games, four generated training candidates, 15,425 learned
choices, 843 fallbacks, 891 frozen weights.

Held-out mirror evaluation on different candidates/seeds with learned pilot
swapped between seats:
- **8/8 completed**
- learned pilot: **2 wins, 6 losses, 0 draws**
- raw held-out win rate vs zero-prior stochastic legal pilot: **25%**
- 10,402 observation checks / 10,402 policy-view checks

This is **pilot-skill evidence only** and it is a negative result for the current
learner. Do not use it as deck-strength evidence or feed it into candidate
ranking, payoff matrices, mutation fitness, or the double oracle.

## Engine/text audit still open

- exact Reborn pool: 2,273 titles
- engine mapped: 2,251
- engine-name mismatches/unmapped: 22
- exact official/engine text equality: 1,938
- non-exact text comparisons to audit: 313
- Red-Eyes Darkness Metal Dragon latest-errata script-path blocker remains
- never silently fall back to historical/pre-errata scripts

## Resume

1. Improve the pilot before any deck ranking. The current held-out score is 2-6
   versus the stochastic legal baseline.
2. Safely enumerate complex legal action sets so multi-card/tribute/counter/sum/
   place/select-unselect decisions can be learned instead of randomized fallback.
3. Improve zero-prior credit assignment/state representation and repeat frozen
   paired-seat held-out evaluation on disjoint seeds.
4. Continue the 22-name / 313-text / latest-errata audit, including REDMD and
   reviewed Double Spell semantics.
5. Add Extra Deck generation/optimization.
6. Only after pilot competence and errata/interaction gates are strong enough,
   generate certified paired-seat payoff data and run adversarial best-response /
   double-oracle deck search.
7. Preserve constraints: exact 2,273-card pool, Reborn banlist, certified Reborn
   rules, latest errata always, actual Yu-Gi-Oh rules, and no human/community/
   tournament/metagame priors.
