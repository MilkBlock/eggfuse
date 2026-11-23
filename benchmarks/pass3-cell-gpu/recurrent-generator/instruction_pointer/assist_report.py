"""Check matched full Pass timings and distinguish signed ownership from eliminated search."""
import argparse
import json
from pathlib import Path
from statistics import median


def load(path):
    return json.loads(path.read_bytes())


def summarize(folder, oracle_folder):
    out = {}
    for name in ('fact', 'loopfact', 'sum-divisors'):
        run = load(folder/(name+'.json'))
        oracle = load(oracle_folder/('oracle-'+name+'.json'))
        arms = ('exact','assist','oracle')
        if (run['spec']['binary'] != oracle['build_sha256']
            or run['spec']['program'] != oracle['program_sha256']
            or len(run['pairs']) != 4):
            raise ValueError('missing or unmatched full-workload comparisons')
        required = oracle['reference_commits']
        audit = run['audit']['assist']
        receipts = ('issued','accepted','duplicates','rejected','residual_commits',
                    'exact_candidates','exact_rows','skipped_rule_calls','exact_rule_calls')
        stamps = {a:[] for a in arms}
        wins = dict(assist_over_exact=0,oracle_over_exact=0)
        for i, pair in enumerate(run['pairs']):
            expected = arms if i%2==0 else tuple(reversed(arms))
            if tuple(r['arm'] for r in pair)!=expected:
                raise ValueError('timing order differs')
            indexed = {r['arm']:r for r in pair}
            for arm,r in indexed.items():
                if r['state_sha']!=oracle['state_sha'] or r['runs']!=oracle['source_runs_observed']:
                    raise ValueError('timed state differs from oracle')
                if arm=='assist':
                    if (r['accepted']+r['residual_commits'] != required
                        or r['issued'] != r['accepted']+r['duplicates']+sum(r['rejected'].values())
                        or any(r[k]!=audit[k] for k in receipts)):
                        raise ValueError('assist proposal or residual attribution changed')
                elif r['committed']!=required:
                    raise ValueError('source commits changed')
                stamps[arm].append(r)
            wins['assist_over_exact']+=indexed['assist']['wall']<indexed['exact']['wall']
            wins['oracle_over_exact']+=indexed['oracle']['wall']<indexed['exact']['wall']
        times = {a:{k:median(r[k] for r in stamps[a]) for k in ('wall','inference','verify','exact')}
                 for a in arms}
        for k in ('duplicate_seconds','rejected_seconds'):
            times['assist'][k]=median(r[k] for r in stamps['assist'])
        out[name]=dict(required=required,runs=oracle['source_runs_observed'],state_sha=oracle['state_sha'],
                       assist={k:audit[k] for k in (*receipts,'rejected_reads','duplicate_reads','reads')},
                       exact_residual_candidates=run['audit']['exact']['residual_candidates'],
                       median_seconds=times,paired_wins=wins,oracle_in_memory_ms=oracle['timing_ms'])
    return out


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('timings','oracle_folder','output'):ap.add_argument(k,type=Path)
    a=ap.parse_args()
    a.output.write_text(json.dumps(summarize(a.timings,a.oracle_folder),indent=2)+'\n')
