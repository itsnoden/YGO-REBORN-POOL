# Checkpoint 0003 — 2026-09-06

Status: first strict legal-action protocol layer implemented and published; a
complete-duel correctness probe now exists. No strongest deck has been established.

## New work in this checkpoint

- Added `reborn/protocol.py`, derived from the exact pinned ygopro-core protocol
  layout at core commit `b8c05dff14da0b13608950a73906287dc0b601f9`.
- Implemented strict parser/response support for:
  - `MSG_SELECT_IDLECMD`
  - `MSG_SELECT_BATTLECMD`
  - `MSG_SELECT_EFFECTYN`
  - `MSG_SELECT_YESNO`
  - `MSG_SELECT_OPTION`
  - `MSG_SELECT_CARD`
  - `MSG_SELECT_CHAIN`
  - `MSG_SELECT_PLACE`
  - `MSG_SELECT_DISFIELD`
  - `MSG_SELECT_POSITION`
- Added legal response encoders for command choices, card-index selections and
  field-zone selections. Invalid counts, indices, duplicate selections and
  forbidden zones raise instead of being guessed.
- Added an explicit privacy boundary: parsed decision views can only be
  materialized for the player who owns the prompt. Raw engine messages remain
  privileged referee data and are not policy observations.
- Added `tests/test_protocol.py`. The six focused protocol tests passed in the
  implementation workspace before publication.
- Added `reborn/flow_probe.py`, which advances generated candidate pairs using a
  deterministic conservative legal-action baseline. It stops on unsupported
  prompts, missing scripts, retries or nonterminal unexplained engine stops.
- Updated `docs/ENGINE.md` with the new rebuild/probe path and strict rules for
  interpreting its output.

## Important evidence boundary

`flow_probe` is **not a deck-strength evaluator**. The baseline intentionally
prefers passing/ending phases and exists only to discover protocol and engine
coverage blockers. Even a completed duel from this probe is not a certified
win-rate sample and must not feed deck ranking, mutation selection, the oracle,
or any search prior.

No complete duel from the pinned engine has been recorded in the repository yet,
because the live pinned dependency rebuild/probe has not been executed after this
code publication. Therefore there are still **zero certified completed duels,
zero certified win rates and no #1 deck**.

## Resume

1. Rebuild the exact pinned core/scripts/database from `engine.lock.json`.
2. Run `python -m unittest discover -s tests -v` and then `reborn.flow_probe`.
3. Inspect the first unsupported prompt family in `reports/flow_probe.json` and
   implement it from pinned core source, with regression tests, before proceeding.
4. Continue until diverse candidate pairs can complete full games without retry,
   unsupported-prompt, script or hidden-information failures.
5. Add public-state querying/observation filtering beyond prompt ownership before
   any learned or search pilot can consume duel state.
6. Only after that, build paired-seat pilots, adversarial self-play, held-out
   evaluation and certified payoff matrices for the double-oracle search.

The existing source constraints remain unchanged: use only the exact 2,273-card
Reborn pool, Reborn banlist, actual Yu-Gi-Oh rules and latest official errata.
Simulator code/card data may implement those rules/effects; do not use tournament
decks, historical decklists, Reddit, tier lists, community strategy priors or
outside metagame data.
