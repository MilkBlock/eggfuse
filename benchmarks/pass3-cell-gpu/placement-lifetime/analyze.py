"""Compute complete requested-heap and time-in-storage objectives at source boundaries."""
import argparse
import json
from pathlib import Path


def analyze(rows):
    baseline=rows['pooled/keep']
    output={}
    for label,row in rows.items():
        assert row['graph']==baseline['graph'] and row['source_sha']==baseline['source_sha']
        assert row['runs']==baseline['runs'] and row['stride']==1 and baseline['stride']==1
        curve=row['curve'];reference=baseline['curve']
        delta=[r[1]-b[1] for r,b in zip(curve,reference)]
        assert len(delta)==row['runs']+1 and all(r[1]>0 for r in curve)
        assert delta[0]==0,(label,delta[0])
        dynamic=[r[1] for r in curve]
        end=row['static_end'];start=row['static_start']
        assert (dynamic[0],dynamic[-1])==(start[0],end[0])
        assert row['terminal']==row['after_export']
        assert all(n>0 for n in start+end)
        assert all(r[2]>=r[1] and r[6]>=0 for r in curve)
        assert all(r[3]>=p[3] and r[4]>=p[4] for p,r in zip(curve,curve[1:]))
        assert curve[-1][3]==sum(v[0] for v in row['phase_bytes']) and curve[-1][4]==sum(v[1] for v in row['phase_bytes'])
        assert curve[-1][7]==row['selected'] and all(r[2]-curve[0][2]==r[3]-r[4] for r in curve)
        physical=row['phase_bytes'][3]
        assert physical[1]-physical[0]==row['saved']
        output[label]=dict(
            first_difference=next((i for i,d in enumerate(delta) if d),None),
            first_recorded_merge=next((r[0] for r in curve if r[7]),None),
            graph_initial=dynamic[0],graph_final=dynamic[-1],graph_peak=max(dynamic),
            graph_peak_run=dynamic.index(max(dynamic)),final_delta=delta[-1],max_delta=max(delta),
            min_delta=min(delta),runs_below_stock=sum(d<0 for d in delta[1:]),
            graph_byte_runs=sum(dynamic[1:]),area_delta=sum(delta[1:]),
            runtime_byte_runs=sum(r[2] for r in curve[1:]),
            cumulative_requested=curve[-1][3],cumulative_freed=curve[-1][4],
            source_requested=row['phase_bytes'][0][0],placement_requested=row['phase_bytes'][1][0],
            replay_validation_requested=row['phase_bytes'][2][0],merge_requested=physical[0],
            requested_without_replay_checks=curve[-1][3]-row['phase_bytes'][2][0],
            actual_merge_savings=row['saved'],actions=row['issued'],merges=row['selected'],
            program_initial=start[1],program_final=end[1],library_initial=start[2],library_final=end[2],
            after_export_graph=row['after_export'][0],runtime_final=curve[-1][2],
            remaining_runtime_final=curve[-1][2]-end[0]-end[1])
    actor=output['defer/retrained']
    kept=output['defer/keep']
    actor['relative_to_same_placement_keep']={
        'terminal_bytes':actor['graph_final']-kept['graph_final'],
        'graph_byte_runs':actor['graph_byte_runs']-kept['graph_byte_runs'],
        'cumulative_requested':actor['cumulative_requested']-kept['cumulative_requested'],
        'cumulative_freed':actor['cumulative_freed']-kept['cumulative_freed']}
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    out={n:analyze(json.loads((a.folder/(n+'.json')).read_bytes())) for n in ('gemm-bias-relu','gated-state')}
    a.out.write_text(json.dumps(out,indent=1)+'\n')
