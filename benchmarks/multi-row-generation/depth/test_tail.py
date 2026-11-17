import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task import generate
from train import tail_graphs
from probe import reference

class TailTests(unittest.TestCase):
    def test_new_tail_contract_and_final_stationary_endpoint(self):
        d=tail_graphs(8,2,8,31817);p,f=reference(d['a'],d['b'],12)
        for g in range(8):
            edge={int(row[0]):int(row[1]) for row in d['b'][g]}
            roots=[k for k,v in edge.items() if k==v];self.assertEqual(len(roots),1)
            lengths=[]
            for start in edge:
                at=start;steps=0
                while at!=roots[0]:at=edge[at];steps+=1;self.assertLess(steps,17)
                lengths.append(steps)
            self.assertEqual(sorted(lengths),list(range(16)))
            self.assertTrue(np.all(f[4:,g,:,1]==roots[0]))

if __name__=='__main__':unittest.main()
