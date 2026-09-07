# YGO Reborn independent solver

Research objective: discover the strongest legal deck under the exact 2,273-card
YGO Reborn pool, Reborn banlist, actual Yu-Gi-Oh rules and **latest official
English TCG errata**. This is an incremental research engine, not a solved format.

The duel backend is the existing **EDOPro/ocgcore**, not a hand-written duel
simulator. Its C++ core, Project Ignis scripts and BabelCDB database are pinned in
`engine.lock.json`. Our code owns pool/banlist enforcement, latest-text audits,
candidate search, privacy-safe observations, pilot training/evaluation and
experiment evidence gates.

The solver now defaults to the user-confirmed `reborn` gameplay profile: 8,000 LP,
5-card opening hand, draw 1, no first-turn draw, and the current pinned-core
MR5/TCG mechanics already used by the project. Gameplay-rule confirmation is
separate from the requirement to use **latest errata always**.

## Resume first

Read these before changing search or interpreting duel results:

- `checkpoints/LATEST.md`
- `reports/DUEL_OBSERVATIONS.md`
- `docs/ARCHITECTURE.md`
- `docs/ENGINE.md`

Checkpoint 0004 records the first strict complete-duel + privacy-safe learning
milestone. Preserve prior experiments and their invalidation notes.

## Reproduce core data/search

Python 3.11+, `pip install -r requirements.txt`, then from `solver/`:

```
python -m reborn.import_pool
python -m reborn.official --workers 4
python -m reborn.mine
python -m reborn.search --seed 20260906 --population 256
python -m unittest discover -s tests -v
```

**Resume an interrupted official import with only the second command.** Completed
page checkpoints are reused; failed/missing pages are retried. Re-running pool
import resets the enriched database, so rerun official import afterward to join
saved batches. Use `--refresh` for a new official snapshot. Snapshot changes must
invalidate dependent effect certifications, replays and deck evaluations.

## Engine/pilot verification

After bootstrapping/building the exact pins described in `docs/ENGINE.md`, the
current verification layers are:

- `reborn.flow_probe` — conservative complete-duel/protocol/privacy correctness;
- `reborn.pilot_probe` — paired stochastic adversarial interaction coverage;
- `reborn.learn_probe` — zero-prior complete-game learning smoke;
- `reborn.pilot_eval` — train/freeze/held-out mirror-deck pilot-skill evaluation.

The first three are **not deck-strength experiments**. Their winners are debug
fields only. `pilot_eval` measures pilot quality only because both seats use the
same deck during evaluation.

## Sources and separation

`data/raw/MASTER.txt` defines membership; `BANLIST_MASTER.txt` defines limits.
`DECKBUILDING_FINDINGS_MASTER.txt` is an archived historical handoff. Its human
deck rankings, outside metagame information and earlier proxy estimates are NOT
read by candidate generation or fitness code. No tournament decklists, historical
decks, Reddit, tier lists or community strategy priors may guide the independent
search. Simulator/card data may implement rules/effects only.

The pool includes Extra Deck cards. They cannot occupy a Main Deck slot. Extra
Deck construction/optimization remains a separate pending search dimension. No
side deck or outside opponent distribution is assumed.

## Honesty gates

Pattern mining returns hypotheses, not proven combinations. Generated decks are
legal proposals, not recommendations. Complete engine games establish only the
evidence level explicitly named by the experiment: protocol correctness,
interaction coverage, learning data flow, pilot skill, or (later) certified deck
payoffs.

Do not promote correctness/stochastic/learning-smoke winners into deck win rates.
Do not use a pilot for deck ranking until it demonstrates held-out skill. Do not
feed payoffs to the double oracle until the participating interactions and latest
errata are sufficiently audited. No global optimality claim is possible from
finite self-play; report empirical bounds over tested populations and continually
seek adversarial counterexamples.
