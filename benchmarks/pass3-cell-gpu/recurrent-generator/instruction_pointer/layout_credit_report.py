"""Check native ledgers and summarize ownership and transfer across a frozen graph catalog."""
import argparse
from pathlib import Path
import json

from higher_cell import read
from ripsat_layout import signatures
from ripsat_replay import unpack
from train_ripsat import layout_id


def verify(report, exact):
    run=report['execution']
    ledger=run['ept']
    counts=[sum(v) for v in zip(ledger['signed_internal'],ledger['signed_external'],
                                ledger['uncredited'],strict=True)]
    if (ledger['ledger_sha256']!=exact['ept']['ledger_sha256'] or
        counts!=exact['ept']['uncredited'] or run['state_sha']!=exact['state_sha']):
        raise ValueError('state or effective operation ledger changed')
    if run['counts']['accepted']+run['assist']['residual_commits']!=report['reference_commits']:
        raise ValueError('signed and residual commits do not partition the reference')


def summarize(root,donor,baked,experiment):
    layouts=unpack(read(baked/'catalog.json'))
    held={i for i,g in enumerate(layouts) if int(layout_id(g)[:8],16)%8==0}
    source=signatures(read(donor/'program.json'))
    summary={}
    for folder in sorted((experiment/'final').iterdir()):
        rows={}
        all_units=set()
        complete_units=set()
        for path in sorted(folder.glob('*.json')):
            report=read(path)
            name=report['program']
            verify(report,read(experiment/'gold'/(name+'.json')))
            run=report['execution']
            ops=sum(run['ept']['signed_external']+run['ept']['signed_internal'])
            target=set(signatures(read(root/name/'program.json')))
            units=[u for u,l in enumerate(layouts) if all(source[r] in target for r,_,_ in l)]
            backend=run['layouts']['counts']
            issued={units[int(i)]:v for i,v in backend['issued_layouts'].items()}
            completed={units[int(i)]:v for i,v in backend['completed_layouts'].items()}
            all_units.update(issued)
            complete_units.update(completed)
            rows[name]=dict(accepted=run['counts']['accepted'],reference=report['reference_commits'],
                            signed_operations=ops,paid=run['issued'],ept=ops/run['issued'],
                            coverage=run['counts']['accepted']/report['reference_commits'],
                            completed_by_size=backend['completed_sizes'],held_issued=sum(issued.get(i,0) for i in held),
                            held_completed=sum(completed.get(i,0) for i in held),
                            step_credit=report['credit'])
        summary[folder.name]=dict(programs=rows,distinct_issued=len(all_units),
                                  distinct_complete=len(complete_units),held_complete=len(complete_units & held))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','donor','baked','experiment','out'):
        p.add_argument(key,type=Path)
    a=p.parse_args()
    a.out.write_text(json.dumps(summarize(a.root,a.donor,a.baked,a.experiment),indent=2)+'\n')
