# YGO Reborn independent solver

Research objective: strongest legal 40-card Main Deck under the exact 2,273-card
pool, Reborn banlist, and **latest official English TCG errata** (user directive
2026-09-06). This is an incremental research engine, not a solved format.

The duel backend is now the existing **EDOPro/ocgcore**, not a hand-written duel
simulator. Its C++ core and Project Ignis Lua scripts are pinned in
`engine.lock.json`. Our code owns pool/banlist enforcement, official-text audits,
candidate search, experiment records and the headless adapter. See
`docs/ENGINE.md` for setup and actual integration-test coverage.

## Reproduce and resume

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

Read `checkpoints/LATEST.md` and `docs/ARCHITECTURE.md` before continuing. Preserve
all prior experiments. Do not infer a winner from proxy synergy scores. A card
with unsupported semantics is an implementation task, never a zero-power card.

## Sources and separation

`data/raw/MASTER.txt` defines membership; `BANLIST_MASTER.txt` defines limits.
`DECKBUILDING_FINDINGS_MASTER.txt` is an archived historical handoff. Its human
deck rankings, outside metagame information and earlier proxy estimates are NOT
read by candidate generation or fitness code. No decklists or community sources
are consulted. Only official `card_search.action` text pages feed enrichment;
ordinary TCG banlist icons on those pages are ignored.

The pool includes cards belonging in the Extra Deck. They cannot occupy a Main
Deck slot. Extra Deck construction/optimization is a separate pending dimension.
No side deck or outside opponent distribution is assumed.

## Honesty gates

Full text retrieval is not full effect implementation. Pattern mining returns
hypotheses, not proven combinations. Generated decks are legal proposals, not
recommendations. All duel-based metrics remain null until certified rules and
effects support every participating card and interaction. No global optimality
claim is possible from finite self-play; report empirical bounds over the tested
population and continually seek adversarial counterexamples.
