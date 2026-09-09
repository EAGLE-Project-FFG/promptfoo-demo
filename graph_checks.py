"""Compare a constructed graph with a reference graph. No model-based grading.

Each assertion names its reference file in the promptfooconfig.yaml `config` block,
so the same two functions can be pointed at different references.
"""

import json
from pathlib import Path

HERE = Path(__file__).parent


def _compare(output, context, key, fields):
    reference = json.loads((HERE / context['config']['reference']).read_text())
    try:
        graph = json.loads(output) if isinstance(output, str) else output
        actual = {tuple(item[f] for f in fields) for item in graph[key]}
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return {'pass': False, 'score': 0, 'reason': f'Cannot read {key} from the output: {exc}'}

    expected = {tuple(item[f] for f in fields) for item in reference[key]}
    tp, fp, fn = len(actual & expected), len(actual - expected), len(expected - actual)
    f1 = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 1.0
    return {
        'pass': actual == expected,
        'score': f1,
        'reason': f'TP={tp} FP={fp} FN={fn} F1={f1:.2f}; '
                  f'missing={sorted(expected - actual)}; extra={sorted(actual - expected)}',
    }


def check_nodes(output, context):
    return _compare(output, context, 'nodes', ('id', 'type', 'name'))


def check_edges(output, context):
    return _compare(output, context, 'edges', ('source', 'relation', 'target'))
