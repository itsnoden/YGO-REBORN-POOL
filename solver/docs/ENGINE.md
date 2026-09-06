# Existing engine integration

Selected upstreams:

- https://github.com/edo9300/ygopro-core — standalone C++ state machine, C API,
  card-script interpreter. Built locally and verified with API 11.0.
- https://github.com/ProjectIgnis/CardScripts — canonical Lua effects and helpers.
- https://github.com/ProjectIgnis/BabelCDB — simulator card IDs and numeric data.

Only simulator implementations and card data were inspected. No pretrained
pilots, community decks, strategy statistics or metagame priors were imported.
The core and scripts are AGPL-3.0-or-later; keep upstream copyright and license
notices. Dependencies are fetched at pinned commits, not vendored without notices.
The new solver integration code is also AGPL-3.0-or-later (see LICENSE).

## Rebuild from a fresh checkout

From `solver/` with Python and g++ available:

```
pip install -r requirements.txt
python -m reborn.bootstrap_engine
python -m reborn.build_core --core vendor/core --output build --jobs 2
python -m reborn.engine_bridge --database vendor/database/cards.cdb --scripts vendor/scripts --core vendor/core
python -m reborn.mine
python -m reborn.search --seed 20260906 --population 256
python -m reborn.smoke_engine --library build/libocgcore.so --database vendor/database/cards.cdb --scripts vendor/scripts --count 8
python -m unittest discover -s tests -v
```

Lua's exact submodule commit is fixed by the core commit. `build_core` mirrors
the upstream premake source exclusions and C++ compilation of Lua. The compiled
binary is rebuildable; machine-specific objects are not committed.

## Working now

- Native library compilation; data/script/log callback wiring; ABI version gate.
- Main Deck validation before candidate integration tests, including shared-name
  limits; strict upstream-ID mapping and an EDOPro whitelist file.
- Real engine card initialization, opening draws and first decision request.
- Eight different generated deck proposals reached a decision with no core
  script errors. This is **zero completed duels**, and conveys no win-rate data.
- Privileged message framing and response transport. Raw messages are not an
  agent observation: they may expose hidden information.
- Strict parsers/response encoders now cover `SELECT_IDLECMD`, `SELECT_BATTLECMD`,
  effect yes/no, yes/no, option, card selection, chain selection, place/disabled
  field selection and position selection against the pinned core binary layout.
- Decision ownership is enforced: only the acting player can materialize a policy
  view of a parsed decision. Raw referee messages remain outside policy input.
- `reborn.flow_probe` now drives candidate pairs forward with a deterministic,
  conservative legal-action baseline and stops on unsupported prompts instead of
  guessing. This probe exists only to establish protocol/game-flow coverage and
  MUST NOT be used as deck strength evidence.

## Complete-duel flow probe

After rebuilding the pinned engine dependencies, run:

```
python -m reborn.flow_probe --library build/libocgcore.so --database vendor/database/cards.cdb --scripts vendor/scripts --count 8
```

The output is saved to `reports/flow_probe.json`. Any unsupported decision type,
core retry, missing script, nonterminal engine stop or step-budget overflow is a
hard blocker. Do not convert blocked games into losses or discard them silently.
The deterministic baseline intentionally prefers passing/ending phases where
legal; even completed games from this probe are protocol tests, not win-rate data.

## Next implementation work

1. Reconcile 32 official-name mismatches and 22 engine-ID mismatches using card
   identity evidence. Retain original MASTER names and reviewed aliases separately.
2. Audit 313 non-exact official/engine text comparisons: many may be formatting
   or terminology, but no semantic equivalence is assumed. 1,938 mapped cards
   have exact whitespace-normalized official text equality.
3. Run `flow_probe` against the pinned binary and implement remaining decision
   messages in blocker-frequency order. Unsupported prompts must abort and be
   logged, never become guessed moves. Add protocol regression tests for every
   new message family before enabling it in self-play.
4. Add public-state querying/observation construction beyond decision ownership:
   own hand, public zones, revealed cards, LP/phase/turn/chain state, while masking
   opponent hand/deck identities and facedown information not legally known.
5. Build a baseline legal pilot, paired-seat complete-duel tests and replay logs,
   then information-set planning and independent held-out pilot evaluation.
6. Connect certified payoff data to the double-oracle callback orchestration.
   Restricted-game mixture solving and learned best responses are not yet built.

## Errata-specific finding

Folder names are not a sufficient proof of current errata. At the pinned script
commit, Red-Eyes Darkness Metal Dragon's standard code 88264978 exists under
`pre-errata/` but its header says "errata, OCG" and contains named count limits;
`official/c88264988.lua` explicitly says "pre-errata". Our current strict reader
blocks the missing standard official-path script. Resolve this using an explicit
reviewed mapping and behavioral tests against official card ID 7557; never
enable all historical scripts as a fallback. This is a tracked blocker, not a
reason to drop the card from full-pool consideration.

## Rules profile

The integration smoke tests use an explicitly labelled current-TCG experimental
profile with 8,000 LP and five opening cards. They do not establish Reborn's
turn-one draw, priority or field-spell behavior. Latest card errata is fixed by
the user; rules-profile differences still require validation or separate runs.
