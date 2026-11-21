"""First-commit native composition of the frozen dispatcher and bounded wide pair actions."""
import argparse,json,hashlib
from pathlib import Path
from runpy import run_path
from collections import Counter,defaultdict
from time import perf_counter
from statistics import median
HERE=Path(__file__).resolve().parent
joint=run_path(str(HERE.parent/'joint-fept-actors/study.py'))
src=joint['src'];weights=json.loads((HERE.parent/'joint-fept-actors/single-policy.json').read_bytes())['weights']
KEYS=joint['KEYS']
FIXED=tuple(k for k in KEYS if k!='raw')+('raw_parent_sha','recurrent','decisions','root_commit_sha','visible_sha','retired_sha',
     'birth_sha','born','visible','expanded_single','expanded_multi','child_candidates','selected_children','source_work','rule_call_sha')

def sha(obj):
    return hashlib.sha256(json.dumps(obj,separators=(',',':')).encode()).hexdigest()


def settings(req,a,trace):
    packed=joint['wave']['settings'](req,a)['packed']
    opt={'mode':'learned','weights':weights}
    g=dict(packed,class_actor=1,rows=dict(packed['rows'],fept_gate=opt))
    return {k:dict(cfg,pair_family={'mode':mode,'trace':trace}) for k,cfg,mode in (
              ('packed',packed,0),('singleton',g,0),('wide',packed,2),('joint',g,2))}


def analyze(case,v,gold,program,arm):
    q=src.base.summarize(v,gold);assert q['aligned'] and all(q['checks'].values())
    row={k:q[k] for k in KEYS}
    s=v['single'];m=v['multi'];root=v['root_recipe'];birth=v['constructor_births'];child=v['merge_child']['issued']
    cls=dict(s['class_actor']);runs=cls.pop('rule_calls');intervals=cls.pop('audit_ranges');families=m['family_work']
    expanded_single,external_multi=root['emitted']
    single_map={i:idx for idx,(start,n) in enumerate(intervals) for i in range(start,start+n)}
    family_map=dict(m['family_origins'])
    assert len(family_map)==len(m['family_origins'])==families['private_rows']
    assert len(single_map)==cls['internal_receipts'] and len(intervals)==cls['issued']
    assert set(single_map).isdisjoint(family_map)
    expanded_multi=m['counts']['raw_tuples']
    assert external_multi+len(family_map)==expanded_multi
    assert families['receiver_pairs']==families['candidate_bound'] and families['actions']==sum(r[1] for r in m['family_rules'].values())
    assert families['private_rows']==sum(r[3] for r in m['family_rules'].values())
    kids=[r for r in child if r['selected']];alloc={r['allocated'] for r in kids if r['allocated'] is not None}
    origins={r[2]:r[1] for r in root['commits']}
    assert len(origins)==len(root['commits'])==q['rhs']==q['neural_rhs']
    categories={'single_action':cls['issued'],'single_literal':expanded_single-len(single_map),'wide_action':families['actions'],
                'multi_literal':external_multi,'selected_child':len(kids)}
    endpoints={r[0] for r in birth['endpoint'] if not r[2]};born=Counter();retained=Counter();birth_records=[]
    for f,t,ep,ctor,sid,anc,cross,flags in birth['rows']:
        if not(ctor and sid and flags&1):continue
        if f>>32 in alloc and f&0xffffffff==0:k=('selected_child',f)
        elif sid in single_map:k=('single_action',single_map[sid])
        elif sid in family_map:k=('wide_action',family_map[sid])
        else:k=(origins[sid]+'_literal',sid)
        born[k]+=1;birth_records.append((f,t,ep,sid))
        if f in endpoints:retained[k]+=1
    assert sum(retained.values())==joint['endpoint_ref'][case]['retention']['original_visible_per_committed_root']['births']
    by_kind={}
    for kind,n in categories.items():
        xs=[v for (tag,i),v in retained.items() if tag==kind]
        by_kind[kind]={'packets':n,'visible':sum(xs),'born':sum(v for (tag,i),v in born.items() if tag==kind),
                      'zero':n-len(xs),'one':xs.count(1),'two_plus':sum(v>=2 for v in xs),'max':max(xs,default=0)}
        assert by_kind[kind]['zero']>=0
    assert sum(x['visible'] for x in by_kind.values())==sum(retained.values())
    by_rule=defaultdict(Counter);arity=Counter();query_width=Counter();rules=program['recipe']['rules']
    by_set=defaultdict(Counter)
    for r,(n,p,refs) in m['pair_rule_issues'].items():
        rid=int(r);assert n>0 and refs%n==0;arity[refs//n]+=n;query_width[len(rules[rid]['query'])]+=n
        by_rule[rid]['multi_literal']+=n
    assert sum(arity.values())==external_multi
    for epoch,r,eligible,selected,scanned,accepted,survivors,descriptors,fallback,empty in runs:
        by_rule[r]['single_action']+=descriptors;by_rule[r]['single_literal']+=fallback
    for r,counts in m['family_rules'].items():by_rule[int(r)]['wide_action']+=counts[1]
    for c in kids:by_rule[c['parent']['rule']]['selected_child']+=1
    all_traffic=Counter()
    for r,z in by_rule.items():all_traffic.update(z);by_set[rules[r]['metadata']['source_set']].update(z)
    assert all(all_traffic[k]==v for k,v in categories.items())
    top=[]
    for rid,traffic in sorted(by_rule.items(),key=lambda it:-it[1]['multi_literal'])[:12]:
        r=rules[rid];top.append([rid,r['metadata']['source_set'],traffic['multi_literal'],len(r['query']),[a['call'].get('table') or a['call'].get('primitive') for a in r['query']]])
    n=sum(categories.values());useful=sum(retained.values());budget=useful//2
    legacy_rows=sum(r[4] for r in runs if not r[3])
    dispatch=s['fept_gate']['calls'] if arm in ('singleton','joint') else 0
    # Forward plus failed/unoccupied prototype offers is the family study's paid-group convention.
    # All-prototype decisions also charge successful prototype examinations and both dispatches.
    rejected_proto=families['absent']+families['stale']
    paid=n+rejected_proto
    prototypes=families['prototypes']; feedback=cls['issued']
    full=dispatch+cls['issued']+legacy_rows+external_multi+families['actions']+prototypes+len(child)
    assert full>=paid
    den={'forward':n,'bidirectional':n+feedback,'paid_groups':paid,'paid_plus_return':paid+feedback,
         'all_prototype_decisions':full,'decisions_plus_return':full+feedback}
    wire_multi=sum(48*p+32*refs for n,p,refs in m['pair_rule_issues'].values())
    wire_single=64*(s['packed']['pages']-(cls['issued']-cls['empty']))+37*categories['single_literal']
    child_wire=sum(8+len(json.dumps({k:x for k,x in c.items() if k not in {'entered_allocator','allocated','reused','rejected'}},
                                  separators=(',',':'),ensure_ascii=False).encode()) for c in kids)
    wire=dict(single_actions=64*cls['issued'],single_literals=wire_single,wide_actions=families['wire_bytes'],multi_literals=wire_multi,
              selected_children=child_wire,feedback=cls['feedback_bytes'])
    row.update(checks=q['checks'],raw_parent_sha=m['raw_sha256'],recurrent=cls['recurrence_digest'],decisions=s['adaptive_rows']['decision_digest'],
           rule_call_sha=sha([[r[0],r[1],r[2],r[4],r[5],r[6],r[9]] for r in runs]),root_commit_sha=sha(root['commits']),
           visible_sha=sha(birth['endpoint']),retired_sha=sha(birth['coalesced']),birth_sha=sha(birth_records),born=sum(born.values()),visible=useful,
           expanded_single=expanded_single,expanded_multi=expanded_multi,child_candidates=len(child),selected_children=len(kids),
           source_work=[s['work'][2],m['counts']['verified_parent_tuples']],single_dispatches=dispatch,single_residual_decisions=legacy_rows,
           single_logits=s['adaptive_rows']['stats']['evaluations'],multi_approx_visits=m['counts']['approximate_visits'],arity=dict(arity),
           residual_query_width=dict(query_width),top_rules=top,rulesets=dict(by_set),categories=by_kind,denominators=den,
           per_packet={k:useful/v for k,v in den.items()},max_total_for_fept_two=budget,
           budget_remaining_after_forward=budget-n,strict_remaining_after_decisions=budget-full,
           wide_actions_affordable_at_fept_two=budget-(n-families['actions']),
           optimistic_matched_packets=n-families['actions']+families['matched_min_packets'],
           optimistic_matched_fept=useful/(n-families['actions']+families['matched_min_packets']),
           class_counts=cls,family_counts=families,wire=wire,bi_bytes=sum(wire.values()),ms=[],wall_ms=[])
    return row


def main(a):
    a.out.mkdir(parents=True,exist_ok=True);all_data={}
    for case in a.cases:
        path,plan,req=src.common.config(a,case);program=json.loads(path.read_bytes());detail=settings(req,a,True);fast=settings(req,a,False)
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',path) as cpu:gold=cpu({'audit':True})
        rows={};faults={}
        with src.base.session(a.native,path,plan) as run:
            for arm,cfg in detail.items():
                v=run(dict(cfg,audit=True,birth_ledger=True));assert 'source_error' not in v,(case,arm,v.get('source_error'))
                row=rows[arm]=analyze(case,v,gold,program,arm);del v
                for k in FIXED:assert row[k]==rows['packed'][k],(case,arm,k)
                print(case,arm,row['visible'],row['denominators'],row['per_packet']['forward'],row['arity'],flush=True)
            for name,cfg,why in [('single',dict(fast['joint'],class_actor=3),'generation mismatch'),
                                  ('wide',dict(fast['joint'],pair_family={'mode':2,'fault':True}),'family')]:
                v=run(cfg);assert why in v.get('source_error','') and v['runs']<gold['runs'];faults[name]=[v['runs'],v['source_error']]
            arms=list(rows)
            for it in range(a.repeats+1):
                seq=arms[it%len(arms):]+arms[:it%len(arms)]
                for arm in seq if it%2 else reversed(seq):
                    t=perf_counter();v=run(fast[arm]);ms=1000*(perf_counter()-t)
                    assert v['runs']==gold['runs'] and v['state_sha']==gold['state_sha']
                    assert v['root_recipe']['allocated']==rows[arm]['root_allocated'] and rows[arm]['family_counts']['actions']==v['multi']['family_work']['actions']
                    if it:rows[arm]['ms'].append(v['ms']);rows[arm]['wall_ms'].append(ms)
            for r in rows.values():r.update(median_ms=median(r['ms']),median_wall_ms=median(r['wall_ms']))
        all_data[case]={'arms':rows,'runs':gold['runs'],'faults':faults}
        (a.out/'results.json').write_text(json.dumps(all_data,indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',default=['3mm','deriche','sum-bits']);p.add_argument('--repeats',type=int,default=4)
    a=p.parse_args();joint['common'](a);main(a)
