"""Inspect real signed-middle return values and later original physical parents in two donor Runs. Audit only."""
import argparse,hashlib,json
from collections import Counter,defaultdict
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
bench=run_path(str(HERE.parent/'ripsat-neural-bake/study.py'))
bridge=run_path(str(HERE.parent/'explicit-parent-cell-composition/ripsat_bridge.py'))
adapter=run_path(str(HERE.parent/'ripsat-strict-programs/compile.py'))
src=bench['src']
sha=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def fact(dep):
    return ((dep['Fact']['cell']<<32)|dep['Fact']['op']) if dep and 'Fact' in dep else None


def run_case(a,case,donors):
    prog,plan,req=src.config(a,case)
    recipe=adapter['Recipe'](prog)
    library=adapter['compile_library'](a.evidence,donors,prog)
    spec=library['strict_named']
    encoded={tuple(map(tuple,path)) for path in spec['library']}
    assert encoded=={((143,1,55),)}
    cfg=bench['bake'].settings(req,dict(spec,partial=True,record_links=True))
    cfg.update(rows=dict(cfg["rows"],scalar_certificates=True),integral_root="off",integral_packets=False)
    with src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",prog) as exact:
        gold=exact({"audit":True})
    with src.base.session(a.native,prog,plan) as infer:
        v=infer(dict(cfg,audit=True,birth_ledger=True))
    assert 'source_error' not in v,v.get('source_error')
    assert all(v[k]==gold[k] for k in ('rhs','writes','resumes','runs','state_sha'))
    roots={r[2]:r for r in v['root_recipe']['commits']}
    links={s:(parent,path,ports) for s,parent,path,ports,_ in v['strict_named']['signed_commits']}
    assert len(links)==v['strict_named']['counts']['source_commits']>0
    assert all(path==[[143,1,55]] and roots[s][3]==55 and roots[p][3]==143 for s,(p,path,ports) in links.items())

    primary={r[0]:r[5] for r in v['root_recipe']['fresh']}
    nominated=[c["original"] for c in library["certificates"] if c["donor"]==case]
    assert len(nominated)==1
    selected=nominated[0];special=selected["consumer_serial"]
    assert roots[special][:6]==[selected["consumer_ordinal"],roots[special][1],special,55,roots[special][4],selected["consumer_run"]]
    watched=set(links)|{special};returns=defaultdict(set);aliases=Counter()
    for f,t,epoch,ctor,s,ancestor,cross,flags in v['constructor_births']['rows']:
        if ctor and s in watched and flags&1 and not flags&2 and primary.get(f>>32)==s:
            returns[s,f&0xffffffff].add((f,epoch,'fresh'))
    for run in v['events']:
        for event in run:
            if event[0]=='observed-signed-static-alias':
                _,token,rid,pos=event;assert token in links and roots[token][3]==rid
                aliases[token,pos]+=1
            if event[0]!='observed-signed-return':continue
            _,s,rid,epoch,op,dep,version,reason=event
            assert s in links and rid==roots[s][3] and epoch==roots[s][5]
            if fact(dep) is not None:
                returns[s,op].add((fact(dep),version,reason))

    uses=defaultdict(list)
    for kid,root in roots.items():
        for ref in root[6]:
            f=fact(ref['row'])
            if f is not None:uses[f,ref['version']].append((root[5],root[0],kid,root[3],ref['atom']))
    by_op=defaultdict(Counter);outgoing=Counter();example={};unique=defaultdict(set)
    for s,(parent,path,ports) in links.items():
        current=roots[s];assert len(ports)==1
        previous,op,version,_run=ports[0]
        assert primary[previous]==parent and op==1
        incoming=(previous<<32)|op
        assert any(fact(ref['row'])==incoming and ref['version']==version for ref in current[6])
        effects=recipe.rules[current[3]]['effects']
        for op,eff in enumerate(effects):
            k=f"{op}:{eff['op']}:{eff.get('call',{}).get('table')}"
            hist=by_op[k];hist['signed_applications']+=1
            observed=returns[s,op]
            if not observed:
                hist['static_alias_elided' if aliases[s,op] else 'not_observed']+=1;continue
            assert len({(fid,version) for fid,version,_why in observed})==1,(s,op,observed)
            fid,ver,why=next(iter(observed));hist['observed']+=1;hist[why]+=1
            hist['same_as_middle_input']+=int(fid==incoming)
            cells=set()
            for ep,ordinal,kid,rid,atom in uses[fid,ver]:
                if ep<=current[5] or ordinal<=current[0]:continue
                cells.add(kid)
                try:certificate=recipe.certify(current[3],op,rid,atom)
                except ValueError as error:reason=str(error)
                else:reason="static_source_shape_compatible"
                actual=(kid in links and links[kid][0]==parent and len(links[kid][1])==2)
                outgoing[k,rid,reason,'signed' if actual else 'ordinary_or_other_owner']+=1
                if kid not in links:hist['later_external_named_uses']+=1;unique[k].add(kid)
                if actual:hist['executed_second_step_without_external_proposal']+=1
                if (why=='fresh' or k not in example) and (k not in example or (example[k]['next_rule']!=143 and rid==143)):
                    example[k]=dict(root=parent,middle=s,middle_ordinal=current[0],middle_run=current[5],incoming_fact=incoming,
                                    outgoing_fact=fid,op=op,kind=why,version=ver,terminal=kid,next_rule=rid,next_atom=atom,next_run=ep,
                                    next_ordinal=ordinal,terminal_external=kid not in links,static_check=reason)
            hist['middle_occurrences_with_later_named_use']+=int(bool(cells))
            hist['later_named_consumers']+=len(cells)
    for k,t in by_op.items():t['distinct_later_external_serials']=len(unique[k])
    nominated_row=dict(selected,middle_signed=special in links)
    if special in links:
        parent,path,ports=links[special]
        assert parent==selected["producer_serial"]
        assert (ports[0][0]<<32)|ports[0][1]==selected['result_fact'] and ports[0][2]==selected['version']
    assert {"rule":55,"operation":0,"dst":2,"value":{"slot":1}} in json.loads(prog.read_bytes())['known_results']['static_aliases']
    nominated_row['elided_single_at_op0']=bool(aliases[special,0])
    nominated_row['get_at_op1']=[]
    for fid,ver,kind in sorted(returns[special,1]):
        later=[dict(run=ep,ordinal=q,serial=k,rule=rid,atom=atom,external=k not in links)
               for ep,q,k,rid,atom in uses[fid,ver] if rid==143 and ep>selected['consumer_run'] and q>selected['consumer_ordinal']]
        nominated_row['get_at_op1'].append({'fact':fid,'cell':fid>>32,'op':fid&0xffffffff,'version':ver,'kind':kind,'later_143':later})
    assert nominated_row["middle_signed"]
    assert len(nominated_row["get_at_op1"])==1 and nominated_row["get_at_op1"][0]["kind"]=="fresh"
    return {'nominated_middle':nominated_row,'runs':v['runs'],'rhs':len(roots),'state_sha':v['state_sha'],'root_commits_sha':sha(v['root_recipe']['commits']),
            'ordinary_root_packets':v['root_recipe']['emitted'],'separately_selected_child_packets':v['merge_child']['counts'][1],
            'signed_first_steps':len(links),'signed_second_steps':sum(len(t[1])==2 for t in links.values()),
            'by_operation':dict(by_op),'outgoing_uses':[[*k,n]for k,n in sorted(outgoing.items())],
            'examples':example,'source_rhs_sha':sha(v['rhs']),'source_write_sha':sha(v['writes']),'source_spine_sha':sha(v['resumes'])}


def main(args):
    args.out.mkdir(parents=True,exist_ok=True);res={}
    donors=bridge['donor_paths'](args.donor)
    for case in args.cases:
        res[case]=run_case(args,case,donors)
        (args.out/'chain-audit.json').write_text(json.dumps(res,indent=1)+'\n')
        print(case,res[case]['signed_first_steps'],res[case]['by_operation'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','evidence','out'):p.add_argument(n,type=Path)
    p.add_argument('--donor',action='append',required=True)
    p.add_argument('--cases',nargs='+',default=['dot-product','jacobi-1d'])
    a=p.parse_args();a.seed=1703;a.cap=8192;main(a)
