#!/usr/bin/env python3
"""Fresh-process, alternating native/Cell replay of the 96 x 3 captured passes.
This measures executions, not end-to-end production extraction equivalence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import statistics
import subprocess
import tempfile
import time
ROOT = Path(__file__).resolve().parents[2]
FIELDS = ('ordinal','ruleset','path','iterations','epoch','logical_matches','executed_bindings','changed')


def sha(path):
    h = hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def call(argv, timeout=360):
    start=time.perf_counter()
    p=subprocess.Popen([str(x) for x in argv],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       start_new_session=True,env=ENV)
    try: out,err=p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL);p.communicate();raise RuntimeError(f'timeout after {timeout}s')
    if p.returncode: raise RuntimeError(err.decode(errors='replace')[-2500:])
    return out.decode(),err.decode(),time.perf_counter()-start


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path)
    p.add_argument('--repeat',type=int,default=3)
    p.add_argument('--limit',type=int)
    args=p.parse_args(); root=args.root.resolve()
    binaries={n:root/'bin'/n for n in ('compiler','cell','native','transfer')}
    hashes={n:sha(path) for n,path in binaries.items()}
    manifest=json.loads((root/'capture/manifest.json').read_text())
    cases=manifest['cases'][:args.limit]
    (root/'scratch').mkdir(exist_ok=True)
    records=root/'suite.jsonl'
    done={(r['case'],r['pass_number']) for r in map(json.loads,records.read_text().splitlines())} if records.exists() else set()
    metadata={'scope':__doc__, 'native_tag':subprocess.check_output(['git','rev-parse','egglog-baseline'],cwd=ROOT,text=True).strip(),
              'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'binaries':hashes,'machine':platform.platform(),'repeats':args.repeat,'threads':1,
              'capture_manifest_sha256':sha(root/'capture/manifest.json'),
              'semantic_contract':'Cell endpoint/schedule determinism only; no suite-wide native semantic acceptance',
              'current_flags':['--repair-ports','--entry-publications'],
              'training':'fixed common Bake input and historical donor; no per-target catalog learning'}
    if (root/'metadata.json').exists():
        old=json.loads((root/'metadata.json').read_text())
        assert old['binaries']==hashes and old['repeats']==args.repeat, 'cannot resume with different executables or repetition count'
    (root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    for phase in (3,1,2):
        for index,c in enumerate(cases):
            name=c['source'].split('/benchmarks/passing/')[1]
            if (name,phase) in done:continue
            item=c['passes'][phase-1]
            source=root/'capture'/Path(c['directory']).name/Path(item['input']).name
            assert sha(source)==item['input_sha256']
            row={'case':name,'directory':c['directory'],'pass_number':phase,'flat_sha256':sha(source),'samples':[],
                 'semantic_status':'not_certified_against_native'}
            with tempfile.TemporaryDirectory(dir=root/'scratch') as tmp:
                w=Path(tmp)
                try:
                    _,_,seconds=call([binaries['compiler'],'compile','--source',source,'--bake-source',root/'bake.egg','--output',w/'compiled'])
                    result,_,link=call([binaries['transfer'],root/'donor.json',w/'compiled/program.json',w/'ready.json'])
                    row.update(compile_bake_s=seconds,link_s=link,prepare_s=seconds+link,units=int(result.strip()))
                    program=json.loads((w/'ready.json').read_text())
                    row.update(program_sha256=program['sha256'],recipe_sha256=program['recipe']['sha256'])
                    for iteration in range(args.repeat):
                        sample={'i':iteration+1,'order':['native','cell'] if (index+phase+iteration)%2==0 else ['cell','native']}
                        for arm in sample['order']:
                            timer=['/usr/bin/time','-l'] if platform.system()=='Darwin' else ['/usr/bin/time','-f','RSS_KIB=%M']
                            if arm=='native':
                                stdout,stderr,wall=call([*timer,binaries['native'],source])
                                sample['native_ms']=float(re.findall(r' ([\d.]+) ms',stdout)[-1])
                            else:
                                dest=w/f'run-{iteration}'
                                stdout,stderr,wall=call([*timer,binaries['cell'],'--program',w/'ready.json','--output',dest,
                                                       '--repair-ports','--entry-publications'])
                                r=json.loads((dest/'report.json').read_text());assert r['status']=='complete'
                                sample['cell_ms']=r['inference_seconds']*1000
                                sample['cell_rss_through_inference_bytes']=r['peak_rss_through_inference_bytes']
                                state=sha(dest/'state.json');(dest/'state.json').unlink()
                                schedule=hashlib.sha256(json.dumps([[s[k] for k in FIELDS] for s in r['steps']]).encode()).hexdigest()
                                for key,val in dict(state_sha256=state,schedule_sha256=schedule,runs=len(r['steps']),bindings=r['stats']['bindings']).items():
                                    if key in row: assert row[key]==val, f'Cell repeat differs: {key}'
                                    row[key]=val
                            sample[arm+'_cli_ms']=wall*1000
                            m=re.search(r'(\d+)\s+maximum resident set size' if platform.system()=='Darwin' else r'RSS_KIB=(\d+)',stderr)
                            sample[arm+'_process_rss_bytes']=int(m[1])*(1 if platform.system()=='Darwin' else 1024)
                        row['samples'].append(sample)
                    row['status']='complete'
                    for metric in ('native_ms','cell_ms','native_cli_ms','cell_cli_ms','native_process_rss_bytes','cell_process_rss_bytes','cell_rss_through_inference_bytes'):
                        row[metric]=statistics.median(s[metric] for s in row['samples'])
                    row['execution_time_ratio']=row['native_ms']/row['cell_ms']
                except Exception as e: row.update(status='failed',error=str(e))
            assert {n:sha(path) for n,path in binaries.items()}==hashes, 'executables changed'
            with records.open('a') as f:f.write(json.dumps(row)+'\n')
            print(phase,index,name,row['status'],round(row.get('native_ms',0),3),round(row.get('cell_ms',0),3),row.get('error','')[:180],flush=True)

ENV={k:v for k,v in os.environ.items() if not k.startswith(('CELL_CPU_','RAYON_','EGGLOG_COUNT_','EGG_LAYOUT_','LLVM_PROFILE_'))}
ENV['RAYON_NUM_THREADS']='1'
ENV['EGG_LAYOUT_ANALYSIS_THREADS']='1'
if __name__=='__main__': main()
