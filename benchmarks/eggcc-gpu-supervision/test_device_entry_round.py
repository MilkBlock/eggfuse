import unittest
import numpy as np
import mlx.core as mx
import test_device_entry_transition as entry_test
from device_entry_round import run_round,run_rounds


class EntryRound(unittest.TestCase):
    def fixture(self):
        s,p,f,c,m=entry_test.EntryTransition().fixture()
        # Leave room for simultaneous branches and a next-round continuation.
        for key,value in list(s.items()):
            pad=np.zeros((2,)+value.shape[1:],value.dtype)
            if key in ('slots','slot_roots','keys'):pad.fill(-1)
            s[key]=np.concatenate([value,pad],axis=0)
        return s,p,f,c,m

    def test_all_entries_read_same_snapshot_and_new_tokens_feed_next_round(self):
        s,p,f,c,m=self.fixture()
        second={k:v.copy() for k,v in p.items()};second['consumer'][0]=2
        later={k:v.copy() for k,v in p.items()};later['producer'][0]=1;later['consumer'][0]=3
        later['projection'][0]=[0,1]
        blocks=[(p,f,c),(second,f,c),(later,f,c)]
        out,mark=run_round(s,blocks,m,np.array(0),np)
        self.assertEqual(mark['new_tokens'],2)
        self.assertEqual(set(out['keys'][out['present'],0]),{0,1,2})
        out,mark=run_round(out,blocks,m,np.array(0),np)
        self.assertEqual(mark['new_tokens'],1)
        self.assertEqual(set(out['keys'][out['present'],0]),{0,1,2,3})
        if mx.metal.is_available():
            dev=lambda d:{k:mx.array(v) for k,v in d.items()}
            db=[tuple(dev(d) for d in block) for block in blocks];dm=dev(m)
            result,marks=mx.compile(lambda state:run_rounds(state,db,dm,mx.array(0),3,mx))(dev(s));mx.eval(result,marks)
            self.assertEqual(np.array(marks['new_tokens']).tolist(),[2,1,0])
            np.testing.assert_array_equal(np.array(result['keys']),out['keys'])

    def test_joint_competitors_cannot_each_transfer_same_owner(self):
        s,p,f,c,m=self.fixture();p['transfer_covered'][0]=True
        second={k:v.copy() for k,v in p.items()};second['consumer'][0]=2
        out,mark=run_round(s,[(p,f,c),(second,f,c)],m,np.array(0),np)
        self.assertEqual(mark['new_tokens'],2);self.assertFalse(mark['transferred'].any())
        self.assertTrue(out['active'][0])

    def test_duplicate_entries_and_budget_do_not_claim_saturation(self):
        s,p,f,c,m=self.fixture()
        out,mark=run_round(s,[(p,f,c),(p,f,c)],m,np.array(0),np)
        self.assertEqual(mark['new_tokens'],1)
        self.assertEqual(mark['duplicate'].sum(),1)
        _,marks=run_rounds(s,[(p,f,c)],m,np.array(0),1,np)
        self.assertTrue(marks['last_round_admitted'])
        with self.assertRaises(ValueError):run_round(s,[],m,np.array(0),np)


if __name__=='__main__':unittest.main()
