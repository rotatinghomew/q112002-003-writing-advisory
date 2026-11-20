import unittest

from record_reader import read_records


class RecordsTest(unittest.TestCase):
    def setUp(self):
        self.tables = read_records()

    def references(self, left, left_key, right, right_key):
        candidates = {row[right_key] for row in self.tables[right]}
        self.assertTrue(all(row[left_key] in candidates for row in self.tables[left]))

    def test_documents_reference_source_records(self):
        self.references('observations','activity','observation_map','activity')
        self.references('rulings','observation','observations','observation')
        self.references('appointments','session','workshops','session')
        self.references('prerequisites','required','goals','goal')
        self.references('seats','section','sections','section')
        self.references('adjustments','session','workshops','session')
        same = [row for row in self.tables['observations'] if row['occasion']=='c']
        self.assertEqual(len({row['activity'] for row in same}), 2)
        self.assertEqual(len({row['student'] for row in same}), 1)
        self.assertTrue(any(row['verified'] > row['day'] for row in self.tables['workshops']))
