import unittest
from select_multi_producer_inputs import select

class Selection(unittest.TestCase):
    def test_order_independent_and_excludes_prior(self):
        rows=[dict(producer=[0,1],consumer=2,input_sha256=h) for h in ['c','a','b']]
        a,coverage=select(rows,{'a'},1)
        b,_=select(list(reversed(rows)),{'a'},1)
        self.assertEqual(a,b);self.assertEqual(a[0]['input_sha256'],'b')
        self.assertEqual(coverage[0]['available'],2)
    def test_shared_snapshot_retains_interface_coverage(self):
        rows=[dict(producer=p,consumer=2,input_sha256='a') for p in [[0,1],[1,0]]]
        chosen,coverage=select(rows,set(),1)
        self.assertEqual(len(chosen),1);self.assertEqual(len(coverage),2)
    def test_invalid_limit(self):
        with self.assertRaises(ValueError):select([],set(),0)

if __name__=='__main__':unittest.main()
