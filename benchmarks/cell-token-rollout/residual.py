"""Check exact GPU-completed tuple fragments against actual CPU residual closure.
Restricted positive saturation experiment, not a general runtime integration.
"""
import argparse,hashlib,json,subprocess,tempfile,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from run import module


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--runner',type=Path,required=True)
    p.add_argument('--reference-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--proposals',type=Path);a=p.parse_args()
    ds=module('dataset',a.reference_dir/'dataset.py');cases=json.loads(a.runtime.read_text())['cases']
    rules=json.loads(Path(__file__).with_name('source-rules.json').read_text())['rules']
    assert mx.metal.is_available();mx.set_default_device(mx.gpu)
    proposal_cases=None
    if a.proposals:
        proposal_file=json.loads(a.proposals.read_text())
        assert proposal_file['runtime_sha256']==hashlib.sha256(a.runtime.read_bytes()).hexdigest()
        assert proposal_file['schema']=='learned-tuple-token-proposals/v1'
        proposal_cases={c['id']:c['values'] for c in proposal_file['cases']}
        assert len(proposal_cases)==len(proposal_file['cases'])
    report=[];executions=[];requests=[];negative=None
    a.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        for case in cases:
            input_rows=[r for r in case['initial']['rows'] if r['table']=='Input']
            assert len(input_rows)==1 and input_rows[0]['values'][0]['value']==0
            base=input_rows[0]['values'][-1]
            roots=[r for r in case['initial']['rows'] if r['table']=='SubTuple']
            assert all(r['values'][0]==base for r in roots)
            values=np.array([[r['values'][1]['value'],r['values'][2]['value']] for r in roots],np.float32)
            assert np.all((values[:,1]>=1)&(values[:,1]<=16)&(np.abs(values[:,0])<=32))
            # CPU compiles exact ragged wiring from input lengths, not final graph.
            owners=np.repeat(np.arange(len(values)),values[:,1].astype(int))
            offsets=np.concatenate([np.arange(int(b)) for _,b in values]).astype(np.float32)
            go=mx.array(owners);gj=mx.array(offsets)
            def run(inputs):
                bound=inputs[go]
                tokens=mx.stack([bound[:,0]+gj,bound[:,1]-gj],axis=1)
                # Subsequent Cell consumes the token directly, including the
                # successor parameters needed for an expansion boundary.
                return mx.stack([tokens[:,0],tokens[:,1],tokens[:,0]+1,tokens[:,1]-1],axis=1)
            gpu_request=None;rejected=0
            if proposal_cases is None:
                fn=mx.compile(run);before=time.perf_counter();device=fn(mx.array(values));mx.eval(device);result=np.array(device)
                gpu_request=time.perf_counter()-before
            # Exact acceptance for this compiled arithmetic domain; learned
            # scores are not used to authorize union or any other graph effect.
            expected=np.array([[values[o,0]+j,values[o,1]-j,values[o,0]+j+1,values[o,1]-j-1] for o,j in zip(owners,offsets)],np.float32)
            if proposal_cases is not None:
                prediction=np.array(proposal_cases[case['id']],np.float32)
                assert prediction.shape==(len(expected),3)
                rounded=np.rint(prediction)
                correct=np.isfinite(rounded).all(1)&(rounded[:,:2]==expected[:,:2]).all(1)&(rounded[:,2]==expected[:,0]+expected[:,1])
                rejected=int((~correct).sum())
                # Exact typed-boundary check, not confidence thresholding.
                pair=np.where(correct[:,None],rounded[:,:2],expected[:,:2])
                result=np.column_stack([pair,pair[:,0]+1,pair[:,1]-1])
                corrupt=rounded.copy();corrupt[0,0]+=1
                assert not np.array_equal(corrupt[0,:2],expected[0,:2])
            np.testing.assert_array_equal(result,expected)
            prefix='(datatype Expr (Input i64) (Get Expr i64) (Single Expr) (SubTuple Expr i64 i64) (Concat Expr Expr))\n'
            prefix+='(ruleset residual)\n(ruleset full-check)\n'
            for rule in rules:
                if rule['rule']!=138:prefix+=rule['source'].replace('always-run','residual')+'\n'
                prefix+=rule['source'].replace('always-run','full-check')+'\n'
            prefix+='\n'.join(case['metadata']['roots'])+'\n'
            effects=[]
            for av,bv,next_a,next_b in result.astype(np.int64):
                if bv==1:
                    effects.append(f'(union (SubTuple (Input 0) {av} 1) (Single (Get (Input 0) {av})))')
                else:
                    effects.append(f'(union (SubTuple (Input 0) {av} {bv}) (Concat (Single (Get (Input 0) {av})) (SubTuple (Input 0) {next_a} {next_b})))')
            # Legacy CPU adapter materializes the completed region once. No
            # graph or per-effect host exchange happened inside GPU completion.
            source=prefix+'\n'.join(effects)+'\n(run-schedule (saturate (run residual)))\n(run-schedule (saturate (run full-check)))\n'
            req=dict(id=case['id'],source=source,verify_ruleset='full-check',include_bindings=True)
            requests.append(req);ip=Path(directory)/'in.json';op=Path(directory)/'out.json';ip.write_text(json.dumps(dict(cases=[req])))
            before=time.perf_counter()
            try:subprocess.run([str(a.runner.resolve()),str(ip),str(op)],check=True,capture_output=True,text=True,timeout=1.)
            except subprocess.TimeoutExpired:
                report.append(dict(id=case['id'],status='timeout'));continue
            except subprocess.CalledProcessError as e:
                report.append(dict(id=case['id'],status='error',stderr=e.stderr));continue
            duration=time.perf_counter()-before;c=json.loads(op.read_text())['cases'][0];executions.append(c)
            residual=[i for i,s in enumerate(c['steps']) if s['ruleset']=='residual']
            assert residual
            pre=ds.canonical(c['boundaries'][residual[-1]]['graph'])[0]
            baseline=ds.canonical(case['final'])[0];native=ds.canonical(case['native_final'])[0]
            after=ds.canonical(c['final'])[0]
            audit=[s for s in c['steps'] if s['ruleset']=='full-check']
            passed=pre==baseline==native==after and all(not s['changed'] for s in audit)
            report.append(dict(id=case['id'],status='pass' if passed else 'difference',
                initial_cells=len(values),rejected_learned_tokens=rejected,gpu_active_tokens=len(result),gpu_padding_tokens=0,
                boundary_action_requests=len(effects),residual_equals_original=pre==baseline,residual_equals_native=pre==native,
                full_rule_audit_changed_runs=sum(bool(s['changed']) for s in audit),
                residual_runs=len(residual),original_runs=len(case['steps'])-2,original_verification_runs=2,
                residual_executed_bindings=sum(c['steps'][i]['executed_bindings'] for i in residual),
                original_executed_bindings=sum(s['executed_bindings'] for s in case['steps']),
                gpu_first_request_seconds=gpu_request,cpu_process_seconds=duration))
            if negative is None:
                no_completion=prefix+'\n(run-schedule (saturate (run residual)))\n(run-schedule (saturate (run full-check)))\n'
                control=dict(id=case['id']+'-missing-completion',source=no_completion,verify_ruleset='full-check')
                ip.write_text(json.dumps(dict(cases=[control])))
                subprocess.run([str(a.runner.resolve()),str(ip),str(op)],check=True,capture_output=True,text=True,timeout=1.)
                control_result=json.loads(op.read_text())['cases'][0]
                ri=[i for i,s in enumerate(control_result['steps']) if s['ruleset']=='residual']
                before_control=ds.canonical(control_result['boundaries'][ri[-1]]['graph'])[0]
                changes=sum(bool(s['changed']) for s in control_result['steps'] if s['ruleset']=='full-check')
                negative=dict(missing_completion_detected=before_control!=baseline,full_rules_changed_runs=changes)
                assert negative['missing_completion_detected'] and changes>0

    (a.output/'inputs.json').write_text(json.dumps(dict(cases=requests),indent=2)+'\n')
    (a.output/'runtime.json').write_text(json.dumps(dict(cases=executions),indent=2)+'\n')
    output=dict(scope='Exact GPU numeric completion plus transformed-source CPU residual experiment; not production runtime',
        proposals_sha256=hashlib.sha256(a.proposals.read_bytes()).hexdigest() if a.proposals else None,
        proposal_mode='saved learned GPU tokens with exact CPU checks and correction' if a.proposals else 'compiled GPU arithmetic',
        input_sha256=hashlib.sha256(a.runtime.read_bytes()).hexdigest(),runner_sha256=hashlib.sha256(a.runner.read_bytes()).hexdigest(),
        negative_control=negative,all_pass=all(r['status']=='pass' for r in report),cases=report,backpropagation=False,intermediate_gpu_host_reads=0,
        disabled_residual_rule=138,
        limitations=['Only parameter tokens are verified; no learned general Eq/topology completion is proven',
        'CPU boundary adapter materializes completed region as source actions; costs remain',
        'only positive unbounded saturation endpoint contract; original finite-Run visibility is not preserved by this source transform',
        'recorded action requests and executed bindings are not committed mutation counts',
        'first GPU requests include compilation; process times include frontend/compile/audit, not speed comparisons'])
    (a.output/'results.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))
    if not output['all_pass']:raise SystemExit(1)
if __name__=='__main__':main()
