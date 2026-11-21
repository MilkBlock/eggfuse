"""Count non-audit receiver work and revalidate submitted source bytes."""
from argparse import ArgumentParser
from pathlib import Path
from runpy import run_path
import json
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/'study.py'))
def run(a):
    a.out.mkdir(parents=True,exist_ok=True);out={};ref=study['read'](a.results)
    for case,r in ref.items():
        prog,plans,req=study['src'].config(a,case);p=study['read'](a.authorized/(case+'.json'))['strict_named'];out[case]={}
        for arm,s in [('let',dict(depth=1,partial=True,library=p['library'])),('set',p)]:
            with study['src'].base.session(a.native,prog,plans) as infer:v=infer(study['partial']['driver']['filtered'](req,s))
            assert v['state_sha']==r[arm]['state_sha'] and v['root_recipe']['emitted']==r[arm]['emitted']
            st=v['strict_named'];c=st['counts'];part=st['partition'];assert c['audit_score_inputs']==part['child_logits_for_audit']==0
            assert c['no_score_inputs']+part['production_virtual']==c['actual_internal']
            assert st['set_publication']==r[arm]['set_counts'] and not st['set_commits']
            out[case][arm]=dict(internal=c['actual_internal'],committed=c['source_commits'],full_bank_without_scores=c['no_score_inputs'],
                  mixed_prebound_without_scores=part['production_virtual'],internal_child_logits=0,checked_named_coordinates=c['explicit_addresses'],
                  direct_Spine_addresses=c['direct_spine_lookups']+part['mixed_internal_spine_checks'],
                  residual_bank_metadata=part['residual_bank_rows'],skipped_before_residual_scoring=part['excluded_metadata_rows'],residual_scored=part['residual_scored'],
                  state_sha=v['state_sha'])
        print(case,out[case]['set'],flush=True)
    (a.out/'work.json').write_text(json.dumps(out,indent=1)+'\n')
if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    for k in ('exp','native','authorized','results','out'):p.add_argument(k,type=Path)
    run(p.parse_args())
