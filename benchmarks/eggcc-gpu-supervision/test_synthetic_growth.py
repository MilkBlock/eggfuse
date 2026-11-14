import unittest
from audit_synthetic_growth import audit
from reference_union_family import Reference
from device_snapshot_import import identity


class Growth(unittest.TestCase):
    def fixture(self,productive):
        eq=dict(kind='eq',name='E')
        rule=dict(query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)])],
            effects=[dict(kind='construct',call=dict(table='F'),args=[dict(slot=1)],dst=2)] if productive else [])
        recipe=dict(tables=[dict(name='F',kind='constructor',schema=[eq,eq])],rules=[rule])
        values=[dict(sort='E',eq=str(i)) for i in range(2)]
        ref=Reference(recipe,[dict(table='F',values=values)],{identity(v):i for i,v in enumerate(values)})
        return recipe,ref

    def test_growth_budget_is_not_fixedpoint_or_nontermination_proof(self):
        recipe,ref=self.fixture(True)
        result=audit(recipe,ref,3,100)
        self.assertEqual(result['status'],'round_budget')
        self.assertEqual([r['new_constructors'] for r in result['logs']],[1,1,1])
        self.assertEqual(len(ref.facts),1)
        self.assertEqual(audit(recipe,ref,8,3)['status'],'fact_budget')

    def test_exact_quiescence(self):
        recipe,ref=self.fixture(False)
        result=audit(recipe,ref,3,100)
        self.assertEqual(result['status'],'fixedpoint')
        self.assertEqual(len(result['logs']),1)


if __name__=='__main__':unittest.main()
