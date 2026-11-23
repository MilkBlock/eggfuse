"""Validate the three treatment ledgers and archive the matched one-batch comparison."""
import argparse
import csv
import json
from pathlib import Path

from mixed_results import exclusive


def read(p):
    return json.loads(p.read_bytes())


def archive(root,out):
    arms=('named','renamed','structural')
    out.mkdir(exist_ok=True,parents=True)
    results={}
    counts=[]
    trajectories={}
    receiver=None
    for mode in arms:
        path=root/mode
        tr=read(path/'training.json')
        recall=read(path/'live/summary.json')
        ex=read(path/'exclusive.json')
        held=read(path/'held.json')
        fixed=read(path/'held-fixed.json')
        oracle=read(path/'run79.json')
        common_cut=read(path/'fixed.json')
        probes=[read(path/(tag+'-probe.json')) for tag in ('plain','rename')]
        if receiver is None: receiver=recall['receiver_sha256']
        if (tr['mode']!=mode or recall['mode']!='shadow' or ex['mode']!='exclusive' or
            recall['wave_limit']!=1 or ex['wave_limit']!=1 or
            any(e['receiver_sha256']!=receiver for e in [recall,oracle,common_cut,*probes]) or
            ex['verifier_sha256']!=receiver or any(e['build_sha256']!=receiver for e in (held,fixed)) or
            any(e['weights_sha256']!=tr['weights_sha256'] for e in [recall,ex,oracle,common_cut,*probes]) or
            fixed['checkpoint_sha256']!=tr['weights_sha256'] or fixed['thresholds']!=[0.,0.,0.] or
            common_cut['thresholds']!=[0.,0.,0.]):
            raise ValueError('treatment mismatch')
        counts.append((tr['seed'],tr['steps'],tr['training_runs'],tr['calibration_runs'],tr['counts']))
        splits={}
        for k,x in held['splits'].items():
            f=fixed['splits'][k]
            if (x['programs']!=48 or f['programs']!=48 or
                    [c['case'] for c in x['exclusive']['cases']]!=[c['case'] for c in f['exclusive']['cases']]):
                raise ValueError('different held programs')
            splits[k]=dict(calibrated=exclusive(x['exclusive']['cases']),fixed=exclusive(f['exclusive']['cases']))
        changed={}
        for n,case in probes[0]['cases'].items():
            changed[n]={k:case[k]['requests_sha256']!=probes[1]['cases'][n][k]['requests_sha256']
                        for k in ('shadow','given_anchors')}
            if mode=='structural' and any(changed[n].values()):
                raise ValueError('structural issuance changed under renaming')
        results[mode]=dict(training=tr,one_batch=recall['cases'],exclusive=ex['cases'],synthetic=splits,
                           run79=oracle['cases']['loopfact'],fixed_run79=common_cut['cases']['loopfact'],
                           name_intervention_changed_requests=changed,trained_declaration_ties=read(path/'symmetry.json'))
        for name in ('fact','loopfact','sum-divisors'):
            with (path/'live'/(name+'.csv')).open() as f: rows=list(csv.DictReader(f))
            case=recall['cases'][name]
            if sum(int(r['recovered']) for r in rows)!=case['recovered'] or case['decode_endings']!={'single_batch':len(rows)}:
                raise ValueError('incomplete one-batch ledger')
            trajectories.setdefault(name,{})[mode]=rows
    if any(x!=counts[0] for x in counts[1:]):raise ValueError('different training budget')
    for name,runs in trajectories.items():
        with (out/(name+'.csv')).open('w') as f:
            writer=csv.writer(f,lineterminator='\n')
            metrics=('issued','recovered','duplicate_matches','off_reference','rejected')
            writer.writerow(['run','ruleset','teacher_commits']+[m+'_'+k for m in arms for k in metrics])
            for batch in zip(*(runs[m] for m in arms),strict=True):
                common=[tuple(r[k] for k in ('run','ruleset','teacher_commits')) for r in batch]
                if len(set(common))!=1:raise ValueError('unmatched teacher snapshot')
                writer.writerow([*common[0],*(r[k] for r in batch for k in metrics)])
    (out/'summary.json').write_text(json.dumps(dict(receiver_sha256=receiver,arms=results),indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('out',type=Path)
    a=parser.parse_args()
    archive(a.root,a.out)
