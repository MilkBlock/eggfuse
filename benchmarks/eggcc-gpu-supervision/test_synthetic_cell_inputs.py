import copy,unittest
from synthetic_cell_inputs import generate,oracle,validate,digest,select_recipe


def recipe():
    eq=dict(kind='eq',name='E')
    atom=lambda t,*ss:dict(call=dict(table=t),args=[dict(slot=s) for s in ss])
    return dict(tables=[dict(name='F',kind='constructor',schema=[eq,eq])],rules=[dict(
        metadata=dict(source_set='test'),slots=[dict(sort=eq,definition='query') for _ in range(3)],
        query=[atom('F',0,1),atom('F',1,2)],effects=[dict(kind='union',args=[dict(slot=1),dict(slot=2)])])])


class SyntheticInputs(unittest.TestCase):
    def test_replay_canonical_seed_and_oracle(self):
        r=recipe();snap=generate(r,17,3)
        self.assertEqual(snap,generate(r,17,3))
        result=oracle(r,snap)
        self.assertEqual(result['runs'][-1]['new_equivalences'],0)
        self.assertEqual(result['runs'][-1].get('new_constructors',0),0)
        doc=dict(schema='synthetic-cell-input/v1',recipe=r,snapshot=snap,recipe_sha256=digest(r),input_sha256=digest(snap),generator=dict(seed=17,fragments=3,reuse=.35))
        self.assertEqual(validate(doc),(r,snap))
        bad=copy.deepcopy(doc);bad['generator']['seed']=90
        with self.assertRaises(ValueError):validate(bad)
        bad=copy.deepcopy(doc);bad['snapshot']['rows'][0]['values'][0]['eq']='tampered'
        with self.assertRaises(ValueError):validate(bad)

    def test_only_definitions_used_and_unsupported_types_rejected(self):
        r=recipe();source=dict(r,runs=['do not use'],boundaries=['do not use'])
        self.assertEqual(select_recipe(source,[0]),r)
        bad=copy.deepcopy(r);bad['rules'][0]['slots'][0]['sort']=dict(kind='string',name='String')
        with self.assertRaises(ValueError):generate(bad,1)
        with self.assertRaises(ValueError):generate(r,1,0)
        with self.assertRaises(ValueError):generate(r,1,reuse=2)

    def test_seed_aliasing_changes_completion_not_only_numbering(self):
        r=recipe()
        distinct=generate(r,1,1,reuse=0)
        shared=generate(r,1,1,reuse=1)
        self.assertGreater(oracle(r,distinct)['unions'],0)
        self.assertEqual(oracle(r,shared)['unions'],0)
        self.assertNotEqual(len(distinct['rows']),len(shared['rows']))

if __name__=='__main__':unittest.main()
