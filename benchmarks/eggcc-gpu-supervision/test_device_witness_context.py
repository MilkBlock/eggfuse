import unittest
import numpy as np
from device_witness_context import initialize,retain,sources


class Context(unittest.TestCase):
    def fixture(self):
        return initialize(dict(present=np.array([True,True,False]),visible=np.ones(3,bool),
            settled=np.ones(3,bool),generation=np.array([2,3,0])),1,np)

    def test_retains_only_actual_admission_and_checks_generation(self):
        state=self.fixture();batch=dict(sources=np.array([[0]]),mask=np.array([[True]]),generations=np.array([[2]]))
        out=retain(state,dict(state,present=np.ones(3,bool)),batch,0,np)
        self.assertEqual(out['context_sources'][:,0].tolist(),[-1,-1,0])
        rows,valid,_=sources(out,np.array([2]),np.array([True]),np.array([0]),1,np)
        self.assertEqual(rows.tolist(),[2,0]);self.assertTrue(valid.all())
        out['generation'][0]+=1
        self.assertEqual(sources(out,np.array([2]),np.array([True]),np.array([0]),1,np)[1].tolist(),[True,False])

    def test_invalid_intermediate_cannot_expose_ancestor(self):
        state=self.fixture();state['present'][:]=True
        state['context_sources'][:,0]=[1,2,-1];state['context_generations'][:,0]=[3,0,-1]
        state['context_valid'][:,0]=[True,True,False];state['visible'][1]=False
        _,valid,_=sources(state,np.array([0]),np.array([True]),np.array([2]),2,np)
        self.assertEqual(valid.tolist(),[True,False,False])

    def test_rejected_admission_does_not_record_context(self):
        state=self.fixture();batch=dict(sources=np.array([[0]]),mask=np.array([[True]]),generations=np.array([[2]]))
        out=retain(state,state,batch,0,np)
        self.assertFalse(out['context_valid'].any())


if __name__=='__main__':unittest.main()
