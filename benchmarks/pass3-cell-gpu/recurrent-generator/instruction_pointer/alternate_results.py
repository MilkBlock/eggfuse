"""Archive native, per-Run and ownership-credit controls for the alternate-proof experiment."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from mixed_results import exclusive


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(root,baseline,out):
    labels=read(root/'labels.json')
    source=read(baseline/'live/summary.json')
    build=source['receiver_sha256']
    if labels['receiver_sha256']!=build:raise ValueError('different mining receiver')
    out.mkdir(exist_ok=True,parents=True)
    archived={}
    plan=read(root/'entries.json')
    exposure=read(root/'visibility.json')
    volumes={}
    for name,path in [('canonical',baseline),('expanded',root/'expanded/structural'),('grouped',root/'grouped/structural'),
                      ('blind',root/'anchor-read/blind'),('context',root/'anchor-read/context'),('entry_cover',root/'entry-cover'),
                      ('calibration',root/'commit-calibration'),('disagreement',root/'disagreement')]:
        training=read(path/('calibration.json' if name=='calibration' else 'training.json'))
        sha=training['weights_sha256']
        if digest(path/'model.pt')!=sha:raise ValueError('wrong weights')
        cases=read(path/'exclusive.json')
        held=read(path/'held.json')
        study=read(path/'run79.json')
        if (cases['verifier_sha256']!=build or held['build_sha256']!=build or study['receiver_sha256']!=build
                or cases['weights_sha256']!=sha or study['weights_sha256']!=sha):
            raise ValueError('mismatched verifier or policy')
        recall={}
        folders=[path/'live']
        if name=='expanded':folders.append(path/'blocked-replay')
        if name=='disagreement':folders.append(path/'long-replay')
        for folder in folders:
            summary=read(folder/'summary.json')
            if summary['weights_sha256']!=sha or summary['receiver_sha256']!=build or summary['mode']!='shadow':
                raise ValueError('wrong shadow trajectory')
            for workload,result in summary['cases'].items():
                if workload in recall:raise ValueError('duplicate measurement')
                recall[workload]=result
                with (folder/(workload+'.csv')).open() as f:rows=list(csv.DictReader(f))
                if (len(rows)!=result['runs'] or sum(int(r['recovered']) for r in rows)!=result['recovered'] or
                        sum(int(r['issued']) for r in rows)!=result['issued'] or result['decode_endings']!={'single_batch':len(rows)}):
                    raise ValueError('incomplete single-batch measurement')
                volumes.setdefault(workload,{})[name]=rows
        scope={'fact','loopfact'} if name in ('context','blind','calibration') else {'fact','loopfact','sum-divisors'}
        if set(recall)!=scope:raise ValueError('unfinished trajectory')
        fixed_path=path/('fixed.json' if name=='canonical' else 'fixed79.json')
        archived[name]=dict(training=training,shadow=recall,native_exclusive=cases['cases'],
            run79=study['cases']['loopfact'],
            fixed_run79=read(fixed_path)['cases']['loopfact'] if fixed_path.exists() else None,
            generated_exclusive={k:exclusive(v['exclusive']['cases']) for k,v in held['splits'].items()})
    for name in ('expanded','grouped'):
        t=archived[name]['training']
        if t['alternate_labels_sha256']!=digest(root/'labels.json') or t['grouped_commit_credit']!=(name=='grouped'):
            raise ValueError('invalid alternate-credit treatment')
        for k in ('reads','updates'):
            if t['counts'][k]!=archived['canonical']['training']['counts'][k]:raise ValueError('different training exposure')
    if exposure['weights_sha256']!=archived['grouped']['training']['weights_sha256']:raise ValueError('wrong key audit')
    for arm in ('context','blind'):
        if archived[arm]['training']['frozen_sha256']!=archived['expanded']['training']['weights_sha256']:
            raise ValueError('wrong frozen parent decoder')
        if archived[arm]['run79']['given_anchors']['runs']!=archived['expanded']['run79']['given_anchors']['runs']:
            raise ValueError('parent decoder changed when supplying anchors')
    disagreement=archived['disagreement']['training']
    if disagreement['frozen_sha256']!=archived['expanded']['training']['weights_sha256']:
        raise ValueError('parent penalty used a different base model')
    if archived['calibration']['training']['initial_sha256']!=archived['grouped']['training']['weights_sha256']:
        raise ValueError('calibration used a different base model')
    fanout={}
    for name,path in [('expanded',root/'fanout.json'),('disagreement',root/'disagreement/fanout.json')]:
        probe=read(path)
        row=next(r for r in volumes['sum-divisors'][name] if int(r['run'])==probe['run'])
        if (int(row['issued'])!=probe['issued'] or int(row['teacher_commits'])!=probe['teacher_commits']
                or probe['weights_sha256']!=archived[name]['training']['weights_sha256']):
            raise ValueError('prefix profile differs from complete native shadow')
        fanout[name]=probe
    if archived['context']['training']['counts']!=archived['blind']['training']['counts']:
        raise ValueError('unmatched anchor-context control')
    if archived['entry_cover']['training']['counts']['entry_reads']!=plan['entries_after']:
        raise ValueError('incomplete positive entry training')
    for workload,arms in volumes.items():
        modes=list(arms)
        metrics=('issued','recovered','duplicate_matches','off_reference','rejected')
        with (out/(workload+'.csv')).open('w') as f:
            writer=csv.writer(f,lineterminator='\n')
            writer.writerow(['run','ruleset','teacher_commits']+[m+'_'+k for m in modes for k in metrics])
            for batch in zip(*arms.values(),strict=True):
                common=[tuple(row[k] for k in ('run','ruleset','teacher_commits')) for row in batch]
                if len(set(common))!=1:raise ValueError('unmatched teacher state schedule')
                writer.writerow([*common[0],*(r[k] for r in batch for k in metrics)])
    report=dict(receiver_sha256=build,label_counts=labels['total'],labels_sha256=digest(root/'labels.json'),
        unchanged_fact_block_control=(root/'block-control/fact.csv').read_bytes()==(baseline/'live/fact.csv').read_bytes(),
        visibility=exposure,entry_selection=plan,fanout=fanout,arms=archived)
    if not report['unchanged_fact_block_control']:raise ValueError('different bounded replay result')
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('root','baseline','out'):parser.add_argument(name,type=Path)
    a=parser.parse_args();archive(a.root,a.baseline,a.out)
