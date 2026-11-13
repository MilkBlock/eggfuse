"""Larger interacting entry forests, bounded real execution and native comparison."""
import argparse,hashlib,json,subprocess,tempfile,time
from pathlib import Path
from run import module
from capacity import summarize


def forest(length,start,variant):
    base='(Input 0)'
    def segment(a,n):return f'(SubTuple {base} {a} {n})'
    def concat(parts,right=False):
        if len(parts)==1:return parts[0]
        if right:return f'(Concat {parts[0]} {concat(parts[1:],True)})'
        return f'(Concat {concat(parts[:-1])} {parts[-1]})'
    cuts=sorted({0,length,length//2,length//3,2*length//3})
    parts=[segment(start+a,b-a) for a,b in zip(cuts,cuts[1:])]
    # Both trees denote the same interval; their subintervals share Input and
    # overlap other explicit roots. These are interacting, not disjoint repeats.
    roots=[concat(parts),concat(parts,True),segment(start+1,length-2)]
    if variant==0:roots.append(segment(start,length))
    elif variant==1:roots.append(f'(Single (Get {base} {start}))')
    else:roots.append(segment(start,length//2))
    return list(dict.fromkeys(roots))


def main():
    p=argparse.ArgumentParser();p.add_argument('--runner',type=Path,required=True)
    p.add_argument('--reference-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    ds=module('dataset',a.reference_dir/'dataset.py')
    rules=json.loads(Path(__file__).with_name('source-rules.json').read_text())['rules']
    prefix='(datatype Expr (Input i64) (Get Expr i64) (Single Expr) (SubTuple Expr i64 i64) (Concat Expr Expr))\n(ruleset always-run)\n'
    prefix+='\n'.join(r['source'] for r in rules)+'\n'
    a.output.mkdir(parents=True,exist_ok=True);results=[];accepted=[];requests=[]
    with tempfile.TemporaryDirectory() as d:
        for length in (6,8,12,16):
            for variant,start in enumerate((-3,0,7)):
                roots=forest(length,start,variant)
                source=prefix+'\n'.join(roots)+'\n(run-schedule (saturate (run always-run)))\n'
                case=dict(id=f'connected-{length}-{variant}',source=source,metadata=dict(length=length,variant=variant,start=start,roots=roots),verify_ruleset='always-run',native_reference=True)
                requests.append(case);req=Path(d)/'input.json';out=Path(d)/'output.json';req.write_text(json.dumps(dict(cases=[case])))
                before=time.perf_counter()
                try:
                    subprocess.run([str(a.runner.resolve()),str(req),str(out)],check=True,capture_output=True,text=True,timeout=1.)
                except subprocess.TimeoutExpired:
                    results.append(dict(id=case['id'],status='timeout',limit_seconds=1.));continue
                except subprocess.CalledProcessError as e:
                    results.append(dict(id=case['id'],status='error',stderr=e.stderr));continue
                elapsed=time.perf_counter()-before;c=json.loads(out.read_text())['cases'][0]
                assert c['fixed_point']['status']=='pass'
                final=ds.canonical(c['final'])[0];native=ds.canonical(c['native_final'])[0]
                assert final==native,case['id']
                states=[summarize(g,32) for g in [c['initial']]+[b['graph'] for b in c['boundaries']]]
                results.append(dict(id=case['id'],status='pass',wall_seconds=elapsed,run_boundaries=len(c['boundaries']),
                    initial=states[0],final=states[-1],max_scalar_blocks=max(s['scalar_only_blocks'] for s in states),
                    scalar_block_growth_events=sum(y['scalar_only_blocks']>x['scalar_only_blocks'] for x,y in zip(states,states[1:])),
                    native_canonical_equal=True,completion_sha256=ds.digest(final)))
                accepted.append(c)
    (a.output/'inputs.json').write_text(json.dumps(dict(cases=requests),indent=2)+'\n')
    (a.output/'runtime.json').write_text(json.dumps(dict(cases=accepted),indent=2)+'\n')
    report=dict(scope='Actual saved Cell executor plus independent native egglog; bounded five-rule DAG contract',
        runner_sha256=hashlib.sha256(a.runner.read_bytes()).hexdigest(),canonicalizer_sha256=hashlib.sha256((a.reference_dir/'dataset.py').read_bytes()).hexdigest(),
        rules_sha256=hashlib.sha256(Path(__file__).with_name('source-rules.json').read_bytes()).hexdigest(),
        cases=results,all_requested_pass=all(r['status']=='pass' for r in results),timing_scope='1-second timeout enforcement, not a performance comparison',
        limitations=['No GPU computation in this collection','Scalar blocks exclude identity, topology and hidden state','Final graph comparison does not independently verify every Run boundary'])
    (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
