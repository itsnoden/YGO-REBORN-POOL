import unittest

from reborn.announce import (
    declarable, OPCODE_ISCODE, OPCODE_ISTYPE, OPCODE_ISSETCARD,
    OPCODE_AND, OPCODE_ALLOW_ALIASES, OPCODE_ALLOW_TOKENS,
    TYPE_MONSTER, TYPE_TOKEN,
)


class AnnounceTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            'id': 123,
            'alias': 0,
            'setcode': 0x00100020,
            'type': 0x21,
            'attribute': 0x20,
            'race': 0x2,
        }

    def test_iscode_type_and_boolean_expression(self):
        self.assertTrue(declarable(self.row, [123, OPCODE_ISCODE]))
        self.assertFalse(declarable(self.row, [456, OPCODE_ISCODE]))
        self.assertTrue(declarable(self.row, [0x20, OPCODE_ISTYPE]))
        ops = [123, OPCODE_ISCODE, 0x20, OPCODE_ISTYPE, OPCODE_AND]
        self.assertTrue(declarable(self.row, ops))

    def test_alias_and_token_gates(self):
        alias = {**self.row, 'alias': 999}
        self.assertFalse(declarable(alias, [123, OPCODE_ISCODE]))
        self.assertTrue(declarable(alias, [123, OPCODE_ISCODE, OPCODE_ALLOW_ALIASES]))
        token = {**self.row, 'type': TYPE_MONSTER | TYPE_TOKEN}
        self.assertFalse(declarable(token, [123, OPCODE_ISCODE]))
        self.assertTrue(declarable(token, [123, OPCODE_ISCODE, OPCODE_ALLOW_TOKENS]))

    def test_setcode(self):
        self.assertTrue(declarable(self.row, [0x20, OPCODE_ISSETCARD]))
        self.assertFalse(declarable(self.row, [0x30, OPCODE_ISSETCARD]))


if __name__ == '__main__':
    unittest.main()
