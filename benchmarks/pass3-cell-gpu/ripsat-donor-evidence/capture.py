"""Collect original committed rule, physical witness and typed first-birth provenance from actual donors."""
from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path
from runpy import run_path
from hashlib import sha256
import json
HERE=Path(__file__).resolve().parent
wave=run_path(str(HERE.parent/'verified-wave-execution/study.py'));src=wave['source']
FOCUS=((440,3,446),(446,0,446),(502,3,506),(504,4,506),(505,4,506),(55,1,143),(143,2,137),(143,1,55))
def digest(obj):return sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def rule_sig(rule):return digest([rule[k] for k in ('metadata','query','effects','slots','interface')])
def dep_id(ref):
    x=ref['row']
    if 'Fact' in x:return x['Fact']['cell']<<32|x['Fact']['op']
    return None

class Terms:
    """Recover finite representative ground terms from donor births and unions seen BEFORE the source Run."""
    def __init__(self):self.parents={};self.terms={};self.births={}
    def find(self,x):
        while x in self.parents:
            y=self.parents[x];self.parents[x]=self.parents.get(y,y);x=y
        return x
    def read(self,value,sort=None):
        if 'Eq' in value:return self.terms.get(self.find(value['Eq']))
        if 'Int' in value:return (1,('true' if value['Int'] else 'false') if sort=='bool' else str(value['Int']))
        if 'Text' in value:return (1,json.dumps(value['Text'],ensure_ascii=False))
        return None
    def event(self,e,tables):
        if e[0]=='union':
            hi=self.find(e[1]);lo=self.find(e[2])
            if hi!=lo:
                self.parents[hi]=lo
                t=self.terms.pop(hi,None)
                if t and (lo not in self.terms or t<self.terms[lo]):self.terms[lo]=t
        elif e[0]=='birth':
            _,tid,args,ret,fact,*loc=e;self.births[fact]=e
            if tables[tid]['kind']!='constructor' or 'Eq' not in ret:return
            vals=[self.read(a,sort['name']) for a,sort in zip(args,tables[tid]['schema'])]
            if any(a is None for a in vals):return
            size=1+sum(a[0] for a in vals)
            if size>120:return
            op=tables[tid]['name'];text='('+op+''.join(' '+a[1] for a in vals)+')';key=self.find(ret['Eq'])
            if key not in self.terms or (size,text)<self.terms[key]:self.terms[key]=(size,text)


def collect(v,gold,program):
    q=src.base.summarize(v,gold);assert all(q['checks'].values())
    rules=program['recipe']['rules'];tables=program['recipe']['tables'];tids={t['name']:i for i,t in enumerate(tables)}
    roots={r[2]:r for r in v['root_recipe']['commits']};cells={x[0]:x[5] for x in v['root_recipe']['fresh']}
    born={}
    for f,t,ep,ctor,s,_,_,flags in v['constructor_births']['rows']:
        if not s or not (flags&1 and ctor) or flags&2:continue
        assert cells.get(f>>32)==s; born[f]=(s,t,ep)
    by_run=defaultdict(list);total=defaultdict(int);events_by_route=defaultdict(list);exact_ids=set()
    for child in roots.values():
        for ref in child[6]:
            f=dep_id(ref)
            if f not in born:continue
            sid,t,ep=born[f];par=roots[sid];route=(par[3],f&0xffffffff,child[3])
            if ep!=ref['version'] or ep>=child[5]:continue
            edge=(par[2],child[2],ref['atom'],f)
            if edge in exact_ids:continue
            exact_ids.add(edge)
            assert rules[par[3]]['effects'][route[1]]['call']['table']==tables[t]['name']
            assert rules[child[3]]['query'][ref['atom']]['call']['table']==tables[t]['name']
            events_by_route[route].append((route,par,child,f,ref));total[route]+=1
    ranked=sorted(total,key=lambda k:(-total[k],rule_sig(rules[k[0]]),k[1],rule_sig(rules[k[2]])))
    generic=[];seen_sets=set()
    eligible=[k for k in ranked if any('table' in q['call'] for q in rules[k[0]]['query'])
        and rules[k[0]]['metadata']['name'].startswith(('(rule','(rewrite')) and rules[k[2]]['metadata']['name'].startswith(('(rule','(rewrite'))]
    for k in eligible:
        key=(rules[k[0]]['metadata']['source_set'],rules[k[2]]['metadata']['source_set'])
        if key not in seen_sets and len(generic)<12:generic.append(k);seen_sets.add(key)
    for k in eligible:
        if len(generic)==12:break
        if k not in generic:generic.append(k)
    selected=set(generic)|set(FOCUS)
    for k in selected&events_by_route.keys():
        for item in events_by_route[k]:by_run[item[1][5]].append(item)

    terms=Terms();saved={};failures={};noalias=defaultdict(dict)
    # Mirror Graph::import's sorted (sort,old-ID) identity assignment in original input order.
    ids={};initial=[]
    for row in program['initial']:
        values=[]
        for value in row['values']:
            if 'eq' in value: values.append({'Eq':ids.setdefault((value['sort'],value['eq']),len(ids)+1)})
            elif value['sort']=='String':values.append({'Text':value['value']})
            elif value['sort'] in ('i64','bool','Unit'):values.append({'Int':int(value.get('value') or 0)})
            else:values.append({'Unrepresented':value.get('value')})
        if not row.get('subsumed'):
            initial.append(['birth',tids[row['table']],values[:-1],values[-1],-1,None])
    for _ in range(4):
        for e in initial:terms.event(e,tables)

    def snap(root):
        rule=rules[root[3]]; slots=root[7];all_tables=[j for j,a in enumerate(rule['query']) if 'table' in a['call']]
        refs={r['atom']:r for r in root[6]};output=[]
        for j in all_tables:
            at=rule['query'][j];tn=at['call']['table']
            vs=[]
            for a in at['args']:
                if 'slot'in a:vs.append(slots[str(a['slot'])])
                elif isinstance(a['literal'],int):vs.append({'Int':a['literal']})
                elif isinstance(a['literal'],str):vs.append({'Text':a['literal']})
                else:raise ValueError('unsupported literal')
            ground=[terms.read(x,t['name']) for x,t in zip(vs[:-1],tables[tids[tn]]['schema'])]
            if any(x is None for x in ground):
                for ix,t in enumerate(ground):
                    if t is None:failures.setdefault((root[3],j,ix),vs[ix])
                return None
            actual_result=terms.read(vs[-1],tables[tids[tn]]['schema'][-1]['name'])
            output.append(dict(atom=j,table=tn,values=vs,named=refs.get(j),terms=[x[1] for x in ground],result_term=actual_result[1] if actual_result else None,size=sum(x[0] for x in ground)))
        return output
    pending=defaultdict(list)
    for step,events in zip(v['schedule'],v['events']):
        ep=step[1]
        for route,par,child,f,ref in by_run.get(ep,[]):
            try:parents=snap(par)
            except (ValueError,KeyError):continue
            if parents is None:continue
            # Each root frame was captured at its actual source epoch. Future
            # events never enter the producer-side grounding dictionary.
            pending[child[5]].append((route,par,child,f,ref,parents))
        for route,par,child,f,ref,parents in pending.pop(ep,[]):
            try:childrows=snap(child)
            except (ValueError,KeyError):continue
            if childrows is None or f not in terms.births:continue
            born_event=terms.births[f];assert born_event[1]==born[f][1] and born_event[5][1]==par[3]
            size=sum(a['size'] for a in [*parents,*childrows])
            key=(size,par[2],child[2])
            if route not in ((440,3,446),(446,0,446)) and route in saved and saved[route][0]<=key:continue
            def record(r,rows):
                return dict(rule=r[3],fingerprint=rule_sig(rules[r[3]]),source_name=rules[r[3]]['metadata']['name'],
                        ruleset=rules[r[3]]['metadata']['source_set'],epoch=r[5],ordinal=r[0],serial=r[2],rows=rows)
            entry=(key,dict(producer=record(par,parents),consumer=record(child,childrows),producer_op=route[1],
                              consumer_atom=ref['atom'],original_fact=f,original_version=ref['version'],birth_event=born_event,relative_runs=ep-par[5]))
            if route not in saved or key<saved[route][0]:saved[route]=entry
            if route in ((440,3,446),(446,0,446)):noalias[route][(par[2],child[2])]=entry
        for e in events:terms.event(e,tables)
    chains=[(a[0][0]+b[0][0],p1,p2,c2,a,b) for (p1,p2),a in noalias[(440,3,446)].items() for (c1,c2),b in noalias[(446,0,446)].items() if p2==c1]
    if chains:
        _,_,_,_,a,b=min(chains,key=lambda c:c[:4]);saved[(440,3,446)]=a;saved[(446,0,446)]=b

    nominated_serials={u['serial'] for _,x in saved.values() for u in (x['producer'],x['consumer'])}
    real_neighbors=defaultdict(list);declared_receipts={}
    for route,es in events_by_route.items():
        for _,par,child,f,ref in es:
            refkey=','.join(map(str,(*route,ref['atom'])))
            if par[2] not in nominated_serials and refkey in declared_receipts:continue
            receipt=dict(producer_rule=par[3],producer_op=f&0xffffffff,producer_epoch=par[5],producer_serial=par[2],
                consumer_rule=child[3],consumer_atom=ref['atom'],consumer_epoch=child[5],consumer_serial=child[2],consumer_version=ref['version'],
                fact=f,birth_event=terms.births[f])
            declared_receipts.setdefault(refkey,receipt)
            if par[2] in nominated_serials:real_neighbors[str(par[2])].append(receipt)
    return dict(route_receipts=declared_receipts,neighbor_evidence=real_neighbors,reference=dict(runs=v['runs'],rhs=q['rhs'],state_sha=v['state_sha'],source_checks=q['checks']),samples=[
        dict(**sample,support=total[route],selection=("generic_and_requested" if route in generic and route in FOCUS else "generic" if route in generic else "requested")) for route,(_,sample) in sorted(saved.items())],
        discovery=dict(observed_routes=len(total),observed_edges=sum(total.values()),eligible_original_rules=len(eligible),generic_cap=12,generic=generic,requested=FOCUS,
                       no_grounded_sample=sorted((selected&total.keys())-saved.keys())),
        counts={','.join(map(str,route)):n for route,n in sorted(total.items())},unresolved={','.join(map(str,k)):v for k,v in failures.items()})
def main():
    p=ArgumentParser()
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes());a.fraction=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())['models']['fraction']
    for donor in ('dot-product','jacobi-1d'):
        prog,plans,req=src.common.config(a,donor);pr=json.loads(prog.read_bytes())
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog) as ref:gold=ref({'audit':True})
        with src.base.session(a.native,prog,plans) as run:v=run(dict(wave['settings'](req,a)['packed'],audit=True,birth_ledger=True))
        out=collect(v,gold,pr);out['program_sha256']=sha256(prog.read_bytes()).hexdigest();out['recipe_sha256']=pr['recipe']['sha256']
        (a.out/(donor+'.json')).write_text(json.dumps(out,indent=1)+'\n')
        print(donor,out['counts'],[(s['producer']['rule'],s['producer_op'],s['consumer']['rule']) for s in out['samples']],flush=True)
if __name__=='__main__':main()
