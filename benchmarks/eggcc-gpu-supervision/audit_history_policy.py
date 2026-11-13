"""Frozen validation interventions separating source policy from fitted weights."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
import mlx.core as mx
from audit_training_expansion import verified, summarize
from collect_observed_corpus import read_bytes
from packed_cell_replay import executor, prepare
from token_eq_readout import examples, readout_rows, materialize, expand_scores, check_partition
from select_eq_readout import gpu_read


def partition_checks(rows, scores):
    checks = []; offset = 0
    for row in rows:
        count = len(row['quotient']['representatives'])
        full = expand_scores(row, scores[offset:offset+count], True, True)
        checks.append(check_partition(row['pairs'], row['y'], full)); offset += count
    if offset != len(scores):
        raise ValueError('query alignment mismatch')
    return checks


def categories(left, right):
    if len(left) != len(right):
        raise ValueError('population mismatch')
    result = []
    for i, (a, b) in enumerate(zip(left, right)):
        if not np.array_equal(a['target'], b['target']):
            raise ValueError('target mismatch')
        ea = a['edges']; eb = b['edges']
        direct = len(ea) != len(eb) or any(x != y or not np.array_equal(u,v) for (x,u),(y,v) in zip(ea,eb))
        ra = a.get('edge_routes', []); rb = b.get('edge_routes', [])
        direct = direct or len(ra) != len(rb) or any(not np.array_equal(x,y) for x,y in zip(ra,rb))
        sources = [s for n in (a,b) for s,_ in n['edges']]
        if any(s >= i for s in sources):
            raise ValueError('noncausal route')
        result.append('direct' if direct else 'descendant' if any(result[s] != 'unchanged' for s in sources) else 'unchanged')
    return result


def compare(rows, before, after, groups):
    if len(rows) != len(before) or len(rows) != len(after):
        raise ValueError('comparison population mismatch')
    out = defaultdict(Counter); rules = defaultdict(Counter)
    for row, old, new in zip(rows, before, after):
        if not row['pairs']:
            continue
        key = ('both_exact' if old['exact'] and new['exact'] else
               'lost_exact' if old['exact'] else 'gained_exact' if new['exact'] else 'both_wrong')
        out[groups[row['index']]][key] += 1
        rules[str(row['rule'])][key] += 1
    return dict(by_route={k:dict(v) for k,v in out.items()}, by_rule={k:dict(v) for k,v in rules.items()})


def main():
    p = argparse.ArgumentParser()
    for name in ('validation','baseline','candidate','readout','output'):
        p.add_argument(name, type=Path)
    a = p.parse_args(); manifest_raw = a.validation.read_bytes(); manifest = json.loads(manifest_raw)
    if manifest['partition'] != 'validation':
        raise ValueError('validation only')
    models = {}; reports = {}
    for name, path in [('latest',a.baseline),('earliest',a.candidate)]:
        reports[name] = json.loads(path.with_suffix('.json').read_text())
        models[name] = verified(path,reports[name],'model_sha256')
        if reports[name]['provenance']['corpus_manifest'] != manifest['manifest_sha256']:
            raise ValueError('corpus mismatch')
    if reports['latest']['provenance'] != reports['earliest']['provenance']:
        raise ValueError('fitting provenance mismatch')
    if not np.array_equal(models['latest']['w'],models['earliest']['w']):
        raise ValueError('feature map mismatch')
    dr = json.loads(a.readout.with_suffix('.json').read_text())
    if dr['provenance']['validation'] != hashlib.sha256(manifest_raw).hexdigest() or dr['model_sha256'] != reports['latest']['model_sha256']:
        raise ValueError('decoder provenance mismatch')
    decoder = verified(a.readout,dr,'weights_sha256')
    alpha = dr['selected']['mse']; column = list(decoder['alphas']).index(alpha)
    coef = decoder['coef'][:,column:column+1]
    if not mx.metal.is_available():
        raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu); cases = []
    for entry in manifest['cases']:
        if entry['status'] != 'complete':
            continue
        raw = read_bytes(Path(entry['trace']))
        if entry['split'] != 'validation' or hashlib.sha256(raw).hexdigest() != entry['trace_sha256']:
            raise ValueError('case provenance mismatch')
        trace = json.loads(raw); datasets = {}; allrows = {}
        for name, model in models.items():
            datasets[name], allrows[name] = examples(trace,int(model['channels']),bool(model['zero_role_channels']),True,str(model['encoding']))
        rows = allrows['latest']
        if [(r['index'],r['run'],r['rule']) for r in rows] != [(r['index'],r['run'],r['rule']) for r in allrows['earliest']]:
            raise ValueError('row mismatch')
        groups = categories(datasets['latest'], datasets['earliest'])
        checks = {}; metrics = {}; numeric = {}
        for route, nodes in datasets.items():
            plan = prepare(nodes,'two')
            for weights, model in models.items():
                name = route+'_routes_'+weights+'_weights'
                tokens = np.array(executor(nodes,model['w'],model['coef'],plan,True)())
                matrix,_ = materialize(readout_rows(rows,True),tokens,decoder['w'],True)
                scores,numeric[name] = gpu_read(matrix,coef,strict=False)
                checks[name] = partition_checks(rows,scores[:,0]); metrics[name] = summarize(rows,scores[:,0])
        reference = checks['latest_routes_latest_weights']
        cases.append(dict(case=entry['case'],trace_sha256=entry['trace_sha256'],metrics=metrics,numeric=numeric,
            changes={name:compare(rows,reference,items,groups) for name,items in checks.items() if name!='latest_routes_latest_weights'}))
    result = dict(scope='Standalone frozen validation interventions, not deployment selection',cases=cases,alpha=alpha,
        validation_sha256=hashlib.sha256(manifest_raw).hexdigest(),models={k:r['model_sha256'] for k,r in reports.items()},
        decoder_sha256=dr['weights_sha256'],refitting=False,union_authorized=False,
        limitations=['Swapped routes and weights are distribution-shift diagnostics, not fitted alternatives',
                     'Changed prediction is not proof of missing semantic information',
                     'Observed CPU routes and input observations still required',
                     'Eq partition audit does not certify lifecycle, scalars, or autonomous saturation'])
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    if not all(n['passed'] and not n['threshold_disagreements'] for c in cases for n in c['numeric'].values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
