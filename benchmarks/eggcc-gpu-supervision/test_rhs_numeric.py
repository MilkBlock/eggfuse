import unittest
import mlx.core as mx
import numpy as np
from rhs_tokens import compile_rule
from rhs_numeric import build, ready


class NumericDataflow(unittest.TestCase):
    def execute(self,name,rows):
        sort=dict(name='i64',kind='i64')
        rule=dict(slots=[dict(definition='query',sort=sort)]*2,effects=[
            dict(kind='compute',dst=2,sort=sort,call={'primitive':name},args=[{'slot':0},{'slot':1}])])
        plan=compile_rule(rule);_,kernel=build(plan,ready(plan))
        value,valid=kernel(mx.array(rows,dtype=mx.float32));mx.eval(value,valid)
        return np.array(value)[:,0],np.array(valid)[:,0]

    def test_arithmetic_and_boolean_kernels(self):
        for op,expected in [('+',[-7,11]),('-',[-11,7]),('*',[-18,18]),
                            ('/',[-4,4]),('max',[2,9]),('min',[-9,2]),
                            ('bool-<',[1,0]),('and',[1,1]),('or',[1,1])]:
            with self.subTest(op=op):
                value,valid=self.execute(op,[[-9,2],[9,2]])
                np.testing.assert_array_equal(value,expected)
                self.assertTrue(valid.all())

    def test_division_failure_and_output_overflow_are_marked(self):
        _,valid=self.execute('/',[[1,0]])
        self.assertFalse(valid[0])
        _,valid=self.execute('*',[[2**20,2**20]])
        self.assertFalse(valid[0])

    def test_unresolved_table_result_is_not_numeric_input(self):
        sort=dict(name='i64',kind='i64')
        plan=compile_rule(dict(slots=[],effects=[
            dict(kind='construct',dst=0,sort=sort,call={'table':'f'},args=[]),
            dict(kind='compute',dst=1,sort=sort,call={'primitive':'+'},
                 args=[{'slot':0},{'literal':1,'sort':sort}])]))
        self.assertEqual(ready(plan),[])


if __name__=='__main__':
    mx.set_default_device(mx.gpu)
    unittest.main()
