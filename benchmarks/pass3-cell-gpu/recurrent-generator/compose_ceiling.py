"""Maximum distinct reference RHS under per-source-Run issuance budgets, with verified ancestry."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np
import shutil
import tempfile
import subprocess


def maximum_cover(actions, runs, budget):
    """Each action is an ordered chain of RHS ordinals. Its first event owns its issuance budget."""
    if not actions:return dict(covered=0,issued=0,distinct_by_length={},overlap=0,optimal=True)
    solver=shutil.which('cbc')
    if not solver:raise RuntimeError('put the COIN-OR CBC executable on PATH')
    covers=defaultdict(list);issues=defaultdict(list)
    for i,path in enumerate(actions):
        name=f'x{i}'
        issues[int(runs[path[0]])].append(name)
        for event in path:covers[event].append(name)
    # Grouping the decision variables by source Run bounds certificate issuance.
    # Each RHS has one objective variable, including RHS shared by several proofs.
    weight=len(actions)+1
    objective=' + '.join(f'{weight} y{e}' for e in covers)+' - '+' - '.join(f'x{i}' for i in range(len(actions)))
    lines=['Maximize','value: '+objective,'Subject To']
    lines.extend(f'g{r}: ' + ' + '.join(names)+f' <= {budget}' for r,names in issues.items())
    lines.extend(f'c{e}: y{e} - '+' - '.join(names)+' <= 0' for e,names in covers.items())
    lines.extend(['Binary',' '.join(f'x{i}' for i in range(len(actions))),' '.join(f'y{e}' for e in covers),'End'])
    with tempfile.TemporaryDirectory() as tmp:
        model=Path(tmp)/'cover.lp';solution=Path(tmp)/'cover.sol'
        model.write_text('\n'.join(lines)+'\n')
        subprocess.run([solver,str(model),'-ratio','0','-solve','-solution',str(solution)],
                       capture_output=True,text=True,check=True)
        rows=solution.read_text().splitlines()
    if not rows[0].startswith('Optimal - objective value'):raise RuntimeError(rows[0])
    selected=[actions[int(v[1][1:])] for line in rows[1:] if (v:=line.split())[1].startswith('x') and float(v[2])>.5]
    covered={e for p in selected for e in p}
    assert abs(float(rows[0].split()[-1])-(weight*len(covered)-len(selected)))<.01
    assert max(Counter(runs[path[0]] for path in selected).values(),default=0)<=budget
    return dict(covered=len(covered),issued=len(selected),distinct_by_length=dict(Counter(map(len,selected))),
                overlap=sum(map(len,selected))-len(covered),optimal=True)



def study(cap,donor,program,ingress,online=None,label_path=None,compute_ceiling=True):
    source,target=donor['recipe'],program['recipe']
    assert source['tables']==target['tables']
    lib=donor['spine_blocks']['entries']
    lookup={(e['consumer'],e['pivot']):i for i,e in enumerate(lib)}
    assert len(lib)==len(lookup)
    tables={t["name"]:i for i,t in enumerate(ingress["tables"])}
    ingress_tables={(e["rule"],e["anchor"]):tables[e["table"]] for e in ingress["stage_entries"]}
    compatible=set()
    for e in ingress['stage_entries']:
        key=(e['rule'],e['anchor'])
        if key in lookup and all(source['rules'][key[0]][k]==target['rules'][key[0]][k]
                                 for k in ('query','effects','slots')):
            compatible.add(lookup[key])
    recipes=[((None,i),) for i in range(len(lib))]
    for join in donor['iterative_bake']['joins']:
        left,right=(recipes[join[k]] for k in ('left','right'))
        recipes.append(left+((join['output'],right[0][1]),)+right[1:])
    templates=set(recipes)
    with np.load(cap/'neural-inputs.npz') as z,np.load(cap/'output.npz') as g:
        pivot,pub,tickets,features=(z[k] for k in ('pivot','publications','consumed','features'))
        rhs=g['rhs']
        run=rhs[:,0]
        leaf=[lookup.get((int(r),int(p)-1)) if p else None for r,p in zip(rhs[:,1],pivot)]
        sources={i for i,(tag,row) in enumerate(zip(leaf,rhs)) if tag in compatible and
                 int(row[3]) in features[int(row[0])-1,tag*8:(tag+1)*8,0]}
        paths={(i,) for i in sources}
        for end,tag in enumerate(leaf):
            if tag not in compatible:continue
            chain=(end,)
            shape=((None,tag),)
            while tickets[chain[0]] and len(chain)<donor['iterative_bake']['limits']['depth']:
                ordinal,effect,_,table=map(int,pub[tickets[chain[0]]-1])
                child=chain[0];parent=ordinal-1
                assert 0<=parent<child and run[parent]<run[child]
                if leaf[parent] not in compatible:break
                # The target ingress table of the child must agree with the precise published effect.
                child_entry=(int(rhs[child,1]),int(pivot[child])-1)
                assert ingress_tables[child_entry]==table
                shape=((None,leaf[parent]),(effect,shape[0][1]))+shape[1:]
                chain=(parent,)+chain
                if parent in sources and shape in templates:paths.add(chain)
        if label_path is not None:
            # Offline supervision. Every terminal supplies the exact ancestry of the chosen
            # path; a learner may issue the same root with alternative future continuations.
            # Availability at inference is restricted to the root bank and the static catalog.
            template_id={shape:i for i,shape in enumerate(recipes)}
            targets=[]
            for path in sorted(paths):
                first=path[0]
                rank=np.flatnonzero(features[run[first]-1,leaf[first]*8:leaf[first]*8+8,0]==rhs[first,3])
                assert len(rank)==1
                shape=((None,leaf[first]),)+tuple((int(pub[tickets[i]-1,1]),leaf[i]) for i in path[1:])
                targets.append([int(run[first]),leaf[first],int(rank[0]),template_id[shape],len(path),
                                *[int(i+1) for i in path],*([0]*(donor['iterative_bake']['limits']['depth']-len(path)))])
            # Keep every actual returned port, including zero-use exports, and
            # every pivot use. Shared tickets preserve fanout across path boundaries.
            from compound_boundaries import boundaries
            boundary=boundaries(targets,pub,z['witnesses']) if 'witnesses' in z else {}
            np.savez_compressed(label_path,**boundary,targets=np.asarray(targets,dtype=np.int32),
                                publications=pub,consumed=tickets)
        maximum_by_length=dict(Counter(map(len,paths)))
        result=dict(rhs=len(rhs),runs=len(g['runs']),candidate_paths=maximum_by_length,
                    reachable_distinct=len({i for path in paths for i in path}),budgets={})
        longest=max(sorted(paths),key=len,default=())
        example=[]
        for event in longest:
            ticket=int(tickets[event])
            producer,effect,original_row,table=map(int,pub[ticket-1]) if ticket else (0,-1,-1,-1)
            example.append(dict(rhs_ordinal=event+1,source_run=int(run[event]),rule=int(rhs[event,1]),
                                leaf=leaf[event],reads_row=int(rhs[event,3]),publication=ticket,
                                producer_rhs=producer,producer_effect=effect,published_row=original_row,table=table))
        result['example_chain']=example
        result['spine_receipts_checked']=int((tickets!=0).sum())
        if online:
            result['neural_roots']={}
            for seed,folder in online.items():
                with np.load(folder/'neural-output.npz') as actor:
                    ordinal=actor['rhs_ordinal']
                    raw=actor['raw']
                    emitted=set(int(k)-1 for k in ordinal[ordinal>0])
                with np.load(folder/'output.npz') as actual:
                    np.testing.assert_array_equal(actual['rhs'][:,:2],rhs[:,:2])
                    np.testing.assert_array_equal(actual['rhs'][:,4:],rhs[:,4:])
                    # An alternate accepted source may win the same semantic RHS. Do not attach
                    # the reference's certified continuation to that origin without checking it.
                    matched_origins={i for i in emitted if actual['rhs'][i,3]==rhs[i,3]}
                leaves_by_ordinal={int(ordinal[r,c])-1:int(raw[r,c,-4])-1 for r,c in zip(*np.nonzero(ordinal))}
                roots={i for i in matched_origins if leaves_by_ordinal[i]==leaf[i]}
                reachable=[path for path in paths if path[0] in roots and len(path)>1]
                outputs={e for path in reachable for e in path}
                result['neural_roots'][seed]=dict(neural_submitted=len(emitted),compatible_roots=len(roots),
                    roots_with_baked_successor=len({p[0] for p in reachable}),realized_candidate_chains=len(reachable),
                    all_members_already_neural=sum(all(e in roots for e in path) for path in reachable),
                    extra_reference_rhs_if_all_branches_known=len(outputs-emitted))
        if not compute_ceiling:
            return result
        counts=Counter(run[i] for i in sources)
        for b in (2,4,8,16,32):
            base=sum(min(n,b) for n in counts.values())
            combined=maximum_cover(sorted(paths),run,b)
            assert base<=combined['covered']<=result['reachable_distinct']
            result['budgets'][b]=dict(leaf=base,composed=combined)
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','capture','out'):parser.add_argument(k,type=Path)
    parser.add_argument('--paired',type=Path)
    args=parser.parse_args()
    read=lambda p:json.loads(p.read_bytes())
    donor=read(args.ref/'sum-bits/program.json');results={}
    for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        if case in ('sum-bits','dot-product'):
            program=args.ref/case/'program.json';image=args.ref/f'release-input-{case}'
        else:
            program=args.corpus/case/'program.json';image=args.corpus/case/'input'
        ingress=read(image/'ingress.json')
        online={seed:args.paired/f'{case}-{seed}-ids' for seed in (1703,1709)} if args.paired else None
        results[case]=study(args.capture/case,donor,read(program),ingress,online)
        print(case,results[case],flush=True)
    args.out.write_text(json.dumps(results,indent=1)+'\n')
