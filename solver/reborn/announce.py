"""Database-backed evaluator for ocgcore MSG_ANNOUNCE_CARD expressions.

Mirrors field::is_declarable from the exact pinned ygopro-core commit. Candidate
codes are supplied by the Reborn pool mapping, so the correctness probe never
uses an outside card as a strategic choice merely because BabelCDB contains it.
"""
import sqlite3

OPCODE_ADD           = 0x4000000000000000
OPCODE_SUB           = 0x4000000100000000
OPCODE_MUL           = 0x4000000200000000
OPCODE_DIV           = 0x4000000300000000
OPCODE_AND           = 0x4000000400000000
OPCODE_OR            = 0x4000000500000000
OPCODE_NEG           = 0x4000000600000000
OPCODE_NOT           = 0x4000000700000000
OPCODE_BAND          = 0x4000000800000000
OPCODE_BOR           = 0x4000000900000000
OPCODE_BNOT          = 0x4000001000000000
OPCODE_BXOR          = 0x4000001100000000
OPCODE_LSHIFT        = 0x4000001200000000
OPCODE_RSHIFT        = 0x4000001300000000
OPCODE_ALLOW_ALIASES = 0x4000001400000000
OPCODE_ALLOW_TOKENS  = 0x4000001500000000
OPCODE_ISCODE        = 0x4000010000000000
OPCODE_ISSETCARD     = 0x4000010100000000
OPCODE_ISTYPE        = 0x4000010200000000
OPCODE_ISRACE        = 0x4000010300000000
OPCODE_ISATTRIBUTE   = 0x4000010400000000
OPCODE_GETCODE       = 0x4000010500000000
OPCODE_GETSETCARD    = 0x4000010600000000
OPCODE_GETTYPE       = 0x4000010700000000
OPCODE_GETRACE       = 0x4000010800000000
OPCODE_GETATTRIBUTE  = 0x4000010900000000

TYPE_MONSTER = 0x1
TYPE_TOKEN = 0x4000
CARD_MARINE_DOLPHIN = 78734254
CARD_TWINKLE_MOSS = 13857930


def _setcodes(value):
    value &= (1 << 64) - 1
    out = []
    while value:
        out.append(value & 0xffff)
        value >>= 16
    return out


def _cdiv(lhs, rhs):
    if rhs == 0:
        return None
    q = abs(lhs) // abs(rhs)
    return -q if (lhs < 0) ^ (rhs < 0) else q


def declarable(row, opcodes):
    """Return the pinned core's declarability result for one datas row."""
    stack = []
    allow_alias = False
    allow_token = False

    def binary(fn):
        if len(stack) >= 2:
            rhs = stack.pop(); lhs = stack.pop(); stack.append(fn(lhs, rhs))

    def unary(fn):
        if stack:
            stack.append(fn(stack.pop()))

    for opcode in opcodes:
        if opcode == OPCODE_ADD: binary(lambda a,b: a+b)
        elif opcode == OPCODE_SUB: binary(lambda a,b: a-b)
        elif opcode == OPCODE_MUL: binary(lambda a,b: a*b)
        elif opcode == OPCODE_DIV:
            if len(stack) >= 2:
                rhs = stack.pop(); lhs = stack.pop(); value = _cdiv(lhs, rhs)
                if value is None: return False
                stack.append(value)
        elif opcode == OPCODE_AND: binary(lambda a,b: int(bool(a) and bool(b)))
        elif opcode == OPCODE_OR: binary(lambda a,b: int(bool(a) or bool(b)))
        elif opcode == OPCODE_NEG: unary(lambda a: -a)
        elif opcode == OPCODE_NOT: unary(lambda a: int(not a))
        elif opcode == OPCODE_BAND: binary(lambda a,b: a & b)
        elif opcode == OPCODE_BOR: binary(lambda a,b: a | b)
        elif opcode == OPCODE_BXOR: binary(lambda a,b: a ^ b)
        elif opcode == OPCODE_BNOT: unary(lambda a: ~a)
        elif opcode == OPCODE_LSHIFT: binary(lambda a,b: a << b)
        elif opcode == OPCODE_RSHIFT: binary(lambda a,b: a >> b)
        elif opcode == OPCODE_ALLOW_ALIASES: allow_alias = True
        elif opcode == OPCODE_ALLOW_TOKENS: allow_token = True
        elif opcode == OPCODE_ISCODE: unary(lambda a: int(row['id'] == (a & 0xffffffff)))
        elif opcode == OPCODE_ISTYPE: unary(lambda a: row['type'] & a)
        elif opcode == OPCODE_ISRACE: unary(lambda a: row['race'] & a)
        elif opcode == OPCODE_ISATTRIBUTE: unary(lambda a: row['attribute'] & a)
        elif opcode == OPCODE_GETCODE: stack.append(row['id'])
        elif opcode == OPCODE_GETTYPE: stack.append(row['type'])
        elif opcode == OPCODE_GETRACE: stack.append(row['race'])
        elif opcode == OPCODE_GETATTRIBUTE: stack.append(row['attribute'])
        elif opcode == OPCODE_ISSETCARD:
            if stack:
                set_code = stack.pop()
                settype = set_code & 0xfff; setsubtype = set_code & 0xf000
                ok = any((sc & 0xfff) == settype and ((sc & 0xf000) & setsubtype) == setsubtype
                         for sc in _setcodes(row.get('setcode', 0)))
                stack.append(int(ok))
        else:
            # Mirrors the core: OPCODE_GETSETCARD currently falls through here.
            stack.append(opcode)

    if len(stack) != 1 or not stack[-1]:
        return False
    code = row['id']
    if code in (CARD_MARINE_DOLPHIN, CARD_TWINKLE_MOSS):
        return True
    alias_ok = allow_alias or not row.get('alias', 0)
    is_token = (row['type'] & (TYPE_MONSTER + TYPE_TOKEN)) == (TYPE_MONSTER + TYPE_TOKEN)
    return bool(alias_ok and (allow_token or not is_token))


def enumerate_declarable(database, opcodes, allowed_codes):
    """Return every legal declaration inside the mapped Reborn card pool.

    This is a legality oracle, not a strength prior.  Codes are sorted only for
    deterministic reproducibility; a learning or stochastic pilot may choose
    among the returned legal set without consulting human strategy.
    """
    allowed = sorted(set(int(c) for c in allowed_codes))
    if not allowed:
        raise ValueError('no allowed Reborn codes supplied')
    con = sqlite3.connect(database); con.row_factory = sqlite3.Row
    try:
        rows = {}
        for start in range(0, len(allowed), 900):
            batch = allowed[start:start+900]
            marks = ','.join('?' for _ in batch)
            for row in con.execute(f'SELECT id,alias,setcode,type,attribute,race FROM datas WHERE id IN ({marks})', batch):
                rows[row['id']] = dict(row)
    finally:
        con.close()
    legal = [code for code in allowed if code in rows and declarable(rows[code], opcodes)]
    if not legal:
        raise ValueError('no declarable card exists inside the mapped Reborn pool')
    return legal


def choose_declarable(database, opcodes, allowed_codes):
    """Return the lowest legal Reborn-mapped passcode accepted by the core.

    Kept for deterministic diagnostics.  Strategic pilots should use
    ``enumerate_declarable`` and choose from the complete legal set instead.
    """
    return enumerate_declarable(database, opcodes, allowed_codes)[0]
