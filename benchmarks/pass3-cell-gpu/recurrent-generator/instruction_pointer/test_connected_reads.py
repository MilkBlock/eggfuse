import unittest

from catalog import Catalog


class ConnectedReadTests(unittest.TestCase):
    def test_only_static_wiring_changes_read_order(self):
        catalog = Catalog.__new__(Catalog)
        catalog.atoms = {0: range(5)}
        links = {frozenset(pair) for pair in [(0, 3), (2, 3), (1, 4)]}
        catalog.field_links = {
            (0, i, j): [(0, 0)] if frozenset((i, j)) in links else []
            for i in catalog.atoms[0] for j in catalog.atoms[0] if i != j
        }
        self.assertEqual(catalog.read_order(0, 0, 'connected'), (0, 3, 2, 1, 4))
        self.assertEqual(catalog.read_order(0, 3, 'connected'), (3, 0, 2, 1, 4))
        self.assertEqual(catalog.read_order(0, 3, 'source'), (3, 0, 1, 2, 4))
        for anchor in catalog.atoms[0]:
            order = catalog.read_order(0, anchor, 'connected')
            self.assertEqual(order[0], anchor)
            self.assertCountEqual(order, catalog.atoms[0])


if __name__ == '__main__':
    unittest.main()
