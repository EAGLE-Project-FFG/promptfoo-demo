"""Checks that the ground-truth comparison behaves as intended, without an API call."""
import copy
import json
import unittest

import graph_checks as checks

CORRECT = {'config': {'reference': 'data/demo_ground_truth.json'}}
TYPO = {'config': {'reference': 'data/demo_ground_truth_typo.json'}}


class GraphComparisonTest(unittest.TestCase):
    def setUp(self):
        self.graph = json.loads((checks.HERE / 'data/demo_ground_truth.json').read_text())

    def test_reference_passes_regardless_of_order(self):
        self.graph['nodes'].reverse()
        self.graph['edges'].reverse()
        for check in (checks.check_nodes, checks.check_edges):
            self.assertEqual(check(json.dumps(self.graph), CORRECT)['score'], 1)
            self.assertTrue(check(self.graph, CORRECT)['pass'])

    def test_missing_edge_reduces_recall(self):
        self.graph['edges'].pop()
        result = checks.check_edges(self.graph, CORRECT)
        self.assertFalse(result['pass'])
        self.assertAlmostEqual(result['score'], 8 / 9)
        self.assertIn('FP=0 FN=1', result['reason'])

    def test_invented_edge_reduces_precision(self):
        extra = copy.deepcopy(self.graph['edges'][0])
        extra['target'] = 'component:39'
        self.graph['edges'].append(extra)
        result = checks.check_edges(self.graph, CORRECT)
        self.assertFalse(result['pass'])
        self.assertAlmostEqual(result['score'], 10 / 11)

    def test_typo_in_the_reference_fails_a_correct_graph(self):
        """The failing test case in promptfooconfig.yaml, reproduced offline."""
        nodes = checks.check_nodes(self.graph, TYPO)
        self.assertFalse(nodes['pass'])
        self.assertAlmostEqual(nodes['score'], 12 / 14)
        self.assertIn('MSSQL BD', nodes['reason'])
        # Edges reference IDs only, so a misspelled name leaves them untouched.
        self.assertTrue(checks.check_edges(self.graph, TYPO)['pass'])

    def test_unusable_output_fails_without_crashing(self):
        for output in ('not json', 'null', '', {}, {'nodes': [], 'edges': []}, [1, 2]):
            for check in (checks.check_nodes, checks.check_edges):
                with self.subTest(output=output, check=check.__name__):
                    self.assertFalse(check(output, CORRECT)['pass'])


if __name__ == '__main__':
    unittest.main()
