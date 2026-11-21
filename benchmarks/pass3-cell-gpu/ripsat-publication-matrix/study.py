"""Four-arm optional typed Set-publication matrix; default RipSat program remains Let-only."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE=Path(__file__).resolve().parent
AUTH=HERE.parent/'ripsat-publication-chain';TRACE=HERE.parent/'filtered-explicit-parent/library.json'
authorizer=run_path(str(AUTH/'authorize.py'))
native_controls=run_path(str(HERE.parent/'ripsat-set-receipt/study.py'))
src=native_controls['src'];partial=native_controls['partial'];bake=partial['strict'].bake
METHODS=('leaf','trace','ripsat','union')
FIXED=('rhs','runs','state_sha','parents','roots','nested','cells','commits','physical','children','score','births_sha','end_sha',
       'single_winners','multi_winners','new','visible','child_candidates','child')
def read(p):return json.loads(p.read_bytes())
def sha(p):return sha256(p.read_bytes()).hexdigest()
def digest(x):return sha256(json.dumps(x,separators=(',',':'),sort_keys=True).encode()).hexdigest()


def libraries(exp,program,case):
    donors={n:exp/'compact-holdouts-20261121-v1'/(n+'-1703')/'program.json' for n in ('dot-product','jacobi-1d')}
    cert=authorizer['load_checked'](AUTH/(case+'.json'),HERE.parent/'ripsat-donor-evidence/evidence.json',donors,program)
    trace=read(TRACE);_,idx=bake.base['schema_map'](program)
    trace_let=bake.relink(trace['1']['paths'],idx)+bake.relink(trace['2']['paths'],idx)
    freeze=lambda seq:{tuple(map(tuple,path)) for path in seq}
    first=freeze(cert['strict_named']['library']);trace_let=freeze(trace_let)
    cap=cert['strict_named']['set_publication'];typed=tuple(map(tuple,cap['path']))
    assert first=={typed[:1]} and typed not in trace_let and cap['target_sha256']==sha(program)
    def spec(paths,publication=None):
        r=dict(depth=2,partial=True,library=[[list(edge) for edge in path] for path in sorted(paths)])
        if publication is not None:r['set_publication']=publication
        return r
    return dict(leaf=dict(depth=0,partial=True),trace=spec(trace_let),ripsat=spec(first,cap),union=spec(trace_let|first,cap),
                union_let_only=spec(trace_let|first)),dict(target_sha256=sha(program),certificate_sha256=sha(AUTH/(case+'.json')),
                program_sha256=cert['program_sha256'],trace_sha256=sha(TRACE),let_trace=len(trace_let),let_ripsat=len(first),
                let_shared=len(first&trace_let),let_union=len(first|trace_let),typed_set=cap['path'])


def cfg(req,spec,audit=False):
    opts=dict(spec)
    if audit:opts['record_links']=True
    r=partial['driver']['filtered'](req,opts)
    return dict(r,audit=audit,birth_ledger=audit)


def summarize(v,gold,enabled):
    assert 'source_error' not in v,v.get('source_error')
    q=src.base.summarize(v,gold);assert q['aligned'] and all(q['checks'].values())
    roots=v['root_recipe']['commits'];rr={r[2]:r for r in roots}
    assert len(rr)==len(roots)==q['rhs']
    births=v['constructor_births'];end={f for f,_,hidden in births['endpoint'] if hidden==0}
    orig=[(fid,t,ep,rr[sid][0],flags&2) for fid,t,ep,ctor,sid,_,_,flags in births['rows'] if ctor and flags&1 and sid]
    sig=v['strict_named'] or {};terms=sig.get('set_commits',[])
    if enabled:
        links,effects=native_controls['validate_links'](v,None)
    else:
        assert not terms
        effects={k:[0,0] for k in ('typed','dynamic','paid')}
    signed=sig.get('signed_commits',[])
    signed_ord={rr[sid][0] for sid,*_ in signed}
    assert len(signed_ord)==len(signed)
    terminal={rr[z['consumer']][0] for z in terms}
    assert len(terminal)==len(terms) and terminal<=signed_ord
    # Ordinals are stable across generations; root serials or paths can be reassigned
    # when competing first-hop templates claim the same actual source winner.
    first={rr[z['middle']][0] for z in terms}
    path_counts=Counter(json.dumps(path,separators=(',',':')) for _,_,path,_,_ in signed)
    paid=sum(int(c['selected']) for c in v['merge_child']['issued'])
    emitted=q['emitted'];packets=sum(emitted)+paid;visible=sum(fid in end for fid,t,ep,ord,dyn in orig)
    result=dict(checks=q['checks'],rhs=q['rhs'],runs=v['runs'],state_sha=q['state_sha'],parents=q['root_parents'],roots=q['root_ids'],
        nested=q['nested_ids'],cells=q['cells'],commits=q['commits'],physical=q['physical'],children=q['children'],
        single_winners=q['single_winners'],multi_winners=q['multi_winners'],score=v['single']['adaptive_rows']['decision_digest'],
        births_sha=digest(orig),end_sha=digest(births['endpoint']),new=len(orig),visible=visible,child_candidates=len(v['merge_child']['issued']),
        emitted=emitted,child=paid,packets=packets,fept=visible/packets,internal=len(signed),set_internal=len(terms),ordinary_let_internal=len(signed)-len(terms),
        set_counts=sig.get('set_publication',{}),set_origins=effects,paths=dict(path_counts),signed_ordinals_sha=digest(sorted(signed_ord)),
        terminal_ordinals_sha=digest(sorted(terminal)),examples=terms[:1])
    return result,(signed_ord,terminal,first)


def work(a):
    a.out.mkdir(parents=True,exist_ok=False);out={}
    assert sha(a.native)==read(HERE.parent/'ripsat-set-receipt/manifest.json')['exe']
    for case in ('sum-bits','3mm'):
        program,plans,req=src.config(a,case);specs,lib=libraries(a.exp,program,case);req['source_sha256']=sha(program)
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',program) as oracle:gold=oracle({'audit':True})
        rows={};ledger={}
        with src.base.session(a.native,program,plans) as run:
            for name in (*METHODS,'union_let_only'):
                v=run(cfg(req,specs[name],True));row,groups=summarize(v,gold,name in ('ripsat','union'))
                rows[name]=row;ledger[name]=groups;del v
                assert all(row[k]==rows['leaf'][k] for k in FIXED),(case,name)
                assert rows['leaf']['packets']-row['packets']==row['internal']
                print(case,name,row['packets'],row['internal'],row['set_internal'],row['fept'],flush=True)
            for trial in range(5):
                order=METHODS[trial%4:]+METHODS[:trial%4]
                for name in order:
                    v=run(cfg(req,specs[name]));r=rows[name];sig=v['strict_named'] or {}
                    assert v['state_sha']==r['state_sha'] and v['runs']==r['runs'] and v['root_recipe']['emitted']==r['emitted']
                    assert sig.get('counts',{}).get('source_commits',0)==r['internal'] and not sig.get('set_commits',[])
                    assert sig.get('set_publication',{}).get('confirmed',0)==r['set_internal']
                    if trial:rows[name].setdefault('ms',[]).append(v['ms'])
        for name in METHODS:rows[name]['median_ms']=median(rows[name]['ms'])
        u,t,r,ul=(ledger[n] for n in ('union','trace','ripsat','union_let_only'))
        gain=dict(from_trace_packets=rows['trace']['packets']-rows['union']['packets'],
            from_same_union_without_set=rows['union_let_only']['packets']-rows['union']['packets'],
            retained_trace_winners=len(t[0]&u[0]),gained_vs_trace=len(u[0]-t[0]),lost_vs_trace=len(t[0]-u[0]),
            union_terminal_in_trace=len(u[1]&t[0]),union_terminal_not_in_trace=len(u[1]-t[0]),
            union_terminal_in_union_let_only=len(u[1]&ul[0]),union_terminal_not_in_union_let_only=len(u[1]-ul[0]),
            ripsat_terminal_retained=len(r[1]&u[1]),ripsat_terminal_lost=len(r[1]-u[1]),union_only_terminal=len(u[1]-r[1]),
            union_let_gains=len(u[0]-ul[0]),union_let_losses=len(ul[0]-u[0]),same_terminal_middle_ordinals=len(r[2]&u[2]))
        assert gain['gained_vs_trace']-gain['lost_vs_trace']==gain['from_trace_packets']
        assert gain['union_let_gains']-gain['union_let_losses']==gain['from_same_union_without_set']
        out[case]=dict(library=lib,native_sha256=sha(a.native),arms=rows,comparison=gain)
        (a.out/'results.json').write_text(json.dumps(out,indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    work(p.parse_args())
