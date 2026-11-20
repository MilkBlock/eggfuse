"""Check native unmarked, native marked, and the CPU endpoint for each new source."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
BENCH=Path(__file__).resolve().parents[2]
DIVERSITY=BENCH/'eggcc-diversity'
sys.path.insert(0,str(BENCH/'marker-handoff'))
from choice_diagnosis import SOURCE_CORE_SHA256,check_pair,key


def read(path):
    return json.loads(path.read_bytes())


def normalize(tree):
    if not isinstance(tree,list):return tree
    tree=[normalize(x) for x in tree]
    if tree[0]=='TermConcat':
        assert len(tree)==3
        # Canonical ordered concatenation. Never reorder or remove a leaf.
        def items(x):return x[1:] if isinstance(x,list) and x[0]=='$concat-sequence' else [x]
        return ['$concat-sequence',*items(tree[1]),*items(tree[2])]
    if tree[0]=='TermBop' and tree[1] in (['Add'],['Mul']):
        left,right=sorted(tree[2:],key=key)
        if tree[1]==['Add']:
            for sub,other in [(left,right),(right,left)]:
                if isinstance(sub,list) and sub[:2]==['TermBop',['Sub']]:
                    # (x-y)+z = x+(z-y) = (x+z)-y via the two existing
                    # unconditional peephole rules. Preserve every operand.
                    inner=normalize(['TermBop',['Add'],sub[2],other])
                    return ['TermBop',['Sub'],inner,sub[3]]
        tree[2:]=[left,right]
    return tree

def verify(base,program):
    assert hashlib.sha256(key(base['source_core']).encode()).hexdigest()==SOURCE_CORE_SHA256
    a,b=base['recipe'],program['recipe']
    assert base['initial']==program['initial']
    for field in ('control','rulesets','tables'):assert a[field]==b[field]
    init,=next(rs['rule_ids'] for rs in b['rulesets'] if rs['name']=='initialization')
    assert len(a['rules'])==len(b['rules'])
    for i,(x,y) in enumerate(zip(a['rules'],b['rules'])):
        assert x['query']==y['query']
        # Names contain printed fresh variables and can differ. Check every
        # semantic operand, effect, slot sort, set membership and delta flag.
        if i!=init:
            assert x['effects']==y['effects']
            assert {k:v for k,v in x['metadata'].items() if k!='name'}=={k:v for k,v in y['metadata'].items() if k!='name'}
            assert [(s['definition'],s['sort']) for s in x['slots']]==[(s['definition'],s['sort']) for s in y['slots']]
    assert not b['rules'][init]['query'] and {e['kind'] for e in b['rules'][init]['effects']}<= {'copy','construct','set'}
    return len(b['rules'])-1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','reference','binary','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    assert __debug__
    base=read(a.reference/'sum-bits/program.json')
    results={}
    for case in read(DIVERSITY/'manifest.json')['cases']:
        n=case['name'];src=a.corpus/n;prog=read(src/'program.json')
        report={'core':hashlib.sha256(key(prog['source_core']).encode()).hexdigest(),
                'unchanged_noninitial_rule_bodies':verify(base,prog)}
        states=[]
        for file in ('source_sk','source_sk_mk'):
            dest=a.out/f'{n}-{file}.json'
            subprocess.run([a.binary,src/(file+'.egg'),dest],check=True)
            states.append(read(dest))
        states.append(read(src/'reference/state.json'))
        for label,l,r in [('unmarked_vs_marked',0,1),('marked_vs_cell',1,2)]:
            outcome=check_pair(states[l],states[r],prog['source_core']['tables'],normalize=normalize,identities='Add/Mul commute, ordered Concat reassociation, and the two source Add/Sub peepholes')
            report[label]=outcome
        report['status']='pass' if all(report[k]['status']=='pass' for k in ('unmarked_vs_marked','marked_vs_cell')) else 'unverified'
        results[n]=report
        print(n,report['status'],flush=True)
        (a.out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    assert all(r['status']=='pass' for r in results.values())
