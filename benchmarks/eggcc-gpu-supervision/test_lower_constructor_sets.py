import unittest
from copy import deepcopy
from lower_constructor_sets import lower
from reference_union_family import Reference,compare_graph
from device_snapshot_import import identity


class ConstructorSets(unittest.TestCase):
    def fixture(self,existing=False):
        sort=dict(kind='eq',name='E')
        tables=[dict(name=t,kind='constructor',schema=[sort,sort]) for t in ('F','H')]
        rule=dict(slots=[dict(sort=sort,definition='query') for _ in range(2)],query=[dict(call=dict(table='H'),args=[dict(slot=0),dict(slot=1)])],
            effects=[dict(kind='set',call=dict(table='F'),args=[dict(slot=0)],value=dict(slot=1))])
        values=[dict(sort='E',eq=str(i)) for i in range(3)];ids={identity(v):i for i,v in enumerate(values)}
        rows=[dict(table='H',values=values[:2])]
        if existing:rows.append(dict(table='F',values=[values[0],values[2]]))
        return dict(tables=tables,rules=[rule]),rows,ids

    def test_native_set_and_lowered_construct_union_agree(self):
        for existing in (False,True):
            recipe,rows,ids=self.fixture(existing);old=deepcopy(recipe);new,sites=lower(recipe)
            self.assertEqual(recipe,old);self.assertEqual(len(sites),1)
            a=Reference(recipe,rows,ids);b=Reference(new,rows,ids)
            la=a.saturate(recipe['rules']);lb=b.saturate(new['rules'])
            self.assertEqual([r['applications'] for r in la],[r['applications'] for r in lb])
            actual=[(t,v[:-1],v[-1]) for t,v in b.facts]
            self.assertTrue(compare_graph(a,actual,b.partition(),len(ids))['passed'])
            if not existing:self.assertEqual(len(b.parent),len(a.parent)+1)

    def test_mutable_not_lowered_and_wrong_types_rejected(self):
        recipe,_,_=self.fixture();recipe['tables'][0]['kind']='function'
        new,sites=lower(recipe);self.assertEqual(new,recipe);self.assertEqual(sites,[])
        recipe['tables'][0]['kind']='constructor';recipe['rules'][0]['slots'][1]['sort']={'kind':'eq','name':'Other'}
        with self.assertRaises(ValueError):lower(recipe)

    def test_partition_audit_rejects_missing_union_and_false_merge(self):
        recipe,rows,ids=self.fixture(True);ref=Reference(recipe,rows,ids);ref.saturate(recipe['rules'])
        facts=[(t,v[:-1],v[-1]) for t,v in ref.facts]
        self.assertIn('missing_union',compare_graph(ref,facts,[0,1,2],3)['errors'])
        self.assertIn('inconsistent_result_class',compare_graph(ref,facts,[0,0,0],3)['errors'])

if __name__=='__main__':unittest.main()
