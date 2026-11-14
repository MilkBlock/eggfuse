import copy,unittest
from synthetic_context_density import document
from synthetic_cell_inputs import validate,provenance,digest


def recipe():
    e=dict(kind='eq',name='E');c=dict(kind='eq',name='C');i=dict(kind='i64',name='i64')
    rule=dict(slots=[dict(sort=s,definition='query') for s in (e,i,e,c,e)],query=[dict(call=dict(table='Project'),args=[dict(slot=s) for s in (0,1,2)]),dict(call=dict(table='Wrap'),args=[dict(slot=s) for s in (3,2,4)])],effects=[])
    return dict(tables=[dict(name='Project',kind='constructor',schema=[e,i,e]),dict(name='Wrap',kind='constructor',schema=[c,e,e])],rules=[rule])


class ContextDensity(unittest.TestCase):
    def test_replay_distinguishes_joint_connection_from_marginals(self):
        r=recipe();docs=[document(r,0,v,4,3) for v in ('linked','other_context','other_result','absent')]
        self.assertEqual(len({d['input_sha256'] for d in docs}),4)
        for d in docs:
            self.assertEqual(validate(d),(r,d['snapshot']))
            self.assertTrue(provenance(d)['synthetic_input'])
        self.assertEqual([len(d['snapshot']['rows']) for d in docs],[7,7,7,6])
        linked=docs[0]['snapshot']['rows']
        self.assertTrue(any(row['table']=='Wrap' and row['values'][0]['eq']=='context' and row['values'][2]['eq']=='input' for row in linked))
        for d in docs[1:]:
            self.assertFalse(any(row['table']=='Wrap' and row['values'][0]['eq']=='context' and row['values'][2]['eq']=='input' for row in d['snapshot']['rows']))
        bad=copy.deepcopy(docs[0]);bad['generator']['neighbors']=5
        with self.assertRaises(ValueError):validate(bad)
        bad=copy.deepcopy(docs[0]);bad['snapshot']['rows'].pop();bad['input_sha256']=digest(bad['snapshot'])
        with self.assertRaises(ValueError):validate(bad)

    def test_typed_template_and_scalar_limits(self):
        r=recipe()
        for kwargs in [dict(variant='unknown',neighbors=0,scalar=0),dict(variant='linked',neighbors=-1,scalar=0),dict(variant='linked',neighbors=0,scalar=2**63)]:
            with self.assertRaises(ValueError):document(r,0,**kwargs)
        bad=copy.deepcopy(r);bad['rules'][0]['query'][1]['args'][1]['slot']=0
        with self.assertRaises(ValueError):document(bad,0,'linked',0,0)

if __name__=='__main__':unittest.main()
