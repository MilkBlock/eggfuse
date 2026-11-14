import unittest
from typed_literal import value
from reference_union_family import Reference
from device_snapshot_import import identity

class TypedLiteral(unittest.TestCase):
    def arg(self,n):return dict(literal=n,sort=dict(kind='i64',name='i64'))
    def test_exact_range_and_type(self):
        for n in [0,1,-(1<<63),(1<<63)-1,10000000000000000]:self.assertEqual(value(self.arg(n))['value'],n)
        for n in [True,1.0,1<<63,-(1<<63)-1]:
            with self.assertRaises(ValueError):value(self.arg(n))
    def test_literal_guard_and_effect_use_exact_identity(self):
        e=dict(kind='eq',name='E');i=dict(kind='i64',name='i64')
        recipe=dict(tables=[dict(name='F',kind='constructor',schema=[i,e])])
        vals=[dict(sort='i64',value=0),dict(sort='E',eq='x')]
        r=Reference(recipe,[dict(table='F',values=vals)],{identity(v):j for j,v in enumerate(vals)})
        atom=lambda n:dict(call=dict(table='F'),args=[self.arg(n),dict(slot=0)])
        self.assertEqual(r.matches(dict(query=[atom(1)])),[])
        self.assertEqual(len(r.matches(dict(query=[atom(0)]))),1)
        rule=dict(query=[atom(0)],effects=[dict(kind='construct',call=dict(table='F'),args=[self.arg(10000000000000000)],dst=1)])
        r.apply([rule]);self.assertEqual(len(r.matches(dict(query=[atom(10000000000000000)]))),1)
        self.assertEqual(len(r.scalar_values),2)
        before=len(r.parent);r.apply([rule]);self.assertEqual(len(r.parent),before)
if __name__=='__main__':unittest.main()
