import unittest
from finite_entry_domain import input_cases,boundary_contexts
from reference_union_family import Reference
from device_snapshot_import import identity


class Domain(unittest.TestCase):
    def fixture(self):
        eq=dict(kind='eq',name='E')
        atom=lambda t,a,b:dict(call=dict(table=t),args=[dict(slot=a),dict(slot=b)])
        rule=dict(slots=[dict(sort=eq,definition='query') for _ in range(3)],query=[atom('F',0,1),atom('G',1,2)],effects=[])
        recipe=dict(tables=[dict(name=t,kind='constructor',schema=[eq,eq]) for t in ('F','G')],rules=[rule])
        ids={identity(dict(sort='E',eq=str(i))):i for i in range(2)}
        ref=Reference(recipe,[],ids);ref.construct('F',[0],1)
        return recipe,rule,ref

    def test_three_inputs_have_all_five_partitions(self):
        _,rule,_=self.fixture();cases=input_cases(rule)
        self.assertEqual(len(cases),5)
        self.assertEqual(len({tuple(c[i]['eq'] for i in range(3)) for c in cases}),5)
        with self.assertRaises(ValueError):input_cases(rule,limit=4)

    def test_boundary_includes_both_existing_classes_and_one_fresh_class(self):
        _,rule,ref=self.fixture()
        cases=list(boundary_contexts(ref,rule,{('F',(0,1)):None}))
        self.assertEqual({b[2] for _,b in cases},{0,1,2})
        for child,bound in cases:self.assertIn(bound,child.matches(rule))
        self.assertEqual(len(ref.parent),2);self.assertEqual(len(ref.facts),1)
        ref.construct('G',[1],0)
        reduced=list(boundary_contexts(ref,rule,{('F',(0,1)):None}))
        self.assertEqual(len(reduced),1);self.assertEqual(reduced[0][1][2],0)

    def test_scalar_and_budget_boundaries_are_explicit(self):
        _,rule,ref=self.fixture()
        with self.assertRaises(ValueError):list(boundary_contexts(ref,rule,{('F',(0,1)):None},limit=1))
        rule['slots'][2]['sort']=dict(kind='i64',name='i64')
        with self.assertRaises(ValueError):input_cases(rule)
        with self.assertRaises(ValueError):list(boundary_contexts(ref,rule,{('F',(0,1)):None}))


if __name__=='__main__':unittest.main()
