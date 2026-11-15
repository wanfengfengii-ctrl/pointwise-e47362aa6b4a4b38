"""Tests: ``python3 -m unittest discover -s tests`` (stdlib only)."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paretolayers import layers, layers_with_stats  # noqa: E402
from paretolayers.cli import brute_layers, _dominates  # noqa: E402


class SpecificationTests(unittest.TestCase):
    def test_given_example(self):
        self.assertEqual(
            layers([(1, 1, 1), (1, 1, 1), (2, 1, 1), (1, 2, 0)]),
            [0, 0, 1, 0],
        )

    def test_empty(self):
        self.assertEqual(layers([]), [])
        self.assertEqual(layers_with_stats([])[0], [])

    def test_single(self):
        self.assertEqual(layers([(0, 0, 0)]), [0])
        self.assertEqual(layers([(-7, 3, 2)]), [0])

    def test_duplicates_share_layer_and_are_kept(self):
        self.assertEqual(
            layers([(5, 5, 5), (5, 5, 5), (4, 4, 4), (5, 5, 5)]),
            [1, 1, 0, 1],
        )

    def test_input_not_mutated(self):
        records = [(3, 1, 2), (3, 1, 2), (0, 5, 5)]
        snapshot = list(records)
        layers(records)
        self.assertEqual(records, snapshot)

    def test_list_form_records(self):
        self.assertEqual(
            layers([[1, 2, 3], [1, 2, 3], [2, 2, 3]]),
            [0, 0, 1],
        )

    def test_mixed_list_and_tuple_records_rejected(self):
        # The contract supplies homogeneous triples; mixing types would make
        # the lexicographic sort ambiguous, so this must fail loudly rather
        # than silently mislayer.
        with self.assertRaises(TypeError):
            layers([(1, 2, 3), [1, 2, 3], (2, 2, 3)])

    def test_large_magnitudes(self):
        big = 10 ** 30
        self.assertEqual(
            layers([(big, -big, 0), (big, -big, 0), (big + 1, -big, 0)]),
            [0, 0, 1],
        )
        self.assertEqual(
            layers([(-big, big, 0), (-big, big - 1, -1)]),
            [1, 0],
        )


class StructuralTests(unittest.TestCase):
    def test_full_chain(self):
        chain = [(i, i, i) for i in range(20)]
        self.assertEqual(layers(chain), list(range(20)))

    def test_full_chain_reversed(self):
        chain = [(19 - i, 19 - i, 19 - i) for i in range(20)]
        self.assertEqual(layers(chain), list(range(19, -1, -1)))

    def test_antichain(self):
        self.assertEqual(layers([(i, 19 - i, 0) for i in range(20)]), [0] * 20)

    def test_negative_coordinates(self):
        self.assertEqual(
            layers([(-5, -5, -5), (-1, -1, -1), (-3, -3, -3), (-9, 0, 0)]),
            [0, 2, 1, 0],
        )

    def test_single_coordinate_equality_still_dominates(self):
        self.assertEqual(
            layers([(0, 3, 0), (1, 3, 1), (2, 3, 2), (3, 3, 3)]),
            [0, 1, 2, 3],
        )

    def test_reorder_is_equivariant(self):
        records = [(3, 0, 9), (0, 0, 0), (3, 0, 9), (2, 5, -1), (0, 0, 1)]
        base = layers(records)
        order = [4, 2, 0, 3, 1]
        shuffled = [records[i] for i in order]
        self.assertEqual(layers(shuffled), [base[i] for i in order])


class ReferenceTests(unittest.TestCase):
    def test_exhaustive_three_records(self):
        grid = [(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1)
                for z in (-1, 0, 1)]
        for a in grid:
            for b in grid:
                for c in grid:
                    records = [a, b, c]
                    self.assertEqual(layers(records), brute_layers(records),
                                     records)

    def test_randomized_matches_pairwise_reference(self):
        rng = random.Random(424242)
        for _ in range(200):
            n = rng.randrange(1, 9)
            records = [(rng.randint(-2, 2), rng.randint(-2, 2),
                        rng.randint(-2, 2)) for _ in range(n)]
            self.assertEqual(layers(records), brute_layers(records), records)

    def test_dominance_helper_matches_definition(self):
        self.assertTrue(_dominates((0, 0, 0), (0, 0, 1)))
        self.assertFalse(_dominates((0, 0, 0), (0, 0, 0)))
        self.assertFalse(_dominates((0, 0, 1), (0, 0, 0)))


class StatsTests(unittest.TestCase):
    def test_stats_shape(self):
        result, stats = layers_with_stats([(0, 0, 0), (1, 1, 1), (1, 1, 1)])
        self.assertEqual(result, [0, 1, 1])
        for key in ("records", "groups", "query_steps", "update_steps",
                    "update_writes", "bisects", "index_cells"):
            self.assertIn(key, stats)
        self.assertEqual(stats["groups"], 2)

    def test_no_pairs(self):
        # 10k records must not do ~10^8 pair comparisons: index steps stay
        # within a generous log^2-shaped budget.
        rng = random.Random(7)
        records = [(rng.randrange(10 ** 6), rng.randrange(10 ** 6),
                    rng.randrange(10 ** 6)) for _ in range(10000)]
        _, stats = layers_with_stats(records)
        self.assertLess(stats["query_steps"] + stats["update_steps"], 10 ** 6)


if __name__ == "__main__":
    unittest.main()
