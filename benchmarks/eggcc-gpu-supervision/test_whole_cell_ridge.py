import unittest
import numpy as np
from whole_cell_ridge import encode,request
from test_cell_token_successors import rule,atom,make


class WholeCell(unittest.TestCase):
    def test_code_does_not_change_with_duplicate_derivations(self):
        f=[('F',(('input',0),('input',1)))]
        np.testing.assert_array_equal(encode(f),encode(f+f))

    def test_opaque_local_renaming_does_not_change_code(self):
        a=[('F',(('input',0),('input',1))),('G',(('input',1),('result',2)))]
        b=[('F',(('foreign',999),('foreign',1000))),('G',(('foreign',1000),('other',872)))]
        np.testing.assert_array_equal(encode(a),encode(b))

    def test_request_does_not_use_target_or_source_set_labels(self):
        r=rule([atom('F',0,1)],[make('G',2,1)],2);a=request(r,[(0,('input',0)),(1,('input',1))])
        r['metadata']['source_set']='arbitrary';b=request(r,[(0,('anything',50)),(1,('anything',70))])
        np.testing.assert_array_equal(a,b)

if __name__=='__main__':unittest.main()
