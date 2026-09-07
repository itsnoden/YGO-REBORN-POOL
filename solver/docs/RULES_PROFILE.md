# YGO Reborn rules-profile status

This file separates **card text/errata** from **gameplay rules era**.

The user has fixed card text to **latest official errata ALWAYS**. That does not,
by itself, determine whether YGO Reborn uses a first-turn draw, old ignition
priority, one shared face-up Field Spell, modern monster zones, or another rules
profile. Those mechanics are controlled independently by ocgcore duel flags.

## Current experimental engine profile

The solver currently runs `experimental_current_tcg`, defined in
`reborn/rules.py`. Its numeric flag mask is `12885092352` and is exactly:

- `DUEL_MODE_MR5`
  - Pendulum-zone support
  - Extra Monster Zones
  - Fusion/Synchro/Xyz Main-Monster-Zone behavior
  - modern Trap Monster zone behavior
  - trigger-only-in-location behavior
- `DUEL_TCG_SEGOC_NONPUBLIC`
- `DUEL_TCG_SEGOC_FIRSTTRIGGER`

The duel constructor uses 8,000 LP, a five-card opening hand and one draw per
turn. `DUEL_1ST_TURN_DRAW` is **not** enabled, so the player taking the first turn
does not receive a normal draw under this experimental profile.

This profile is rebuildable and is now named explicitly instead of being a magic
integer inside the ctypes bridge.

## What this does NOT prove

Successful complete duels under this profile do **not** establish that it is the
authoritative YGO Reborn rules profile. In particular, the project has not yet
certified Reborn's:

- first-turn draw behavior;
- historical ignition-effect priority behavior;
- Field Spell coexistence/replacement rule;
- exact Master Rule / field-zone era;
- any format-specific rule override not encoded by the card pool or banlist.

Therefore all current duel, stochastic-pilot and learning reports retain the
label `experimental_current_tcg_not_reborn_confirmed` and must not be used as
certified deck-strength evidence.

## Reference profiles

`reborn/rules.py` also records MR1 and MR2 reference flag masks from the exact
pinned ocgcore constants. They exist for controlled sensitivity testing, not
because either has been selected as Reborn's rules.

## Certification gate

Before the solver publishes a certified #1 deck, one of the following must be
true:

1. authoritative Reborn rules documentation identifies the intended gameplay
   rules profile; or
2. the relevant rule choices are independently verified and encoded as a named
   `reborn_*` profile with regression tests.

Until then, pilot development and engine/protocol coverage can continue, but
payoff matrices remain experimental rather than certified.
