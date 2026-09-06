# Checkpoint 0002 — 2026-09-06

Status: pool imported; first official-text pass complete; existing EDOPro engine
compiled and connected; candidate generation and initial-state tests complete.

- 2,273 unique confirmed titles imported with contiguous source indexes.
- Copy-limit counts: 34 forbidden; 45 limited; 11 semi-limited; 2,183 unrestricted.
- Ceasefire and Cyber-Stein appear on the banlist but are absent from MASTER.
  Do not insert them into the pool.
- User explicitly requires latest official errata ALWAYS, superseding historical
  uncertainty in the archived deckbuilding findings.
- All 140 official-page batches saved. 2,241 official matches, 32 unresolved names.
- All 2,239 legal pool cards accounted for: 2,207 text-screened, 32 missing text.
- 256 proposals across full-pool coverage restarts, graph beam seeds, random
  restarts, one/two-card mutation and genetic proxy selection. All 2,121 currently
  verified legal Main Deck cards occur in the proposal population. Extra Deck
  construction is not optimized yet; missing identities stay queued.
- 2,251 engine-ID matches: 1,880 Lua scripts found, 370 scriptless Normal Monsters,
  one explicitly blocked missing-path effect script. 22 unresolved engine names.
- EDOPro core compiled successfully. Eight generated candidates reached the
  first real engine decision without script errors. 11 unit tests pass.
- No complete duels, win rates, certified combinations or #1 deck yet. The
  double-oracle loop has orchestration/gates only, not a trained best-response AI.
- Shared-name copy limit added after integration exposed aliases such as the
  Harpie Lady variants. Candidates regenerated with that legality check.
- Latest-errata script-path anomaly for Red-Eyes Darkness Metal Dragon is recorded
  in `docs/ENGINE.md`; do not quietly load a pre-errata implementation.
- Public upload of this checkpoint, including MASTER, banlist and saved findings,
  was explicitly approved by the user. GitHub is the canonical resume location.
  Earlier upload failures and already-staged blobs are recorded for historical
  reference in reports/publication_pending.json; no further approval is needed.


Resume: read `docs/ENGINE.md`. Rebuild pinned dependencies, then implement legal
action parsing/encoding and hidden-information filtering. Reconcile missing names
and text discrepancies. The official importer reuses completed page checkpoints;
use `--refresh` only when intentionally taking a new snapshot. Save separate
experiment directories before replacing generated outputs in future runs.

Do not use the archived findings' decklists, rankings or proxy win rates as
search priors. Do not describe text coverage as effect implementation coverage.
