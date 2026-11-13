import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from corpus_cell_ridge import initial_attachment,features,load_records,distances
from boundary_cell_ridge import D,B,projection,features as old_features
from collect_observed_corpus import digest
from test_cell_token_successors import rule,atom,make


class CorpusRidge(unittest.TestCase):
    def test_initial_attachment_equals_baked_dense_projection(self):
        ports=[('input',0),('input',1)];binding=[(0,ports[0]),(1,ports[0]),(2,ports[1])]
        values=np.random.default_rng(2).normal(size=D+3*B).astype(np.float32)
        expected=values[D:]@projection(binding,ports,3)
        np.testing.assert_allclose(initial_attachment(values,ports,binding),expected,atol=1e-6)
        q=np.zeros((1,D),np.float32);w=np.zeros((5*D,2),np.float32)
        np.testing.assert_allclose(features(values[None,:],q,expected[None,:],w,np),old_features(values[None,:],q,projection(binding,ports,3)[None,:],w,np),atol=1e-6)

    def test_added_feature_columns_preserve_original_request_features(self):
        rng=np.random.default_rng(4)
        s=rng.normal(size=(2,D+2*B)).astype(np.float32)
        q=rng.normal(size=(2,D)).astype(np.float32);a=rng.normal(size=(2,D)).astype(np.float32)
        w=rng.normal(size=(6*D,5)).astype(np.float32)
        old=features(s,q,a,w[:5*D],np)
        added=features(s,q,a,w,np,np.zeros((2,D),np.float32))
        np.testing.assert_array_equal(old[:,:1+5*D],added[:,:1+5*D])
        np.testing.assert_allclose(old[:,1+5*D:],added[:,1+6*D:],atol=1e-6)

    def test_distance_matches_explicit_group_normalized_difference(self):
        rng=np.random.default_rng(9);x=rng.normal(size=(3,D+7));y=rng.normal(size=(4,D+7))
        delta=x[:,None,:]-y[None,:,:]
        expected=(delta[:,:,:D]**2).mean(2)+(delta[:,:,D:]**2).mean(2)
        np.testing.assert_allclose(distances(x,y,np),expected,atol=1e-10)

    def test_deduplication_preserves_workload_split_and_observation_weight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r=rule([atom('F',0,1)],[make('G',2,1)],2)
            program=root/'program.json';program.write_text(json.dumps(dict(sha256='p',recipe=dict(rules=[r],tables=[]))))
            sample=dict(consumer=0,source=[['F',[['input',0],['input',1]]]],binding=[[0,['input',0]],[1,['input',1]]],completion=dict(facts=[]),observations=3)
            targets=root/'targets.json';targets.write_text(json.dumps(dict(program_sha256='p',targets=[sample])))
            base=dict(status='complete',program=str(program),targets=str(targets),targets_sha256=digest(targets))
            manifest=dict(cases=[dict(base,case='a',split='train'),dict(base,case='b',split='train'),dict(base,case='c',split='test'),dict(case='failed',status='failed')])
            records,failures=load_records(manifest)
            self.assertEqual(len(records),2);self.assertEqual(failures,['failed'])
            self.assertEqual({r['split']:r['observations'] for r in records},{'train':6,'test':3})

if __name__=='__main__':unittest.main()
