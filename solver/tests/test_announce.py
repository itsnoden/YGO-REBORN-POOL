import sqlite3
import tempfile
import unittest

from reborn.announce import (
    declarable, enumerate_declarable, choose_declarable,
    OPCODE_ISCODE, OPCODE_ISTYPE, OPCODE_ISSETCARD,
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

    def test_enumerates_complete_allowed_database_subset(self):
        with tempfile.NamedTemporaryFile(suffix='.cdb') as tmp:
            con = sqlite3.connect(tmp.name)
            con.execute('CREATE TABLE datas (id INTEGER, alias INTEGER, setcode INTEGER, type INTEGER, attribute INTEGER, race INTEGER)')
            con.executemany(
                'INSERT INTO datas VALUES (?,?,?,?,?,?)',
                [
                    (123, 0, 0, 0x21, 0x20, 0x2),
                    (456, 0, 0, 0x1, 0x10, 0x1),
                    (789, 0, 0, 0x21, 0x20, 0x4),
                ],
            )
            con.commit(); con.close()
            # 789 exists in the database but is intentionally outside the
            # supplied Reborn mapping and must never enter the legal choice set.
            legal = enumerate_declarable(tmp.name, [0x20, OPCODE_ISTYPE], [456, 123, 999])
            self.assertEqual(legal, [123])
            self.assertEqual(choose_declarable(tmp.name, [0x20, OPCODE_ISTYPE], [456, 123, 999]), 123)


if __name__ == '__main__':
    unittest.main()
