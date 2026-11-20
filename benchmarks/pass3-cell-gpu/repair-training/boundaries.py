"""Executable source-context counterexamples. Add an external Single, then add its same-key peer."""
import argparse
from pathlib import Path
import json
import subprocess
from harness import Session,EMPTY

SOURCE='''(datatype Expr (Atom i64) (Single Expr))
(relation Start (i64))
(relation External (i64))
(relation Peer (i64))
(ruleset make)
(ruleset external)
(ruleset keep)
(ruleset link)
(rule ((Start n)) ((Atom n) (Atom (+ n 1))) :ruleset make)
(rule ((External 1) (= x (Atom 2))) ((Single x)) :ruleset external)
(rule ((Peer 1) (= x (Atom 1))) ((Single x)) :ruleset keep)
(rule ((= x (Atom 1)) (= y (Atom 2))) ((union x y)) :ruleset link)
(Start 1)
(External EXTERNAL)
(Peer PEER)
(run-schedule (seq (run make) (run external) (run keep) (run link)))
'''
def test(a):
    w=json.loads((a.weights/'manifest.json').read_bytes());report={}
    a.out.mkdir(parents=True,exist_ok=False)
    for ext,peer in ((0,0),(1,0),(1,1)):
        name=f'{ext}-{peer}';source=a.out/f'{name}.egg';dest=a.out/name
        source.write_text(SOURCE.replace('EXTERNAL',str(ext)).replace('PEER',str(peer)))
        subprocess.run([a.compiler,'compile','--source',source,'--output',dest],check=True,stdout=subprocess.DEVNULL)
        program=dest/'program.json';reference=dest/'independent'
        subprocess.run([a.runtime,'--program',program,'--output',reference,'--audit-repair-inputs'],check=True,stdout=subprocess.DEVNULL)
        events=json.loads((reference/'events.json').read_bytes())
        union=[e for run in events for e in run if e[0]=='union']
        retired=[e for run in events for e in run if e[0]=='retire']
        sess=Session(a.session,program,None,None,dest)
        out={}
        try:
            from harness import verify
            canonical=None
            for key in ('generic','capture','unsafe','every','stale','synthetic-1703','real-1703','paired-1703','paired-1709'):
                model=key in w['styles'];record=sess.run('model' if model else key,json.loads((a.weights/(key+'.json')).read_bytes()) if model else EMPTY,w['bake']['tables'],True)
                verify(record,reference,union)
                events_now=record['trial']['delivered'];identities=[e[:4] for e in events_now]
                if canonical is None:canonical=identities
                assert identities==canonical
                out[key]=dict(counts=record['trial']['counts'],recipients=len(identities),state_sha=record['state_sha'],
                              ordered_unions=record['ordered_unions'])
                if key=='capture':out[key]['opportunities']=record['trial']['events']
        finally:sess.close()
        report[name]=dict(external=ext,same_key_peer=peer,collisions=len(retired),runs=len(events),arms=out)
        print(name,len(retired),out['unsafe']['counts']['unsafe_external_rejected'],out['generic']['recipients'],flush=True)
    assert report['0-0']['arms']['unsafe']['counts']['unsafe_external_rejected']==0
    assert report['1-0']['arms']['unsafe']['counts']['unsafe_external_rejected']>0
    assert not report['1-0']['collisions'] and report['1-1']['collisions']>0
    (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('compiler','runtime','session','weights','out'):p.add_argument(k,type=Path)
    test(p.parse_args())
