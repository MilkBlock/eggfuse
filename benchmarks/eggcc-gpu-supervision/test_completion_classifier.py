import unittest
import numpy as np
import mlx.core as mx
from fit_completion_classifier import fit_head,score_head,choose,register_entry,unique_training_rows,training_policy,verify_source,feedback_head_identity
from device_completion_states import compile_states
from test_completion_states import rule
from audit_snapshot_queries import device


class CompletionClassifier(unittest.TestCase):
    def test_feedback_parent_cannot_hide_real_training(self):
        import tempfile,json,hashlib
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'head.npz';p.write_bytes(b'weights');sha=hashlib.sha256(p.read_bytes()).hexdigest()
            report=dict(head_sha256=sha,synthetic_only_training=False)
            p.with_suffix('.json').write_text(json.dumps(report))
            with self.assertRaises(ValueError):feedback_head_identity(p)
            report['synthetic_only_training']=True;p.with_suffix('.json').write_text(json.dumps(report))
            self.assertEqual(feedback_head_identity(p),sha)
            p.write_bytes(b'changed')
            with self.assertRaises(ValueError):feedback_head_identity(p)

    def test_feedback_requires_synthetic_provenance_and_explicit_head(self):
        m=dict(model_sha256='m',capture=dict(synthetic_input=True),source_token_mode='direct state ridge generated Cells, exact imported Cells',completion_readout=dict(kind='direct_state_ridge',head_sha256='h'))
        verify_source(m,{'m'},{'h'})
        with self.assertRaises(ValueError):verify_source(m,{'m'},set())
        with self.assertRaises(ValueError):verify_source(dict(m,capture={}),{'m'},{'h'})
        with self.assertRaises(ValueError):verify_source(m,{'other'},{'h'})
        with self.assertRaises(ValueError):verify_source(dict(m,source_token_mode='unknown'),{'m'},{'h'})

    def test_synthetic_only_policy(self):
        with self.assertRaises(ValueError):training_policy(dict(capture={}))
        training_policy(dict(capture=dict(synthetic_input=True)))
        training_policy(dict(capture={}),allow_historical=True)

    def test_entry_partition_and_duplicate_policy(self):
        programs={};entries=set()
        def meta(run):return dict(capture=dict(program_file_sha256='p'),snapshot_run=run)
        register_entry(meta(1),'train',programs,entries)
        register_entry(meta(2),'train',programs,entries)
        with self.assertRaises(ValueError):register_entry(meta(2),'train',programs,entries)
        with self.assertRaises(ValueError):register_entry(meta(3),'validation',programs,entries)
        x=np.ones((4,2),np.float32);y=np.array([[1,0],[1,0],[0,1],[1,0]],np.float32)
        xx,yy,counts=unique_training_rows(x,y,['p','p','p','q'])
        self.assertEqual(counts,dict(captured=4,unique=3,duplicates=1,ambiguous_inputs=1))
        np.testing.assert_array_equal(yy,y[[0,2,3]])

    def test_centered_head_preserves_ridge_objective_and_gpu_choice(self):
        rng=np.random.default_rng(5)
        x=np.concatenate([np.ones((32,1)),rng.normal(10,.1,(32,19))],axis=1).astype(np.float32)
        y=np.eye(3,dtype=np.float32)[np.arange(32)%3]
        h=fit_head(x,y)
        expected=score_head(x,h,np)
        z=((x-h['mean'])/h['scale']).astype(np.float64)
        primal=np.linalg.solve(z.T@z+10*np.eye(z.shape[1]),z.T@(y-y.mean(axis=0)))
        np.testing.assert_allclose(expected,z@primal+y.mean(axis=0),atol=2e-7)
        actual=mx.compile(lambda v:score_head(v,device(h),mx))(mx.array(x));mx.eval(actual)
        np.testing.assert_allclose(actual,expected,atol=2e-6)
        np.testing.assert_array_equal(np.argmax(actual,axis=1),np.argmax(expected,axis=1))
        constant=fit_head(x,np.ones((32,1),np.float32))
        np.testing.assert_allclose(score_head(x,constant,np),1,atol=1e-7)

    def test_current_input_proof_can_require_unobserved_state(self):
        states=compile_states(rule(3))['states']
        score=np.zeros((1,len(states)),np.float32);score[0,0]=10
        required=np.ones((1,3),bool)
        index,selected=choose(score,required,states,np)
        np.testing.assert_array_equal(selected,1)
        got=mx.compile(lambda s:choose(s,mx.array(required),mx.array(states),mx))(mx.array(score));mx.eval(got)
        np.testing.assert_array_equal(got[0],index);np.testing.assert_array_equal(got[1],selected)

if __name__=='__main__':unittest.main()
