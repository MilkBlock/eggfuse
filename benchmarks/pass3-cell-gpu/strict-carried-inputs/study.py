from argparse import ArgumentParser
from collections import Counter,defaultdict
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
wave=run_path(str(HERE.parent/'verified-wave-execution/study.py'));src=wave['source'];template=json.loads((HERE/'template.json').read_bytes())
def digest(obj):return sha256(json.dumps(obj,separators=(',',':')).encode()).hexdigest()
def ref(x):
    a=x['row']['Fact']
    return (a['cell']<<32|a['op'],x['version'])
def observe(v,gold,rule,names):
    assert 'source_error' not in v,v.get('source_error')
    q=src.base.summarize(v,gold);root=v['root_recipe'];r={row[2]:row for row in root['commits']}
    b=v['constructor_births'];visible={x[0] for x in b['endpoint'] if not x[2]}
    source_births=[e for events in v['events'] for e in events if e[0]=='birth'];events={e[4]:e for e in source_births}
    primary={e[0]:e[5] for e in root['fresh']}
    owned={};born=[];typed=Counter();keep=Counter()
    st=v.get('strict_carry') or {};children=st.get('children',[]);internal={x[0] for x in children}
    for fid,table,epoch,ctor,sid,ancestor,cross,flags in b['rows']:
        if not (flags&1 and ctor and sid):continue
        born.append([fid,table,epoch,r[sid][0],flags&2])
        if flags&2:continue
        assert events[fid][1]==table and events[fid][5][1]==r[sid][3] and primary[fid>>32]==sid
        owned[fid]=(sid,epoch,table)
        if sid in internal:
            typed[names[table]]+=1
            if fid in visible:keep[names[table]]+=1
    byprefix=defaultdict(set);possible=[]
    for rec in r.values():
        if rec[3]!=rule or len(rec[6])!=5:continue
        fields=tuple(ref(x) for x in rec[6])
        byprefix[rec[5],fields[:4]].add(fields[-1])
        fid,ve=fields[3];owner=owned.get(fid)
        if not owner or owner[1]!=ve or fid&0xffffffff!=2:continue
        pred=r[owner[0]]
        if pred[3]!=rule or pred[5]+template['distance']!=rec[5] or len(pred[6])!=5:continue
        if all(fields[j]==ref(pred[6][j]) for j in (0,1,2,4)):
            possible.append((rec[0],pred[0],rec[5],fields))
    alt=Counter(len(byprefix[ep,refs[:4]]) for _,_,ep,refs in possible)
    authorized=[]
    for sid,prior,epoch,provided in children:
        a,p=r[sid],r[prior];fields=tuple(ref(x) for x in provided)
        assert a[5]==epoch==p[5]+template['distance'] and a[3]==p[3]==rule and a[6]==provided
        assert all(fields[j]==ref(p[6][j]) for j in (0,1,2,4))
        fid,version=fields[3];assert owned[fid][:2]==(prior,p[5]) and version==p[5] and fid&0xffffffff==2
        assert len(byprefix[epoch,fields[:4]])==1 and len(set(fields))==5
        authorized.append([p[0],a[0],epoch,fields,p[6][3]])
    child_count=sum(int(e['selected']) for e in v['merge_child']['issued'])
    result=dict(checks=q['checks'],runs=v['runs'],rhs=q['rhs'],state_sha=q['state_sha'],root_parents=q['root_parents'],nested=q['nested_ids'],cells=q['cells'],
         ordered=digest([[c[0],c[1],c[3],c[4],c[5],c[6],c[7]] for c in root['commits']]),source_births=digest(source_births),births=digest(born),
         roots=digest([[*c[:5],r[c[5]][0]] for c in root['fresh']]),final=digest(b['endpoint']),single=q['single_winners'],retained=sum(f in visible for f,*_ in born),
         expanded_multi=v['multi']['counts']['raw_tuples'],emitted=root['emitted'],selected_children=child_count,all_child_decisions=len(v['merge_child']['issued']),
         possible=len(possible),possible_source_digest=digest(possible),ordinary_alternatives=dict(alt),confirmed=len(authorized),direct_new=dict(typed),
         direct_retained=dict(keep),examples=authorized[:3],issued_child_digest=digest(authorized),details={k:vv for k,vv in st.items() if k!='children'})
    if 'counts' in result['details']:
        for unused in ('ordered_comparisons','restored_without_external'):result['details']['counts'].pop(unused,None)
    result['external']=sum(result['emitted'])+child_count;result['fept']=result['retained']/result['external']
    assert not st.get('outstanding',0)
    return result
FIXED=('checks','runs','rhs','state_sha','root_parents','nested','cells','ordered','source_births','births','roots','final','single','retained',
       'selected_children','all_child_decisions','possible_source_digest','ordinary_alternatives')
def main():
    p=ArgumentParser()
    for key in ('exp','native','out'):p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);p.add_argument('--probe',action='store_true');a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes());a.fraction=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())['models']['fraction']
    a.out.mkdir(parents=True,exist_ok=False);report={}
    fingerprints=json.loads((HERE.parent/'strict-composition-opportunities/shape-counts.json').read_bytes())['rule_fingerprints']
    for case in a.cases:
        prog,plan,req=src.common.config(a,case);cfg=wave['settings'](req,a)['packed']
        rid=fingerprints[case].index(template['producer']);tab=[t['name'] for t in json.loads(prog.read_bytes())['recipe']['tables']]
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog) as get:gold=get({'audit':True})
        opts={'ordinary':None,'carried':template}
        if not a.probe:opts.update(wrong_version=dict(template,fault='version'),no_unique=dict(template,fault='count'))
        rows={}
        with src.base.session(a.native,prog,plan) as run:
            for name,opt in opts.items():
                v=run(dict(cfg,strict_carry=opt,birth_ledger=True,audit=True));q=observe(v,gold,rid,tab);rows[name]=q;del v
                for k in FIXED:assert q[k]==rows['ordinary'][k],(case,name,k)
                print(case,name,q['external'],q['possible'],q['confirmed'],q['direct_new'],q['direct_retained'],q['details'],flush=True)
            if not a.probe:
                for i in range(5):
                    for n in (('ordinary','carried') if i%2 else ('carried','ordinary')):
                        v=run(dict(cfg,strict_carry=opts[n]));assert v['runs']==gold['runs'] and v['state_sha']==gold['state_sha']
                        if n=='carried':assert v['strict_carry']['counts']['confirmed']==rows[n]['confirmed'] and v['strict_carry']['reference_rows']==0
                        if i:rows[n].setdefault('ms',[]).append(v['ms'])
                for n in ('ordinary','carried'):rows[n]['median_ms']=median(rows[n]['ms'])
        report[case]=rows;(a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
if __name__=='__main__':main()
