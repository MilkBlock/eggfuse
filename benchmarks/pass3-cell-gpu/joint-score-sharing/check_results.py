import json
from pathlib import Path
from statistics import median


def check(root):
    for filename,expected in [('results.json',16),('header-results.json',8)]:
        groups=json.loads((root/filename).read_bytes());assert len(groups)==expected
        for k,v in groups.items():
            arms=v['arms'];ident=v['hashes']
            assert all(len(h)==64 for key,h in ident.items() if key!='child_gate')
            base=arms['off'];assert base['model_evaluations']==base['model_requests'] and base['cache_hits']==0
            for arm,x in arms.items():
                assert len(x['ms'])==len(x['request_ms'])==8 and median(x['ms'])==x['median_ms']
                if arm=='exact':continue
                assert x['rhs']==base['rhs'] and x['neural_rhs']==base['neural_rhs']
                assert x['direct']==base['direct'] and x['fresh_cells']==base['fresh_cells']
                assert x['model_requests']==x['model_evaluations']+x['cache_hits']==base['model_requests']
                assert x['single_raw_discrete_hash']==ident['offers']
                if arm in ('full-key','static','static-stale','header-stale'):assert x['model_evaluations']<base['model_evaluations']
            if k.endswith('/certified'):
                assert arms['static-stale']['max_hash_entries']==0
                if 'header-stale' in arms:assert arms['header-stale']['header_only_reads']>0
    print('Verified full-pass scores, source ordinals, directly named physical ids and eight interleaved timings.')


if __name__=='__main__':check(Path(__file__).resolve().parent)
