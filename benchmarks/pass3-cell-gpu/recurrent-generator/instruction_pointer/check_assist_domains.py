"""Perturb signed requests on held programs and compare residual takeover to its baseline."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
from assist_domain_audit import audit
from alternate_proofs import digest


def check(root, baseline, treatment, issues):
    groups=defaultdict(Counter)
    records=json.loads((root/'manifest.json').read_bytes())
    if issues:
        known={r['directory'] for r in records}
        for stream in sorted(issues.glob('*-issues.json')):
            name=stream.name.removesuffix('-issues.json')
            if name not in known and (root/name/'capture.json').is_file():
                records.append(dict(directory=name, origin='eggcc', split='held_eggcc'))
    for record in records:
        split=record['split']
        folder=root/record['directory']
        if split in ('held_program','held_result_pc','held_merge'):
            full=json.loads((folder/'tape.json').read_bytes())['requests']
        elif issues and record['origin'] == 'eggcc' and split == 'held_eggcc':
            # Dropping a token from an Actor stream can also orphan later named ports.
            full=json.loads((issues/(folder.name+'-issues.json')).read_bytes())
            split=folder.name
        else:
            continue
        sparse=[req for i,req in enumerate(full) if i%3!=0]
        stale=[dict(req,parents=[dict(p,version=p['version']+1) for p in req['parents']]) for req in full]
        for trial,packets in [('complete',full),('holes',sparse),('wrong_versions',stale)]:
            old=audit(folder,baseline,packets,'audit')
            new=audit(folder,treatment,packets,'audit')
            if old['context']!=new['context'] or old['counts']!=new['counts']:
                raise ValueError('prefix changed after '+trial)
            a=new['assist']
            groups[split,trial].update(programs=1,issued=len(packets),verified=new['counts']['accepted'],
                rejected=sum(new['counts']['rejected'].values()),residual=a['residual_commits'],
                point_domain_skips=a['point_domain_skips'],delta_domain_skips=a['delta_domain_skips'])
    return dict(baseline=digest(baseline),treatment=digest(treatment),groups={f'{s}/{t}':v for (s,t),v in groups.items()})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','baseline','treatment','out'):p.add_argument(n,type=Path)
    p.add_argument('--issues',type=Path,help='directory containing live EggCC request streams')
    a=p.parse_args()
    a.out.write_text(json.dumps(check(a.root,a.baseline,a.treatment,a.issues),indent=2)+'\n')
