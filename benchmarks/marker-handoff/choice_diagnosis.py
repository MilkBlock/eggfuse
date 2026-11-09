#!/usr/bin/env python3
"""Classify saved sum-bits choice differences without executing a workload.

This supplements the strict whole-graph audit; it never changes its verdict.
The only term identities used here are the source's existing Add and Mul
commutativity rules. Cost equality alone is not accepted as term equivalence.
"""
import argparse
import hashlib
import json
from pathlib import Path
from audit import equivalent, key, load

TERM_SORTS = {'Term', 'ListTerm', 'TermAndCost',
              '___PotentialExtractedExprSort', '___ExtractedExprCacheSort'}


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
                assert not r['subsumed'], 'hidden candidates need another proof'
                self.candidates.setdefault(key(r['values'][0]), set()).add(key(r['values'][1]))
            if r['table'] == 'ExtractedExpr':
                self.selected[key(r['values'][0])] = r['values'][1]

    def render(self, v, seen=frozenset()):
        if 'eq' not in v:
            return v['value']
        k = key(v)
        assert k not in seen, 'cyclic term requires another proof'
        rows = self.by_value.get(k, [])
        assert len(rows) == 1, 'ambiguous term constructor requires another proof'
        r = rows[0]
        return [r['table'], *(self.render(x, seen | {k}) for x in r['values'][:-1])]

    def validate_selected(self):
        for expr, tc in self.selected.items():
            candidates = self.candidates[expr]
            assert key(tc) in candidates, 'selected term is not a candidate'
            pair = self.render(tc)
            assert pair[0] == 'TCPair'
            assert pair[-1] == min(self.render(json.loads(c))[-1] for c in candidates)
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
    def inventory(terms, translate):
        return {key([translate(json.loads(expr)), normalize_commutative(terms.render(json.loads(tc)))])
                for expr, candidates in terms.candidates.items() for tc in candidates}
    left_candidates = inventory(lt, lambda v: mapped(v, mapping))
    right_candidates = inventory(rt, lambda v: v)
    assert left_candidates == right_candidates, 'normalized candidate sets differ'
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
        assert normalize_commutative(a) == normalize_commutative(b), 'not explained by Add/Mul commutativity'
        if a != b:
            differences.append({'left_expr': json.loads(expr), 'right_expr': mapped(json.loads(expr), mapping),
                                'left_term_and_cost': a, 'right_term_and_cost': b})
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


def main(root, output):
    files = {'native_source': 'native-source.json', 'native_legacy': 'native-legacy.json',
             'native_values': 'native-values.json', 'cpu_legacy': 'run-legacy/state.json', 'cpu_values': 'run-values/state.json'}
    states = {k: load(root / p) for k, p in files.items()}
    schemas = load(root / 'sum-legacy/program.json')['source_core']['tables']
    result = {'scope': 'diagnosis of saved states; no workload rerun or timing',
              'input_sha256': {k: hashlib.sha256((root / p).read_bytes()).hexdigest() for k, p in files.items()},
              'comparisons': {}}
    for a, b in [('native_source', 'native_legacy'), ('native_legacy', 'cpu_legacy'),
                 ('native_legacy', 'native_values'), ('cpu_legacy', 'cpu_values')]:
        result['comparisons'][a + '_vs_' + b] = diagnose(states[a], states[b], schemas)
    output.write_text(json.dumps(result, indent=2) + '\n')
    for name, r in result['comparisons'].items():
        print(name, 'core rows:', r['core']['rows'], 'term choices changed:', r['selected_term_differences'],
              'cost differences:', r['selected_cost_differences'], 'hoist choices changed:', len(r['hoist_differences']))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    main(args.root, args.output)
