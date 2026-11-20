"""Compare native leaf execution and increasingly shared composed certificates on complete source Runs."""
import argparse,hashlib,json
from pathlib import Path
from statistics import median
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'higher-order-bake'))
from study import make_session,config,describe
from evaluate import read,rpc

def fingerprint(v):
    return hashlib.sha256(json.dumps(v,separators=(',',':')).encode()).hexdigest()


def variants(a):
    parents=read(HERE.parent/'higher-order-bake/growth.json')['second_round']
    anchor=config(a,'baked',parents,recursive=True)
    off=dict(bias=-1,threshold=0,weights=[0.]*8)
    # Accept recursive parent steps only. This uses information already supplied at publication.
    mixed=dict(bias=-0.5,threshold=0,weights=[0.,0.,0.,0.,0.,0.,0.,1.])
    choices={n:dict(anchor,composed=c,**({'macro_policy':p} if p else {})) for n,c,p in
        [('leaf',0,None),('frontier',1,None),('seal',2,None),('inline',3,None),('none',3,off),('mixed',3,mixed),('delta',4,None),('delta-none',4,off),('delta-mixed',4,mixed)]}
    choices['leaf-retire']=dict(choices['leaf'],recycle=True)
    choices['delta-retire']=dict(choices['delta'],recycle=True)
    return choices



def study(a):
    a.catalog=read(HERE.parent/'higher-order-bake/catalog.json')
    a.out.mkdir(parents=True,exist_ok=False);results={}
    for case in a.cases:
        for seed in a.seeds:
            proc,req,plans,_,cap=make_session(a,case,seed)
            arms={};identity=None;baseline=None
            available=variants(a)
            states={name:available[name] for name in a.arms}
            try:
                for name,cfg in states.items():
                    r=rpc(proc,dict(req,audit=True,higher_config=dict(cfg,profile=True)))
                    parity=describe(r,case,a,plans,cap);h=r['higher']
                    exact=[fingerprint(v) for v in (h['winners'],h['transactions']['source_order'],r['root_recipe']['commits'],
                           r['root_recipe']['fresh'],r['merge_child']['issued'],r['single']['committed'])]
                    if identity is None:identity=exact
                    assert exact==identity,(case,name,[(i,x) for i,x in enumerate(exact) if x!=identity[i]])
                    charges=h['charges'];work=h['boundary']
                    ids=[(c['root'],c['generation'],c['counts'][:3]) for c in charges]
                    if baseline is None:baseline=ids
                    assert ids==baseline,(case,name,'different actual owner exposures or winners')
                    pos=[c for c in charges if c['selected']]
                    assert sum(c['counts'][2] for c in charges)==parity['winners']
                    if name in ('none','delta-none'):assert not pos
                    if name in ('mixed','delta-mixed'):assert 0<len(pos)<len(charges)
                    scans=sum(c['counts'][0] for c in pos);fresh=sum(c['counts'][1] for c in pos)
                    assert not work[2] or scans+work[5]==work[2]
                    assert fresh==work[4]
                    if name in ('inline','mixed','delta','delta-mixed'):assert work[8]==work[6]==fresh and work[8]>0
                    if name=='seal':assert not work[8] and work[6]==fresh
                    front_tot=sum(r['single']['rules'][str(a.catalog['family'][k])][1] for k in ('eq','gt'))
                    assert 0<=work[2]<=front_tot
                    if not name.startswith('delta'):assert work[2] in (front_tot,0)
                    arms[name]=dict(ms=[],source_exact=True,graph=parity['graph'],rhs=parity['rhs'],direct=parity['direct'],fresh=parity['fresh'],runs=parity['runs'],winners=parity['winners'],max_chain=parity['max_chain'],identity=identity,boundary=work,delta=h.get('delta'),leaf_entry=front_tot,
                       publications=len(charges),admitted=len(pos),net_entry_after_rebuild=scans-fresh-work[1],
                       initial_row_decodes_saved=scans,selected_wins=sum(c['counts'][2] for c in pos),
                       root_wire_bytes=r['root_recipe']['wire_bytes'],source_owned_refreshes=sum(c['counts'][3] for c in pos),
                       family_guard_counts=dict(selected=h['counts'][5],wrong_fresh_branch=h['counts'][6],stale=h['counts'][7],stale_version=h['counts'][9]))
                    if a.save_charges:(a.out/f'{case}-{seed}-{name}-charges.json').write_text(json.dumps(charges,separators=(',',':')))
                for trial in range(a.repeats+1):
                    names=list(states);order=names[trial%len(names):]+names[:trial%len(names)]
                    for name in order if trial%2 else order[::-1]:
                        r=rpc(proc,dict(req,audit=False,higher_config=states[name]))
                        assert r['state_sha']==arms[name]['graph'] and r['higher']['boundary']==arms[name]['boundary']
                        if 'inference_fact_decodes' in r:
                            actual=r['inference_fact_decodes']
                            assert arms[name].setdefault('native_fact_decodes',actual)==actual
                        if trial:arms[name]['ms'].append(r['ms'])
                for name,v in arms.items():v['median_ms']=median(v['ms'])
            finally:proc.stdin.close();proc.wait()
            results[f'{case}/{seed}']=arms;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            print(case,seed,[(k,round(v['median_ms'],2),v['net_entry_after_rebuild'],v['boundary'][8]) for k,v in arms.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','capture','train_capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709]);p.add_argument('--repeats',type=int,default=8)
    p.add_argument('--arms',nargs='+',default=['leaf','frontier','seal','inline','none','mixed'])
    p.add_argument('--save-charges',action='store_true');study(p.parse_args())
