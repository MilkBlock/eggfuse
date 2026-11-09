#!/usr/bin/env python3
"""Classify saved sum-bits choice differences without executing a workload.

This is the semantic acceptance entrypoint for the documented final-state
contract. The strict whole-graph audit remains a separate determinism check.
The only term identities used here are the source's existing Add and Mul
commutativity rules. Cost equality alone is not accepted as term equivalence.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from audit import UnresolvedState, equivalent, key, load

TERM_SORTS = {'Term', 'ListTerm', 'TermAndCost',
              '___PotentialExtractedExprSort', '___ExtractedExprCacheSort'}
# Bind the accepted proof rules to the baseline source program that was
# actually inspected. A new source/workload needs a reviewed contract, not a
# successful comparison under accidentally matching constructor names.
SOURCE_CORE_SHA256 = '17d851c513fa8f8cd3a64b007823b8364e6e65112a7816126aa1eb00024bddb5'


class Inconclusive(Exception):
    """The current proof rules do not cover this input or difference."""


def mapped(v, mapping):
    if isinstance(v, dict):
        if 'eq' in v:
            return json.loads(mapping[key(v)])
        return {k: mapped(x, mapping) for k, x in v.items()}
    if isinstance(v, list):
        return [mapped(x, mapping) for x in v]
    return v


def normalize_commutative(tree):
    if not isinstance(tree, list):
        return tree
    tree = [normalize_commutative(x) for x in tree]
    if len(tree) >= 2 and tree[0] == 'TermBop' and tree[1] in (['Add'], ['Mul']):
        assert len(tree) == 4
        tree[2:] = sorted(tree[2:], key=key)
    return tree


class Terms:
    def __init__(self, state, constructors):
        self.by_value = {}
        self.candidates = {}
        self.selected = {}
        for r in state['rows']:
            if r['table'] in constructors and r['table'] != 'Smaller':
                self.by_value.setdefault(key(r['values'][-1]), []).append(r)
            if r['table'] == 'PotentialExtractedExpr':
                if r['subsumed']:
                    raise Inconclusive('hidden candidates need another proof')
                self.candidates.setdefault(key(r['values'][0]), set()).add(key(r['values'][1]))
            if r['table'] == 'ExtractedExpr':
                self.selected[key(r['values'][0])] = r['values'][1]

    def render(self, v, seen=frozenset()):
        if 'eq' not in v:
            return v['value']
        k = key(v)
        if k in seen:
            raise Inconclusive('cyclic term requires another proof')
        rows = self.by_value.get(k, [])
        if len(rows) != 1:
            raise Inconclusive('missing or ambiguous term constructor requires another proof')
        r = rows[0]
        return [r['table'], *(self.render(x, seen | {k}) for x in r['values'][:-1])]

    def validate_selected(self):
        for expr, tc in self.selected.items():
            candidates = self.candidates[expr]
            assert key(tc) in candidates, 'selected term is not a candidate'
            pair = self.render(tc)
            assert pair[0] == 'TCPair', 'selected value is not a term/cost pair'
            assert pair[-1] == min(self.render(json.loads(c))[-1] for c in candidates), 'selected cost is not a current minimum'
        return len(self.selected)


def validate_hoist(state):
    """Check the actual source LHS, including the maximum-size condition."""
    rows = lambda table: [r['values'] for r in state['rows'] if r['table'] == table and not r['subsumed']]
    inv = {(key(r[0]), key(r[1])) for r in rows('is-inv-Expr')}
    loops = {(key(r[0]), key(r[1])) for r in rows('DoWhile')}
    bases = {key(r[-1]) for r in rows('Base')}
    typed = {key(r[0]) for r in rows('HasType') if key(r[1]) in bases}
    sizes = {key(r[0]): r[1]['value'] for r in rows('Expr-size')}
    maxima = {(key(r[0]), key(r[1])): r[2]['value'] for r in rows('to-hoist-size')}
    chosen = {}
    for inputs, body, expr in rows('to-hoist'):
        ib = key(inputs), key(body)
        assert ib in loops and (key(body), key(expr)) in inv and key(expr) in typed
        candidates = [e for b, e in inv if b == key(body) and e in typed and e in sizes]
        assert sizes[key(expr)] == maxima[ib] == max(sizes[e] for e in candidates)
        chosen[key([inputs, body])] = {'expr': expr, 'size': sizes[key(expr)], 'candidates': len(candidates)}
    return chosen


def diagnose(left, right, schemas):
    core = {t['name'] for t in schemas if not t['name'].startswith('CellSpine')
            and t['name'] != 'to-hoist' and not any(s['name'] in TERM_SORTS for s in t['schema'])}
    mapping = {}
    proof = equivalent(left, right, core, False, mapping)
    constructors = {t['name'] for t in schemas if t['kind'] == 'constructor'}
    lt, rt = Terms(left, constructors), Terms(right, constructors)
    if not lt.selected or not rt.selected:
        raise Inconclusive('missing final extraction results')
    def inventory(terms, translate):
        return {key([translate(json.loads(expr)), normalize_commutative(terms.render(json.loads(tc)))])
                for expr, candidates in terms.candidates.items() for tc in candidates}
    left_candidates = inventory(lt, lambda v: mapped(v, mapping))
    right_candidates = inventory(rt, lambda v: v)
    candidates = {'normalized_candidates': len(left_candidates),
                  'normalization': 'existing Add/Mul commutativity only; per Expr and cost',
                  'left_raw_candidates': sum(map(len, lt.candidates.values())),
                  'right_raw_candidates': sum(map(len, rt.candidates.values())),
                  'equal_sets': True}
    n = lt.validate_selected()
    assert n == rt.validate_selected()
    differences = []
    for expr, tc in lt.selected.items():
        rhs = rt.selected[key(mapped(json.loads(expr), mapping))]
        a, b = lt.render(tc), rt.render(rhs)
        assert a[-1] == b[-1], 'selected costs differ'
        if normalize_commutative(a) != normalize_commutative(b):
            raise Inconclusive('selected terms need identities beyond the supported proof')
        if a != b:
            differences.append({'left_expr': json.loads(expr), 'right_expr': mapped(json.loads(expr), mapping),
                                'left_term_and_cost': a, 'right_term_and_cost': b})
    if left_candidates != right_candidates:
        raise Inconclusive('candidate sets differ under supported Add/Mul identities')
    lh, rh = validate_hoist(left), validate_hoist(right)
    assert len(lh) == len(rh)
    changed = []
    for ib, item in lh.items():
        other = rh[key(mapped(json.loads(ib), mapping))]
        assert item['size'] == other['size']
        if mapped(item['expr'], mapping) != other['expr']:
            changed.append({'left': item, 'right': other})
    return {'core': {**proof, 'tables': len(core), 'includes_Expr_equality_and_visibility': True},
            'candidate_inventory_modulo_Add_Mul': candidates, 'selected_expressions': n,
            'all_selected_candidates_are_current_minima': True, 'selected_cost_differences': 0,
            'selected_term_differences': len(differences), 'all_explained_by_existing_Add_Mul_commutativity': True,
            'first_term_difference': differences[:1], 'hoist_choices': len(lh), 'hoist_differences': changed,
            'limits': 'Final saved sum-bits states only. No complete cross-engine per-Run or generated-code execution proof. Smaller, caches, TermSubst and marker history are not claimed identical.'}


def check_pair(left, right, schemas):
    try:
        if not __debug__:
            raise Inconclusive('run without python -O; assertions are part of the validator')
        declarations = {t['name']: t['schema'] for t in schemas}
        for state in (left, right):
            if not state['rows']:
                raise Inconclusive('empty export does not establish the final-state contract')
            for row in state['rows']:
                if row['table'].startswith('CellSpine'):
                    continue  # Compiler-internal marker history is outside this contract.
                columns = declarations.get(row['table'])
                if columns is None or len(columns) != len(row['values']) or any(
                        v['sort'] != c['name'] for v, c in zip(row['values'], columns)):
                    raise Inconclusive('unknown table or incompatible row schema: ' + row['table'])
        return {'status': 'pass', 'proof': diagnose(left, right, schemas)}
    except (Inconclusive, UnresolvedState, KeyError, TypeError, ValueError, RecursionError) as error:
        return {'status': 'inconclusive', 'reason': str(error)}
    except AssertionError as error:
        return {'status': 'difference', 'reason': str(error) or 'a semantic acceptance condition failed'}


def main(root, output):
    files = {'native_source': 'native-source.json', 'native_legacy': 'native-legacy.json',
             'native_values': 'native-values.json', 'cpu_legacy': 'run-legacy/state.json', 'cpu_values': 'run-values/state.json'}
    result = {'schema': 'eggfuse-choice-semantic-check/v1',
              'scope': 'documented sum-bits final-state contract; no workload rerun or timing',
              'strict_graph_equality': 'separate determinism diagnostic; not the semantic acceptance criterion',
              'comparisons': {}}
    try:
        states = {k: load(root / p) for k, p in files.items()}
        core = load(root / 'sum-legacy/program.json')['source_core']
        source_hash = hashlib.sha256(key(core).encode()).hexdigest()
        result['baseline_source_core_sha256'] = source_hash
        if source_hash != SOURCE_CORE_SHA256:
            raise Inconclusive('baseline source is outside the reviewed semantic contract')
        schemas = core['tables']
        result['input_sha256'] = {k: hashlib.sha256((root / p).read_bytes()).hexdigest() for k, p in files.items()}
        if not __debug__:
            raise Inconclusive('run without python -O; assertions are part of the validator')
        for a, b in [('native_source', 'native_legacy'), ('native_legacy', 'cpu_legacy'),
                     ('native_legacy', 'native_values'), ('cpu_legacy', 'cpu_values')]:
            result['comparisons'][a + '_vs_' + b] = check_pair(states[a], states[b], schemas)
        statuses = [r['status'] for r in result['comparisons'].values()]
        result['status'] = 'difference' if 'difference' in statuses else 'inconclusive' if 'inconclusive' in statuses else 'pass'
    except (Inconclusive, OSError, KeyError, TypeError, ValueError) as error:
        result.update(status='inconclusive', reason=str(error))
    output.write_text(json.dumps(result, indent=2) + '\n')
    for name, r in result['comparisons'].items():
        print(name, r['status'], r.get('reason', ''))
    print('semantic status:', result['status'])
    return {'pass': 0, 'difference': 1, 'inconclusive': 2}[result['status']]


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    sys.exit(main(args.root, args.output))
