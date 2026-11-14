import unittest
import numpy as np
import mlx.core as mx
from lower_query_literals import lower
from device_snapshot_import import prepare_family
from device_query_join import compile_query,match
from audit_snapshot_queries import device

class QueryLiterals(unittest.TestCase):
    def test_exact_guard_precedes_bounded_compaction(self):
        for target in [1,(1<<60)+3]:
            i=dict(kind='i64',name='i64');e=dict(kind='eq',name='E')
            recipe=dict(tables=[dict(name='F',kind='constructor',schema=[i,e])],rules=[dict(slots=[dict(sort=e,definition='query')],query=[dict(call=dict(table='F'),args=[dict(literal=target,sort=i),dict(slot=0)])],effects=[])])
            rows=[dict(table='F',subsumed=False,values=[dict(sort='i64',value=n),dict(sort='E',eq=str(n))]) for n in [0,target]]
            local,state,ids,_=prepare_family(lower(recipe),dict(rows=rows),[0],4)
            plan=compile_query(local,0);dp=device(plan);ds=device(state)
            b=mx.compile(lambda s:match(s,dp,1,mx.array(True),mx.array(True),mx))(ds);mx.eval(b)
            self.assertTrue(bool(b['complete']));self.assertFalse(bool(b['overflow']));self.assertEqual(int(np.sum(np.array(b['live']))),1)
            self.assertEqual(int(b['slots'][0,1]),ids['{"sort":"i64","value":'+str(target)+'}'])
            # An absent literal must not match another scalar or overflow.
            local['literal_ids']={};dp=device(compile_query(local,0))
            b=mx.compile(lambda s:match(s,dp,1,mx.array(True),mx.array(True),mx))(ds);mx.eval(b)
            self.assertEqual(int(np.sum(np.array(b['live']))),0);self.assertTrue(bool(b['complete']))
if __name__=='__main__':unittest.main()
