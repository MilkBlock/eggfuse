"""Compare frozen threshold and terminal credit policies on matched native source Runs."""
import argparse
from collections import Counter,defaultdict
import csv
import json
from pathlib import Path

from alternate_proofs import digest
from prefix_results import run_counts


def read(path):
    return json.loads(path.read_bytes())


def archive(root,exp,baseline,out):
    out.mkdir(exist_ok=True,parents=True)
    policy_names=('frozen','calibrated','terminal','opaque','opaque_calibrated')
    paths=(baseline,exp,exp/'final-parent',exp/'opaque-parent',exp/'opaque-parent/calibrated')
    controls=read(baseline/'receiver-replay.json')
    receiver=controls['receiver_sha256']
    calibrate=read(exp/'training.json')
    terminal=read(exp/'final-parent/training.json')
    opaque=read(paths[3]/'training.json')
    reanchored=read(paths[4]/'training.json')
    if any(opaque[k]!=terminal[k] for k in ('source_exposure','optimizer_prefix_reads','training_prefixes','updates','initial_sha256')):
        raise ValueError('different terminal training examples, initial parameters or budget')
    if reanchored['runs']!=calibrate['runs'] or reanchored['required']!=calibrate['required']:
        raise ValueError('unmatched calibration after changing the port representation')
    hashes=[calibrate['initial_sha256'],calibrate['weights_sha256'],terminal['weights_sha256'],opaque['weights_sha256'],reanchored['weights_sha256']]
    if (reanchored['initial_sha256']!=hashes[3] or terminal['initial_sha256']!=hashes[1] or any(digest(p/'model.pt')!=s for p,s in zip(paths[1:],hashes[1:]))
            or any(t['receiver_sha256']!=receiver for t in (terminal,calibrate,opaque,reanchored))):
        raise ValueError('unmatched checkpoint or receiver')
    for name,stats in terminal['source_exposure'].items():
        if set(stats.get('runs',[])) & set(calibrate['runs'].get(name,[])):
            raise ValueError('calibration Run in terminal training')
    report=dict(receiver_sha256=receiver,hashes=dict(zip(policy_names,hashes)),top_k=32,mode='shadow',
                calibration=calibrate,terminal_training=terminal,opaque_training=opaque,second_calibration=reanchored,workloads={},exclusive={},conditional={})
    for case in ('fact','loopfact','sum-divisors'):
        required=defaultdict(dict)
        for p in read(root/case/'tape.json')['requests']:
            required[p['run']][p['token']]=(p['rule'],len(p['parents']))
        rows=[]
        measurements={}
        for idx,(name,path) in enumerate(zip(policy_names,paths)):
            filename=case+'-all-cap.json' if idx==0 else case+'.json'
            packet=read(path/filename)
            v=packet['result']
            if (packet['policy']!={'top_k':32,'verify':False,'audit':False} or packet.get('open_anchor_gate')
                    or packet['weights_sha256']!=hashes[idx] or packet['receiver_sha256']!=receiver
                    or v['state_sha']!=controls['programs'][case]['state_sha'] or v['independent_search_calls']
                    or v['mode']!='shadow' or v['neural_waves']!=v['runs']):
                raise ValueError('changed trajectory, controller or search mode')
            series=v.pop('by_run')
            if len(series)!=v['runs']:
                raise ValueError('incomplete Run ledger')
            rows.append(series)
            by_arity=defaultdict(Counter)
            active_rules,hit_rules=0,0
            for r,row in series.items():
                obligations=required[int(r)]
                if row['required']!=len(obligations):
                    raise ValueError('different teacher obligations')
                winners=row['winner_ids']
                active_rules+=len({rid for rid,_ in obligations.values()})
                hit_rules+=len({obligations[w][0] for w in winners})
                for _,arity in obligations.values():by_arity[arity]['required']+=1
                for w in winners:by_arity[obligations[w][1]]['recovered']+=1
            measurements[name]=dict(totals=run_counts(series),by_arity=by_arity,verified_rule_runs=hit_rules,
                                     required_rule_runs=active_rules,execution=v)
        rules=read(exp/(case+'-rules.json'))
        if rules['weights']!=[hashes[i] for i in (0,2,3)]:
            raise ValueError('wrong anchor-only rule model')
        final_rules=read(paths[-1]/(case+'-rules.json'))
        if final_rules['weights']!=[hashes[-1]]:
            raise ValueError('wrong recalibrated opaque root')
        for i,rc in zip((0,2,3,4),rules['counts']+final_rules['counts'],strict=True):
            actual=measurements[policy_names[i]]
            if (rc['required_commits']!=actual['totals']['required']
                    or rc['required_rule_runs']!=actual['required_rule_runs']
                    or rc['correct_rule_runs']<actual['verified_rule_runs']):
                raise ValueError('incompatible pre-completion rule counts')
            actual['pre_completion_rule_selection']=rc
        # Terminal training freezes every upstream weight, including the anchor
        # offsets and all inputs to root_scores.
        measurements['calibrated']['pre_completion_rule_selection']=measurements['terminal']['pre_completion_rule_selection']
        labels=[n+'_'+effect for n in policy_names[1:] for effect in ('gain','loss')]
        with (out/(case+'.csv')).open('w') as f:
            writer=csv.writer(f,lineterminator='\n')
            writer.writerow(['run','required']+[n+'_'+m for n in policy_names for m in ('issued','recovered')]
                            +labels)
            totals=Counter()
            for r in rows[0]:
                samples=[s[r] for s in rows]
                sets=[set(x['winner_ids']) for x in samples]
                changes=[z for a,b in zip(sets,sets[1:]) for z in (len(b-a),len(a-b))]
                totals.update(dict(zip(labels,changes)))
                writer.writerow([r,samples[0]['required'],*(q for x in samples for q in (x.get('issued',0),x['recovered'])),*changes])
        measurements['changes']=totals
        report['workloads'][case]=measurements
    for idx,(name,path) in enumerate(zip(policy_names,paths)):
        src=read(path/('exclusive-cap.json' if idx==0 else 'exclusive.json'))
        if src['receiver_sha256']!=receiver or src['weights_sha256']!=hashes[idx]:
            raise ValueError('exclusive source differs')
        splits=defaultdict(Counter)
        eggcc={}
        for n,v in src['cases'].items():
            e=v['execution']
            if e['mode']!='exclusive' or e['independent_search_calls']:
                raise ValueError('free rollout used search')
            group=splits[v['split']]
            group.update(programs=1,final_equal=int(v['final_equal']),required=v['reference_commits'],
                         common_commits=v['committed_reference_prefix'])
            failure=v.get('failure')
            if failure:
                if v['final_equal'] or e.get('scope')!='completed prefix before source panic':
                    raise ValueError('failed exclusive run counted as complete')
                group.update(source_panics=1,failed_run_issues=failure['charged']['issued'],
                             failed_run_wall_seconds=failure['charged']['wall_seconds'])
            else:
                group.update(finished=1,issued=e['issued'],accepted=e['counts']['accepted'],
                    duplicates=e['counts']['duplicates'],rejected=sum(e['counts']['rejected'].values()),
                    runs=e['runs'],wall_seconds=e['wall_seconds'],network_seconds=e['network_seconds'],
                    verifier_seconds=e['native_verify_seconds'])
            if v['split']=='eggcc':
                eggcc[n]=dict(common_runs=v['common_runs'],exact_final=v['final_equal'],failure=failure)
        report['exclusive'][name]=dict(splits=splits,eggcc=eggcc)
        if idx:
            conditional=read(path/'conditional.json')
            if conditional['weights_sha256']!=hashes[idx] or conditional['receiver_sha256']!=receiver:
                raise ValueError('different supplied-anchor model')
            report['conditional'][name]=conditional['cases']['loopfact']
    report['coordinate_intervention']={}
    report['exclusive_first_boundary']={}
    for idx in (2,3,4):
        boundary=read(paths[idx]/'boundary.json')
        gauge=read(paths[idx]/'hashes.json')
        if any(q['receiver_sha256']!=receiver or q['weights_sha256']!=hashes[idx] for q in (boundary,gauge)):
            raise ValueError('wrong boundary or coordinate audit')
        if idx>=3 and any(a['changed_proofs'] for c in gauge['cases'].values() for r in c.values() for a in r.values()):
            raise ValueError('opaque address choice changed on xor intervention')
        report['exclusive_first_boundary'][policy_names[idx]]=boundary
        report['coordinate_intervention'][policy_names[idx]]=gauge
    gates=read(paths[-1]/'boundary-gates.json')
    if gates['weights_sha256']!=hashes[-1] or gates['receiver_sha256']!=receiver:
        raise ValueError('boundary intervention changed receiver or checkpoint')
    report['boundary_counterfactuals']=gates
    mixed=read(paths[-1]/'mixed-hashes.json')
    if mixed['permutation']!='mix' or mixed['weights_sha256']!=hashes[-1] or mixed['receiver_sha256']!=receiver:
        raise ValueError('wrong general-bijection control')
    report['permuted_opaque_codes']=mixed
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','exp','baseline','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    archive(a.root,a.exp,a.baseline,a.out)
