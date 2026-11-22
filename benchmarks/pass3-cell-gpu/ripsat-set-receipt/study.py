"""Measure the separately typed, prior-commit Set publication capability against its signed Let prefix."""
from argparse import ArgumentParser
from contextlib import ExitStack
import copy,hashlib,json,subprocess
from pathlib import Path
from runpy import run_path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent
partial=run_path(str(HERE.parent/'strict-partial-named-ports/study.py'));src=partial['src'];digest=partial['digest']
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate_links(v,case):
    born=v['constructor_births'];roots={r[2]:r for r in v['root_recipe']['commits']}
    primary={r[0]:r[5] for r in v['root_recipe']['fresh']};fact={r[0]:r for r in born['rows']};visible={r[0] for r in born['endpoint'] if r[2]==0}
    events={e[4]:e for run in v['events'] for e in run if e[0]=='birth'}
    sn=v['strict_named'];signed={r[0]:r for r in sn['signed_commits']};rows=sn['set_commits'];sets=set()
    reused={tuple(r) for r in sn.get('actual_reused_returns',[])}
    assert len(rows)==sn['set_publication']['confirmed']
    for item in rows:
        seed,mid,child=[item[k] for k in ('root','middle','consumer')]
        fc,op=item['fact'];q=(fc<<32)|op;seen=events[q];path=item['path'];trail=item['ports'];version=item['version']
        assert seed in roots and mid in signed and child in signed and mid not in sets and child not in sets
        assert signed[mid][1:3]==[seed,[path[0]]] and signed[child][1:3]==[seed,path] and signed[child][3]==trail
        assert roots[seed][3]==path[0][0] and roots[mid][3]==path[1][0] and roots[child][3]==path[1][2]
        assert roots[seed][5]<roots[mid][5]==version<roots[child][5] and item['middle_run']<item['consumer_run']
        assert primary[fc]==mid and op==path[1][1] and fact[q][4]==mid and fact[q][2]==version
        assert seen[1]==item['table'] and [*seen[2],seen[3]]==item['fields']
        assert trail[-1]==[fc,op,version,item['middle_run']]
        want={'atom':0,'row':{'Fact':{'cell':fc,'op':op}},'version':version}
        assert want in roots[child][6]
        first=(trail[0][0]<<32)|trail[0][1]
        if first in fact and primary.get(trail[0][0])==seed and fact[first][4]==seed:
            assert trail[0][1]==path[0][1]
        else:
            # The signed producer executed this operation and got a different
            # owner's existing physical reference. Check the return record and
            # producer allocation separately from the consumer's named input.
            coord=tuple([seed,*path[0]])
            assert any(r[:4]==coord and primary.get(r[4])==seed and
                       r[5:]==tuple(trail[0]) for r in reused)
        assert {'atom':0,'row':{'Fact':{'cell':trail[0][0],'op':trail[0][1]}},'version':trail[0][2]} in roots[mid][6]
        sets.add(child)
    paid={x['allocated']<<32 for x in v['merge_child']['issued'] if x['allocated'] is not None}
    effects={k:[0,0]for k in ('typed','dynamic','paid')}
    for fid,t,epoch,ctor,s,_,_,flags in born['rows']:
        if not ctor or s not in sets or not flags&1:continue
        k='paid' if fid in paid else 'dynamic' if flags&2 else 'typed'
        effects[k][0]+=1;effects[k][1]+=int(fid in visible)
    return rows,effects
def check(r):
    base=r['let'];q=r['set']
    for k in ('checks','root_parents','root_ids','nested_ids','cells','children','single_winners','multi_winners','rhs','state_sha','commits','physical','score','single_ledger','birth_digest','endpoint_digest','new','visible','paid','children_issued'):
        assert q[k]==base[k],k
    assert all(q['checks'].values());counts=q['set_counts']
    assert counts['set_attempts']==counts['existing_key']+counts['fresh_activations']
    assert counts['fresh_activations']==counts['published']>=0 and q['packets']==sum(q['emitted'])+q['paid']
    assert counts['confirmed']==q['links'] and q['visible_per_packet']==q['visible']/q['packets']
    assert r['faults']['wrong_kind'] and r['faults']['wrong_target']
    for key in ('missing','stale'):assert r['faults'][key]['restored']
def main(a):
    a.out.mkdir(parents=True,exist_ok=True);results={};all_links={}
    for case in a.cases:
        p,plan,req=src.config(a,case);auth=read(a.authorized/(case+'.json'));assert auth['target_sha256']==sha(p)
        set_spec=auth['strict_named'];first=dict(depth=1,partial=True,library=set_spec['library'])
        opts={'let':first,'set':set_spec};vd=a.exp/'compact-vanilla-20261121'
        with src.base.session(vd/'vanilla-audit',p)as orig:gold=orig(dict(audit=True))
        rows={};logs={}
        for name,opt in opts.items():
            with src.base.session(a.native,p,plan) as run:
                v=run(dict(partial['driver']['filtered'](req,dict(opt,record_links=True)),audit=True,birth_ledger=True))
            assert 'source_error' not in v,(case,name,v.get('source_error'))
            q=src.base.summarize(v,gold);del q['work'],q['rows']
            links,effects=validate_links(v,case);diag=partial['attribution'](v);issued=v['merge_child']['issued'];paid=sum(int(x['selected'])for x in issued)
            total=sum(q['emitted'])+paid
            q.update(set_counts=v['strict_named']['set_publication'],links=len(links),terminal_origins=effects,actual_internal=diag['link_depth'],
                     new=diag['births'],visible=diag['visible'],birth_digest=diag['birth_digest'],endpoint_digest=diag['endpoint_digest'],
                     score=v['single']['adaptive_rows']['decision_digest'],single_ledger=digest(v['single']['committed']),
                     children_issued=len(issued),paid=paid,packets=total,visible_per_packet=diag['visible']/total,authorization_sha256=sha(a.authorized/(case+'.json')),ms=[],wall_ms=[])
            rows[name]=q;logs[name]=links;print(case,name,q['set_counts'],q['emitted'],q['visible_per_packet'],flush=True);del v
        faults={};src_opts=partial['driver']['filtered']
        for kind in ('missing','stale','wrong_fields'):
            with src.base.session(a.native,p,plan) as run:
                v=run(dict(src_opts(req,dict(set_spec,set_fault=kind,record_links=True)),audit=True,birth_ledger=True))
            if kind=='wrong_fields':
                expected=rows['set']['set_counts']['fresh_activations']>0
                assert ('Set activation key/value or version differs' in v.get('source_error',''))==expected
                faults[kind]=dict(error=v.get('source_error'),runs=v['runs'])
            else:
                assert 'source_error' not in v,v.get('source_error')
                eq=src.base.summarize(v,gold);c=v['strict_named']['set_publication'];assert c['confirmed']==0
                for k in ('physical','commits','state_sha','root_parents','cells','children','emitted','wire_bytes'):assert eq[k]==rows['let'][k],(case,kind,k)
                faults[kind]=dict(restored=True,counts=c)
        for mode,msg in [('wrong_kind','incorrect typed Set-publication ABI'),('wrong_target','incorrect Set authorization target'),('spoofed_target','incorrect Set authorization target')]:
            bad=copy.deepcopy(set_spec)
            if mode=='wrong_kind':bad['set_publication']['kinds'][1]='fresh_constructor_let'
            else:bad['set_publication']['target_sha256']='0'*64
            request=src_opts(req,bad)
            if mode=='spoofed_target':request['source_sha256']='0'*64
            f=subprocess.run([a.native,p,plan],input=json.dumps(request)+'\n',text=True,capture_output=True)
            faults[mode]=f.returncode!=0 and msg in f.stderr;assert faults[mode],f.stderr
        rows['faults']=faults;check(rows)
        with src.base.session(a.native,p,plan) as run:
            for i in range(a.repeats+1):
                for name in (['let','set'] if i%2 else ['set','let']):
                    start=perf_counter();v=run(src_opts(req,opts[name]));wall=1000*(perf_counter()-start)
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs'] and v['root_recipe']['emitted']==rows[name]['emitted']
                    assert v['strict_named']['set_publication']==rows[name]['set_counts'] and not v['strict_named']['set_commits']
                    if i:rows[name]['ms'].append(v['ms']);rows[name]['wall_ms'].append(wall)
        for name in opts:rows[name]['median_ms']=median(rows[name]['ms']);rows[name]['median_wall_ms']=median(rows[name]['wall_ms'])
        results[case]=rows;all_links[case]=logs['set']
        (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n');(a.out/'links.json').write_text(json.dumps(all_links,separators=(',',':'))+'\n')
        print(case,'done',len(logs['set']),rows['let']['median_ms'],rows['set']['median_ms'],flush=True)
if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    for k in ('exp','native','authorized','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['dot-product','sum-bits','3mm']);p.add_argument('--repeats',type=int,default=4);main(p.parse_args())
