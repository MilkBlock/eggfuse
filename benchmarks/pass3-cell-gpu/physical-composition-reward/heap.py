"""Validate selected layouts with the legacy counted allocator and complete graph export."""
import argparse
import json
from pathlib import Path
import subprocess
from study import program_path

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for f in ('meter','corpus','study'):p.add_argument(f,type=Path)
    a=p.parse_args()
    def read(p):return json.loads(p.read_bytes())
    results=read(a.study/'results.json');out={};origin={}
    for case,arms in results.items():
        home=a.study/case;out[case]={}
        observation=a.corpus/case/'observation'
        reference={k:read(observation/(k+'.json')) for k in ('state','rhs','writes','resumes')}
        schedules=read(observation/'report.json')['steps']
        accepted=0
        for log in home.glob('run-*/result.json'):
            checks=read(log)['stage_checks']
            if not checks:continue
            assert len(checks)==len(schedules)
            for i,row in enumerate(checks):
                assert row[:6]==[schedules[i][k] for k in ('ruleset','path','iterations','epoch','executed_bindings','changed')]
                assert all(row[6+j]==[reference[t][i]] for j,t in enumerate(('rhs','writes','resumes')))
            accepted+=1
        assert accepted==len(arms['paired'])
        origin[case]=dict(source_runs=len(schedules),ordered_arms=accepted,final_exports=0)

        for name,arm in arms['paired'].items():
            library=home/(name+'.json');dest=home/(name+'-heap.json')
            phases=','.join(read(library)['phases'])
            subprocess.run([a.meter,program_path(a.corpus,case),dest,'inherited-owners','--port-domains-only','--cell-fields','--retired-prefixes',
                            '--integral','primary:'+phases,'--integral-member-views','--integral-neighbors','--integral-library',library,
                            '--matched-storage','3',home/'matched-admissions.json','--state-output',home/(name+'-export.json')],check=True,stdout=subprocess.DEVNULL)
            report=read(dest)
            assert report['final_state_sha256']==arm['source_sha']
            assert read(home/(name+'-export.json'))==reference['state']
            origin[case]['final_exports']+=1
            out[case][name]={k:report[k] for k in ('execution_and_takeover_peak_bytes','cumulative_request_bytes_at_completion','integral_instance_teardown_bytes',
                                                    'integral_library_teardown_bytes','graph_owned_teardown_bytes','retained_program_teardown_bytes')}
    (a.study/'origin.json').write_text(json.dumps(origin,indent=1)+'\n')
    (a.study/'heap.json').write_text(json.dumps(out,indent=1)+'\n')
