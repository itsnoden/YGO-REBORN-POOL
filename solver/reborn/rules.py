"""Explicit ocgcore rules profiles; no profile is silently called 'Reborn'.

Values mirror the exact pinned ygopro-core ocgapi_constants.h.  The currently
used profile is an experimental MR5/TCG profile pending Reborn-format rule
certification. Latest card errata is a separate user-fixed requirement.
"""

DUEL_OCG_OBSOLETE_IGNITION = 0x100
DUEL_1ST_TURN_DRAW = 0x200
DUEL_1_FACEUP_FIELD = 0x400
DUEL_PZONE = 0x800
DUEL_SEPARATE_PZONE = 0x1000
DUEL_EMZONE = 0x2000
DUEL_FSX_MMZONE = 0x4000
DUEL_TRAP_MONSTERS_NOT_USE_ZONE = 0x8000
DUEL_RETURN_TO_DECK_TRIGGERS = 0x10000
DUEL_TRIGGER_ONLY_IN_LOCATION = 0x20000
DUEL_SPSUMMON_ONCE_OLD_NEGATE = 0x40000
DUEL_CANNOT_SUMMON_OATH_OLD = 0x80000
DUEL_TCG_SEGOC_NONPUBLIC = 0x100000000
DUEL_TCG_SEGOC_FIRSTTRIGGER = 0x200000000
DUEL_TCG_FAST_EFFECT_IGNITION = 0x400000000

DUEL_MODE_MR1 = (
    DUEL_OCG_OBSOLETE_IGNITION | DUEL_1ST_TURN_DRAW | DUEL_1_FACEUP_FIELD |
    DUEL_SPSUMMON_ONCE_OLD_NEGATE | DUEL_RETURN_TO_DECK_TRIGGERS |
    DUEL_CANNOT_SUMMON_OATH_OLD
)
DUEL_MODE_MR2 = (
    DUEL_1ST_TURN_DRAW | DUEL_1_FACEUP_FIELD | DUEL_SPSUMMON_ONCE_OLD_NEGATE |
    DUEL_RETURN_TO_DECK_TRIGGERS | DUEL_CANNOT_SUMMON_OATH_OLD
)
DUEL_MODE_MR5 = (
    DUEL_PZONE | DUEL_EMZONE | DUEL_FSX_MMZONE |
    DUEL_TRAP_MONSTERS_NOT_USE_ZONE | DUEL_TRIGGER_ONLY_IN_LOCATION
)

# This exactly equals the flags already used by Duel.__init__ before this module
# was introduced. It remains explicitly experimental until the format's rule era
# is certified; do not rename it to REBORN_FLAGS without evidence.
EXPERIMENTAL_CURRENT_TCG_FLAGS = (
    DUEL_MODE_MR5 | DUEL_TCG_SEGOC_NONPUBLIC | DUEL_TCG_SEGOC_FIRSTTRIGGER
)

PROFILES = {
    'experimental_current_tcg': {
        'flags': EXPERIMENTAL_CURRENT_TCG_FLAGS,
        'starting_lp': 8000,
        'opening_hand': 5,
        'draw_per_turn': 1,
        'first_turn_draw': False,
        'certified_for_reborn': False,
    },
    'mr1_reference': {
        'flags': DUEL_MODE_MR1,
        'starting_lp': 8000,
        'opening_hand': 5,
        'draw_per_turn': 1,
        'first_turn_draw': True,
        'certified_for_reborn': False,
    },
    'mr2_reference': {
        'flags': DUEL_MODE_MR2,
        'starting_lp': 8000,
        'opening_hand': 5,
        'draw_per_turn': 1,
        'first_turn_draw': True,
        'certified_for_reborn': False,
    },
}


def get_profile(name):
    if name not in PROFILES:
        raise KeyError(f'unknown rules profile: {name}')
    return dict(PROFILES[name])
