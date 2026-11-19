"""Real MPS checks for private RHS representations, release and unresolved obligations."""
import json
import os
from pathlib import Path
import unittest

import torch

from engine import DEFAULT_PLAN, ReadinessEngine, prepare_plan, run_engine


class ReadinessContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not torch.backends.mps.is_available() or os.getenv('PYTORCH_ENABLE_MPS_FALLBACK','0')!='0':
            raise RuntimeError('these checks require MPS without CPU fallback')
        cls.dev=torch.device('mps');cls.plan=prepare_plan()
        cls.events=torch.zeros((2,3,16,3),dtype=torch.int32)
        # Both inputs have a key-1 P1 with the same value as a key-0 P0.
        for graph in range(2):
            cls.events[graph,0,:3]=torch.tensor([[1,0,5],[2,1,5],[3,2,7]])
            cls.events[graph,1,:2]=torch.tensor([[1,0,5],[3,0,4]])
        cls.events[0,2,0]=torch.tensor([2,0,5]);cls.events=cls.events.to(cls.dev)
        cls.seal=torch.zeros((2,3,4),device=cls.dev,dtype=torch.bool)
        cls.seal[:,2,3]=True
        cls.seal[1,1,0]=True

    def test_exact_early_work_same_boundary_witness(self):
        local,t=run_engine(self.events,self.seal,plan=self.plan)
        barrier,b=run_engine(self.events,self.seal,'barrier',plan=self.plan)
        for key in ('public_rows','witness','public','pending','sealed_absent','parent_version'):
            torch.testing.assert_close(local[key],barrier[key],atol=0,rtol=0)
        self.assertFalse(t['public'][:,:3].any().item());self.assertFalse(b['computed'][:,:3].any().item())
        self.assertFalse(t['public_rows'][:,:3].ne(-1).any().item())
        self.assertFalse(t['early'].any().item());self.assertFalse(t['input_fault'].any().item())
        # U at wave 0 and wave 1 are consumed without waiting for P1. Duplicate
        # P0(0,5) remains bound to the first source Run and wakes no new use.
        self.assertEqual(local['first_fired_tick'][0,1].tolist(),[1,-1,0,-1])
        self.assertEqual(local['first_fired_tick'][0,0].tolist(),[2,-1,-1,-1])
        self.assertEqual(local['receipt_count'][0,0,0].item(),2)
        self.assertEqual(local['witness'][0,0,0].tolist(),[[1,0,5,0],[2,0,5,2]])
        self.assertEqual(local['public_rows'][0,0,0].tolist(),[0,5,5])
        self.assertFalse(local['public'][1,0,0].item())
        self.assertTrue(local['sealed_absent'][1,0,0].item())
        self.assertTrue(local['pending_open'][1,0,1].item())
        self.assertFalse((t['fired'].int().sum(1)>1).any().item())

    def test_raw_guard_and_exact_drain(self):
        high=torch.ones((2,4,2,4),device=self.dev,dtype=torch.bool)
        raw,r=run_engine(self.events,self.seal,'raw',proposals=high,plan=self.plan)
        self.assertTrue(r['early'][0,0,0,0].item());self.assertEqual(raw['witness'][0,0,0,1].tolist(),[-1]*4)
        self.assertEqual(raw['public_rows'][0,0,0].tolist(),[0,5,-1])
        guarded,g=run_engine(self.events,self.seal,'guarded',proposals=high,plan=self.plan)
        self.assertFalse(g['early'].any().item());self.assertEqual(guarded['witness'][0,0,0,1].tolist(),[2,0,5,2])
        low=torch.zeros_like(high);miss,_=run_engine(self.events,self.seal,'guarded',proposals=low,plan=self.plan)
        self.assertFalse(miss['computed'].any().item());self.assertTrue(miss['withheld'][0,0,0].item())
        fixed,trace=run_engine(self.events,self.seal,'guarded_drain',proposals=low,plan=self.plan)
        torch.testing.assert_close(fixed['public_rows'],guarded['public_rows'])
        self.assertTrue(fixed['drained'][0,0,0].item());self.assertFalse(trace['drained'][:,:3].any().item())

    def test_prefix_sensitivity_callback_and_epoch(self):
        seen=[]
        def policy(tick,wave):
            seen.append((tick,None if wave is None else wave.clone()))
            return torch.ones((2,2,4),device=self.dev,dtype=torch.bool)
        stream=ReadinessEngine(2,'guarded',plan=self.plan)
        with self.assertRaises(ValueError):stream.finish(self.seal,proposal_fn=policy)
        with self.assertRaises(ValueError):stream.step(self.events[:,0],proposal=torch.ones((1,1),device=self.dev))
        self.assertEqual(stream.tick,0)
        frames=[stream.step(self.events[:,t],proposal_fn=policy) for t in range(3)]
        final=stream.finish(self.seal,proposal_fn=policy);self.assertEqual(stream.tick,4)
        self.assertEqual([t for t,_ in seen],[0,1,2,3]);self.assertIsNone(seen[3][1]);
        for t in range(3):torch.testing.assert_close(seen[t][1],self.events[:,t],rtol=0,atol=0)
        # Later state may diverge. Before the sole differing publication all
        # recorded per-graph fields must coincide, and early snapshots stay frozen.
        for frame in frames[:2]:
            for key,value in frame.items():
                if key!='tick':torch.testing.assert_close(value[0],value[1],rtol=0,atol=0)
        self.assertEqual(final['receipt_count'][0,0,0].item(),2)
        self.assertEqual(frames[0]['receipt_count'][0,0,0].item(),1)
        self.assertEqual(frames[1]['parent_version'][0,1,0].item(),0)
        self.assertEqual(frames[2]['parent_version'][0,1,0].item(),3)
        with self.assertRaises(ValueError):stream.finish(self.seal,proposal_fn=policy)

    def test_minimal_barrier_and_zero_dispatch_endpoint(self):
        regular = ReadinessEngine(2,'barrier',False,plan=self.plan)
        minimal = ReadinessEngine(2,'barrier_min',False,plan=self.plan)
        traced = ReadinessEngine(2,'barrier_min',True,plan=self.plan)
        with self.assertRaises(ValueError):
            minimal.endpoint()
        for t in range(3):
            regular.step(self.events[:,t]); minimal.step(self.events[:,t])
            frame = traced.step(self.events[:,t])
            self.assertFalse(frame['computed'].any().item())
            for key in ('ready','pending','parent_live'):
                torch.testing.assert_close(frame[key],regular.snapshot()[key])
        self.assertEqual(minimal.dispatch_counts,dict(ingest=3,advance=0,diagnostic_advance=0))
        for engine in (regular,minimal,traced):
            engine.finish(self.seal)
        self.assertEqual(minimal.dispatch_counts,dict(ingest=3,advance=1,diagnostic_advance=0))
        self.assertEqual(regular.dispatch_counts,dict(ingest=3,advance=4,diagnostic_advance=0))
        self.assertEqual(traced.dispatch_counts,regular.dispatch_counts)
        for name,actual in minimal.endpoint().items():
            torch.testing.assert_close(actual,regular.endpoint()[name],rtol=0,atol=0)
            torch.testing.assert_close(actual,traced.endpoint()[name],rtol=0,atol=0)
            expected = regular.result()
            target = expected['first_early_tick']>=0 if name=='early_execution' else expected[name]
            torch.testing.assert_close(actual,target,rtol=0,atol=0)
        # Endpoint rows are the actual released storage, with no final cloning.
        self.assertEqual(minimal.endpoint()['public_rows'].untyped_storage().data_ptr(),
                         minimal.consumers.untyped_storage().data_ptr())

    def test_ask_for_minimal_intermediate_snapshot(self):
        baseline = ReadinessEngine(2,'barrier',True,plan=self.plan)
        fast = ReadinessEngine(2,'barrier_min',False,plan=self.plan)
        for t in range(3):
            fast.step(self.events[:,t]); reference=baseline.step(self.events[:,t])
            snapshot=fast.snapshot()
            for name in ('parent_value','parent_first_tick','ready','runnable','computed','pending','public'):
                torch.testing.assert_close(snapshot[name],reference[name])
        self.assertEqual(fast.dispatch_counts,dict(ingest=3,advance=0,diagnostic_advance=3))

    def test_compact_endpoint_matches_learned_diagnostics(self):
        for mode in ('raw','guarded','guarded_drain','local'):
            engine = ReadinessEngine(2,mode,False,plan=self.plan)
            high = torch.ones((2,2,4),device=self.dev,dtype=torch.bool)
            opt = {} if mode=='local' else {'proposal':high if mode=='raw' else ~high}
            for t in range(3):engine.step(self.events[:,t],**opt)
            engine.finish(self.seal,**opt)
            detailed=engine.result()
            for name,actual in engine.endpoint().items():
                expected=detailed['first_early_tick']>=0 if name=='early_execution' else detailed[name]
                torch.testing.assert_close(actual,expected,rtol=0,atol=0)

    def test_rhs_projection_and_invalid_input_flag(self):
        # Keep parent binding/policy fixed; change the compiled output operands.
        # This distinguishes a real device projection from a precomputed answer record.
        import tempfile
        source=json.loads(DEFAULT_PLAN.read_bytes())
        c=next(r for r in source['rules'] if r['table']=='C');c['outputs']=[[0,0],[1,1],[0,1]]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'permuted.json';path.write_text(json.dumps(source));plan=prepare_plan(path)
        events=self.events.clone();events[0,2,0,2]=7
        expected,_=run_engine(events,self.seal,plan=self.plan,trace=False)
        changed,_=run_engine(events,self.seal,plan=plan,trace=False)
        torch.testing.assert_close(changed['witness'],expected['witness'])
        self.assertEqual(expected['public_rows'][0,0,0].tolist(),[0,5,7])
        self.assertEqual(changed['public_rows'][0,0,0].tolist(),[0,7,5])
        events[0,1,0,2]=1 # conflicting value for the same producer/key
        invalid,_=run_engine(events,self.seal,plan=self.plan,trace=False)
        self.assertEqual(invalid['input_fault'].tolist(),[True,False])


if __name__=='__main__':
    unittest.main()
