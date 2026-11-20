"""Source-compiled cross-segment binary operations before and after a real union."""
import argparse,json,subprocess,os
from pathlib import Path
from study import ARMS,env,execute,read,graph_events


def source():
    lines=['(datatype Expr (Atom i64))','(sort ExprSet (Set Expr))','(relation Pool (ExprSet))',
        '(function Left () ExprSet :no-merge)','(function Right () ExprSet :no-merge)',
        '(function Before (i64) i64 :no-merge)','(function After (i64) i64 :no-merge)',
        '(ruleset x-before)','(ruleset x-after)','(ruleset x-alias)',
        '(rule ((= a (Atom 0)) (= b (Atom 127))) ((union a b)) :ruleset x-alias)']
    for table,set_ in [('Before','x-before'),('After','x-after')]:
        body=['(set ('+table+' '+str(i)+') (set-length '+op+'))' for i,op in enumerate(
            ['(set-union a b)','(set-intersect a b)','(set-diff a b)','(set-insert a x)'])]
        lines.append('(rule ((= a (Left)) (= b (Right)) (= x (Atom 126))) ('+' '.join(body)+') :ruleset '+set_+')')
    lines.extend(f'(Pool (set-of (Atom {i})))' for i in range(128))
    lines+=['(set (Left) (set-of (Atom 0) (Atom 64)))',
            '(set (Right) (set-of (Atom 63) (Atom 64) (Atom 127)))',
            '(run-schedule (seq (run x-before) (run x-alias) (run x-after)))']
    return '\n'.join(lines)+'\n'


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('compiler','reference','runtime','out'):ap.add_argument(k,type=Path)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False);source_file=a.out/'algebra.egg';source_file.write_text(source());program=a.out/'program'
    subprocess.run([a.compiler,'compile','--source',source_file,'--output',program],check=True)
    ref=a.out/'reference';p,_=execute(a.reference,program/'program.json',ref,os.environ,True)
    if p.returncode:raise RuntimeError(p.stderr)
    result={}
    for rep,subscription in ARMS:
        arm=f'{rep}-{subscription}';dest=a.out/arm;p,_=execute(a.runtime,program/'program.json',dest,env(rep,subscription),True)
        if rep=='mask':
            assert p.returncode and '63 admitted member' in p.stderr
            result[arm]=dict(status='expected_capacity_failure');continue
        if p.returncode:raise RuntimeError(p.stderr)
        graph_events(ref,dest)
        rows=read(dest/'state.json')['rows'];observed={}
        for table,want in [('Before',[4,1,1,3]),('After',[3,2,0,3])]:
            observed[table]=[r['values'][1]['value'] for r in sorted([r for r in rows if r['table']==table],key=lambda r:r['values'][0]['value'])]
            assert observed[table]==want,(rep,table,observed)
        result[arm]=dict(status='pass',observed=observed)
    (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
    print(result)
