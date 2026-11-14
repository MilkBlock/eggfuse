import unittest
from reference_family_schedule import execute
from reference_union_family import Reference
from device_snapshot_import import identity


class FamilySchedule(unittest.TestCase):
    def fixture(self):
        e=dict(kind='eq',name='E')
        rules=[]
        for stage,src,dst in [('a','F','G'),('b','G','H')]:
            rules.append(dict(metadata=dict(source_set=stage),query=[dict(call=dict(table=src),args=[dict(slot=0),dict(slot=1)])],effects=[dict(kind='construct',call=dict(table=dst),args=[dict(slot=1)],dst=2)]))
        recipe=dict(rules=rules,tables=[dict(name=t,kind='constructor',schema=[e,e]) for t in ['F','G','H']])
        values=[dict(sort='E',eq=str(i)) for i in range(2)]
        return Reference(recipe,[dict(table='F',values=values)],{identity(v):i for i,v in enumerate(values)})

    def test_stage_saturation_and_reverse_order(self):
        r=self.fixture();logs=execute(r,[dict(saturate=dict(run='a')),dict(saturate=dict(run='b'))])
        self.assertEqual([x['stage'] for x in logs],['a','a','b','b'])
        self.assertEqual([x['applications'] for x in logs],[1,1,1,1])
        self.assertIn('H',{t for t,_ in r.facts})
        r=self.fixture();execute(r,[dict(run='b'),dict(run='a')])
        self.assertNotIn('H',{t for t,_ in r.facts})

    def test_budget_and_unknown_ruleset_fail(self):
        with self.assertRaises(ValueError):execute(self.fixture(),dict(saturate=dict(run='a')),budget=1)
        with self.assertRaises(ValueError):execute(self.fixture(),dict(run='missing'))
        r=self.fixture();self.assertEqual(execute(r,dict(repeat=0,body=dict(run='a'))),[])

if __name__=='__main__':unittest.main()
