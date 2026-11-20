"""Generate controlled shared readers, across a fixed population and selected Set density."""
import argparse,subprocess,json
from pathlib import Path
CASES=[(16,2,1),(16,2,128),(16,2,512),(63,2,128),(63,63,128),(64,2,128),(128,2,128),(128,64,128),(256,128,128)]


def source(n,m,k):
    members=sorted({round(i*(n-1)/(m-1)) for i in range(m)})
    assert len(members)==m and 0 in members and n-1 in members
    rows=['(datatype Expr (Atom i64))','(sort ExprSet (Set Expr))','(datatype Holder (Own i64 ExprSet))',
          '(relation Pool (ExprSet))','(relation Reader (i64))','(function Shared () ExprSet :no-merge)',
          '(function Cardinality (Holder) i64 :merge (min old new))','(ruleset make)','(ruleset observe)','(ruleset alias)',
          '(rule ((Reader i) (= s (Shared))) ((Own i s)) :ruleset make)',
          '(rule ((= h (Own i s))) ((set (Cardinality h) (set-length s))) :ruleset observe)',
          f'(rule ((= a (Atom 0)) (= b (Atom {n-1}))) ((union a b)) :ruleset alias)']
    rows.extend(f'(Pool (set-of (Atom {i})))' for i in range(n))
    rows.append('(set (Shared) (set-of '+' '.join(f'(Atom {i})' for i in members)+'))')
    rows.extend(f'(Reader {i})' for i in range(k))
    rows.append('(run-schedule (seq (run make) (run observe) (run alias) (run observe) (run observe)))')
    return '\n'.join(rows)+'\n'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('compiler',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False);cases={}
    for n,m,k in CASES:
        name=f'n{n}-w{m}-readers{k}';egg=a.out/f'{name}.egg';egg.write_text(source(n,m,k))
        p=subprocess.run([str(a.compiler),'compile','--source',str(egg),'--output',str(a.out/name)],capture_output=True,text=True)
        if p.returncode:raise RuntimeError(p.stderr+p.stdout)
        cases[name]=[n,m,k];print(name,flush=True)
    (a.out/'fixtures.json').write_text(json.dumps(cases,indent=1)+'\n')
