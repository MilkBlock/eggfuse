import unittest,json
import numpy as np
from reference_union_family import Reference,compare_graph
from device_snapshot_import import eq_registry,identity


def value(i,sort='E'):return dict(sort=sort,eq=str(i))
def atom(t,args):return dict(call=dict(table=t),args=[dict(slot=s) for s in args])

class UnionReference(unittest.TestCase):
    def test_duplicate_constructor_boundary_is_not_a_local_value_error(self):
        vals=[value(0),value(1)];ids={identity(v):i for i,v in enumerate(vals)}
        ref=Reference({},[dict(table='F',values=vals)],ids)
        result=compare_graph(ref,[('F',(0,),1),('F',(0,),2)],np.arange(3),1)
        self.assertEqual(result['errors'],['missing_union'])
        self.assertEqual(result['missing_union_classes'],[dict(expected=1,actual=[1,2])])
        self.assertEqual(result['duplicate_constructor_results'],[dict(table='F',args=[0],results=[1,2])])
        repaired=compare_graph(ref,[('F',(0,),1),('F',(0,),2)],np.array([0,1,1]),1)
        self.assertTrue(repaired['passed'])

    def fixture(self):
        vals=[value(i) for i in range(6)];ids={identity(v):i for i,v in enumerate(vals)}
        rows=[dict(table=t,values=[vals[a],vals[b]]) for t,a,b in [('F',0,2),('F',1,3),('G',2,4),('G',3,5),('Link',0,1)]]
        rule=dict(query=[atom('Link',[0,1])],effects=[dict(kind='union',args=[dict(slot=0),dict(slot=1)])])
        return Reference({},rows,ids),rule,ids

    def test_no_new_fact_does_not_mean_saturation(self):
        ref,r,ids=self.fixture();logs=ref.saturate([r])
        self.assertEqual([x['new_equivalences'] for x in logs],[3,0])
        self.assertEqual(ref.partition(),[0,0,2,2,4,4])
        self.assertEqual(len(ref.normalized_facts()),3)

    def test_union_enables_later_join(self):
        ref,r,ids=self.fixture()
        later=dict(query=[atom('Link',[0,1]),atom('F',[0,2]),atom('F',[1,2])],effects=[])
        self.assertEqual(ref.matches(later),[])
        ref.apply([r]);self.assertEqual(len(ref.matches(later)),1)

    def test_typed_registry_and_invalid_seed_namespace(self):
        _,_,ids=self.fixture();ids[identity(dict(sort='i64',value=4))]=len(ids)
        registry=eq_registry(ids,['E'],2)
        self.assertEqual(registry['sorts'].tolist(),[0]*6+[-1]*3)
        with self.assertRaises(ValueError):eq_registry(ids,[])
        with self.assertRaises(ValueError):eq_registry({'{}':2},[])
        ref,_,_=self.fixture();ref.types[1]='Other'
        with self.assertRaises(ValueError):ref.merge(0,1)

if __name__=='__main__':unittest.main()
