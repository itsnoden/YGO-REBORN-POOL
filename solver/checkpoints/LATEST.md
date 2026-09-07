# Checkpoint 0006 — 2026-09-07

Status: mapping coverage has improved substantially and the broader pilot benchmark exposed a generalization failure that prevents deck-ranking certification. **No strongest deck has been established yet.**

Read the full checkpoint at `checkpoints/0006.md` and the governing project rules at `../YGO_REBORN_AI_DECKBUILDING_RULES.txt` / repository-root `YGO_REBORN_AI_DECKBUILDING_RULES.txt` before continuing.

## Canonical verified state

GitHub Actions `Solver Verify` run **#116** (`run_id=34100241620`) on commit
`62cd69512f30624f42110662ad6f00f075fc3458` passed the complete pipeline.

Artifact id: `10010439569`
Digest: `sha256:ff61c657040016d6b3fc5ea528448bba4ecc6b45d347264dcf344bcaaeb1748e`

## Engine coverage

- exact Reborn pool: **2,273**
- mapped: **2,269**
- unmapped: **4**
- exact-title mappings: 2,251
- reviewed identity aliases: 18
- exact official/engine text equality: 1,938
- non-exact text comparisons still requiring audit: 331
- missing required script among mapped cards: 0

Remaining unresolved cards: `Level Down!`, `Long Nose`, `Red-Eyes Black Chick`, `Worm Warrior`. Do not fuzzy-map them. Long Nose and Red-Eyes Black Chick are explicitly protected from collapsing into separate pool cards Great Long Nose and Black Dragon's Chick; Level Down! must not be substituted with Level Down!?.

## Pilot benchmark

6-block held-out benchmark: **144/144 completed**, zero policy fallbacks.

Learned pilot vs stochastic-legal mirror baseline:
- **76 wins / 60 losses / 8 draws**
- raw wins/completed: 52.78%
- Wilson 95% lower: 44.66%

Per-block: 15-9, 17-7, 15-9, 7-9-8, 13-11, 9-15.

The first three blocks were 47-25, but the three newly added blocks were only **29-35-8**. Therefore the earlier ~65% result did not generalize. **Pilot is still not certified for deck ranking.**

Counterfactual treatment also failed its held-out A/B: control 17-15 vs treatment 13-19 (-12.5 percentage points). Do not promote it.

## Next experiment

Current terminal REINFORCE uses `1/sqrt(episode decisions)` per-decision scaling, so longer/chain-heavy games still receive greater total update magnitude. Test an equal-total-credit-per-duel normalization (`~1/episode decisions`) against the current learner with identical decks, seeds, features, actions and evaluation protocol. Add no human strategy priors. Promote only if held-out generalization improves.

## Resume

1. Preserve `YGO_REBORN_AI_DECKBUILDING_RULES.txt`: no tournament/community/historical-meta strategy priors.
2. Resolve the final 4 mapping blockers from identity evidence only.
3. Continue the 331-text/latest-errata audit.
4. Run the controlled episode-credit-normalization A/B.
5. Improve pilot generalization before any deck ranking.
6. Add Extra Deck generation/optimization.
7. Only then produce certified paired-seat payoff matrices and adversarial/double-oracle deck search.
8. Never claim a strongest deck prematurely.
