import unittest
from synthetic_result_ownership import result_context
from synthetic_cell_inputs import oracle,generate,validate,digest


def fixture():
    sort=dict(kind='eq',name='E')
    r=dict(tables=[dict(name=t,kind='constructor',schema=[sort,sort]) for t in ('F','G')],rules=[dict(
        slots=[dict(sort=sort,definition='query') for _ in range(2)],metadata=dict(source_set='test'),
        query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)])],
        effects=[dict(kind='set',call=dict(table='G'),args=[dict(slot=0)],value=dict(slot=1))])])
    return r


class ResultOwnership(unittest.TestCase):
    def test_existing_equal_and_distinct_preserve_real_effects(self):
        r=fixture();base=generate(r,5,1,0.)
        outcomes={}
        for mode in ('absent','equal','distinct'):
            s,e=result_context(r,base,0,mode);label=oracle(r,s);outcomes[mode]=label
            self.assertEqual(e['already_equal'],mode=='equal')
            doc=dict(schema='synthetic-cell-input/v1',recipe=r,snapshot=s,recipe_sha256=digest(r),input_sha256=digest(s),generator=dict(seed=5,fragments=1,reuse=0.,result_context=dict(rule=0,mode=mode)))
            self.assertEqual(validate(doc),(r,s))
        self.assertEqual(outcomes['absent']['runs'][0]['new_constructors'],1)
        self.assertEqual(outcomes['equal']['unions'],0)
        self.assertEqual(outcomes['distinct']['unions'],1)
        self.assertNotIn('new_constructors',outcomes['distinct']['runs'][0])

    def test_existing_key_and_invalid_mode_rejected(self):
        r=fixture();base=generate(r,5,1,0.);seed,_=result_context(r,base,0,'equal')
        with self.assertRaises(ValueError):result_context(r,seed,0,'distinct')
        with self.assertRaises(ValueError):result_context(r,base,0,'unknown')

if __name__=='__main__':unittest.main()
