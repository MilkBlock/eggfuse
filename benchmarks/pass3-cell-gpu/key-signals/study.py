"""Compare hashed features in the same real Run cohorts at fixed proposal budget."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
from statistics import median
from time import perf_counter
from train import train

ROOT=Path(__file__).resolve().parents[3]
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    target=Path(os.environ.get('CARGO_TARGET_DIR',ROOT/'target'))/'release/eggfuse-cell-runtime'
    binaries={}
    for audit in (True,False):
        features='gpu-bindings'+(',slot-transfer-audit' if audit else '')
        subprocess.run(['cargo','build','--release','--locked','-p','eggfuse-cell-runtime','--features',features],cwd=ROOT,check=True)
        binaries[audit]=a.out/features;shutil.copy2(target,binaries[audit])
    results={}
    for seed in (1703,1709):
        arms={f'{mode}-{dim}':train(a.out,mode,dim,seed) for mode,dim in
              [('single',8),('single',16),('double_hash',8),('source_role',8)]}
        arms['point']=None
        for n in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
            anchor=n in ('sum-bits','dot-product')
            oracle=(a.reference/f'oracle-{n}' if anchor else a.corpus/n/'reference')
            program=(a.reference if anchor else a.corpus)/n/'program.json'
            reference=read(oracle/'report.json')
            out={}
            for i in range(-1,2*len(arms)):
                order=list(arms)
                order=order[i%len(arms):]+order[:i%len(arms)]
                for label in order if i<len(arms) else order[::-1]:
                    dest=a.out/f'{n}-{seed}-{label}-{i}'
                    start=perf_counter()
                    flags=['--unique-parent','point'] if label=='point' else ['--unique-parent','model','--parent-weights',arms[label]]
                    subprocess.run([binaries[i<0],'--program',program,'--output',dest,*flags],
                                   check=True,stdout=subprocess.DEVNULL)
                    cli=(perf_counter()-start)*1000
                    report=read(dest/'report.json'); c=report['unique_parent']
                    assert report['program_sha256']==reference['program_sha256'] and report['backend']==('cell-cpu-unique-point' if label=='point' else 'cell-cpu-resident-parent-model')
                    assert sha(dest/'state.json')==sha(oracle/'state.json')
                    assert [(s['path'],s['iterations'],s['changed'],s['executed_bindings'],s['ruleset']) for s in report['steps']]==[
                        (s['path'],s['iterations'],s['changed'],s['executed_bindings'],s['ruleset']) for s in reference['steps']]
                    if i<0:
                        for f in ('rhs.json','writes.json','resumes.json'):assert sha(dest/f)==sha(oracle/f)
                        assert c['wrong_parent']==c['wrong_identical_code']+c['wrong_primary_only']+c['wrong_other_score']
                        assert c['proposals']==c['audited_parent_addresses']
                        out[label]=dict(weights=sha(arms[label]) if arms[label] else None,counts={k:v for k,v in c.items() if not k.endswith('_seconds')},
                                        samples=[],spine=sha(oracle/'resumes.json'),final=sha(oracle/'state.json'),
                                        rhs=sha(oracle/'rhs.json'),writes=sha(oracle/'writes.json'),runs=len(report['steps']))
                    else:
                        assert c['bindings']==out[label]['counts']['bindings']
                        out[label]['samples'].append(dict(cli_ms=cli,ms=report['inference_seconds']*1000,
                            forward_ms=c['forward_seconds']*1000,port_ms=c['port_seconds']*1000))
            assert len({(a['counts']['anchors'],a['counts']['bindings'],a['counts']['scored_positions']) for k,a in out.items() if k!='point'})==1
            assert len({a['counts']['bindings'] for a in out.values()})==1
            for arm in out.values():arm['median_ms']={k:median(s[k] for s in arm['samples']) for k in arm['samples'][0]}
            results[f'{n}/{seed}']=out
            (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            print(n,seed,{k:(v['counts']['wrong_parent'],round(v['median_ms']['ms'])) for k,v in out.items()},flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('reference','corpus','out'):p.add_argument(k,type=Path)
    main(p.parse_args())
