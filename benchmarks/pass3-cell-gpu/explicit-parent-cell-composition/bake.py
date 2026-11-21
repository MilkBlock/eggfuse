"""Bake exact constructor-operation to consumer-slot programs from genuine named returns."""
import argparse,hashlib,json,sys
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
ripsat=run_path(str(HERE/"ripsat_bridge.py"))
if __name__ == "__main__" and sys.argv[1:2] == ["ripsat-fragments"]:
    run_path(str(HERE.parent / "ripsat-scale/library.py"))["cli"](sys.argv[2:])
    sys.exit(0)
if __name__=="__main__" and sys.argv[1:2]==["ripsat"]:
    ripsat["cli"](sys.argv[2:])
    sys.exit(0)
base=run_path(str(HERE.parent/'iterative-integral-certificates/bake.py'));src=base['joint']['src']
def settings(req,opt):
    return dict(req,header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,multi_page_tuples=8192,proposal_wave=65536,strict_named=opt)
def relink(paths,ix):
    return [[[ix[p],op,ix[c]] for p,op,c in path] for path in paths if all(ix.get(p) is not None and ix.get(c) is not None for p,op,c in path)]
def train(a):
    a.out.mkdir(parents=True,exist_ok=True);record={};prefix=[];gold={}
    for depth in (1,2):
        totals={};local={}
        for case in ('dot-product','jacobi-1d'):
            p,plan,req=src.config(a,case);ids,ix=base['schema_map'](p)
            if case not in gold:
                with src.base.session(a.exp/'compact-vanilla-20261121/vanilla',p)as ref:gold[case]=ref({})
            cfg={'depth':depth}
            if depth==2:cfg.update(library=relink(prefix,ix),explore_second=True)
            with src.base.session(a.native,p,plan) as solve:v=solve(settings(req,cfg))
            assert 'source_error' not in v,v.get('source_error')
            assert v['state_sha']==gold[case]['state_sha'] and v['runs']==gold[case]['runs'] and v['multi']['total_rhs']==gold[case]['rhs_count']
            z=v['strict_named'];counts=z['counts'];print(case,depth,counts,flush=True)
            assert counts['released']==counts['actual_internal']==counts['source_commits']+z['uncommitted']
            valid=[]
            for path,row in z['routes']:
                if len(path)!=depth:continue
                if any(ix.get(ids[pn])!=pn or ix.get(ids[cn])!=cn for pn,op,cn in path):continue
                k=tuple((ids[pn],op,ids[cn])for pn,op,cn in path)
                if depth==2:assert (k[0],) in prefix
                old=totals.setdefault(k,[0,0,0])
                for i,n in enumerate(row):old[i]+=n
                if row[2]:valid.append((k,row))
            local[case]=dict(program=hashlib.sha256(p.read_bytes()).hexdigest(),counts=counts,positive=valid,graph=v['state_sha'])
        # All named operations for a chosen consumer are kept together. A
        # partial producer set may leave the entire consumer bank uncovered.
        cs={}
        for k,v in totals.items():cs[k[-1][2]]=cs.get(k[-1][2],0)+v[2]
        chosen=[k for k,n in sorted(cs.items(),key=lambda x:(-x[1],x[0])) if n>0][:4]
        keep=sorted(k for k,v in totals.items() if k[-1][2] in chosen)
        prefix.extend(keep)
        record[str(depth)]=dict(consumers=chosen,paths=keep,observed=sum(len(v)>0 for v in totals.values()),positive=sum(v[2]>0 for v in totals.values()),
                                committed=sum(v[2]for v in totals.values()),donors=local)
    (a.out/'library.json').write_text(json.dumps(record,separators=(',',':'))+'\n');print('programs',[len(v['paths'])for v in record.values()],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','out'):p.add_argument(n,type=Path)
    train(p.parse_args())
