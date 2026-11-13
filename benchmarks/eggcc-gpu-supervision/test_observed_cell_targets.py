import copy
import unittest
from observed_cell_targets import instantiate,equality_audit
from test_cell_token_successors import rule,atom,make,TABLES


def binding(roots,after=None):
    return dict(values=[dict(slot=i,value=dict(sort='E',eq='opaque')) for i in range(len(roots))],eq_ports=[dict(slot=i,sort='E',before=v,after=(after or roots)[i]) for i,v in enumerate(roots)])


class Observed(unittest.TestCase):
    def test_physical_identity_renaming_preserves_inputs(self):
        r=rule([atom('F',0,1)],[make('G',2,1)])
        a,_=instantiate(r,binding([100,200]),TABLES)
        b,_=instantiate(r,binding([900,700]),TABLES)
        self.assertEqual(a,b)

    def test_actual_pre_run_partition_changes_input(self):
        r=rule([atom('F',0,1)],[make('G',2,1)])
        a,_=instantiate(r,binding([100,200]),TABLES)
        b,_=instantiate(r,binding([100,100]),TABLES)
        self.assertNotEqual(a['source'],b['source'])

    def test_post_run_labels_never_enter_features(self):
        r=rule([atom('F',0,1)],[dict(kind='union',args=[dict(slot=0),dict(slot=1)])])
        good=binding([100,200],[100,100]);bad=binding([100,200],[100,200])
        a,_=instantiate(r,good,TABLES);b,_=instantiate(r,bad,TABLES)
        self.assertEqual(a,b)
        self.assertEqual(equality_audit(a,good),(1,0))
        self.assertEqual(equality_audit(b,bad),(1,1))

    def test_missing_audit_port_is_not_inferred_from_value_string(self):
        r=rule([atom('F',0,1)],[]);b=binding([100,200]);b['eq_ports'].pop()
        with self.assertRaisesRegex(ValueError,'missing audited'):instantiate(r,b,TABLES)

    def test_scalar_inputs_are_preserved(self):
        r=rule([atom('F',0,1)],[make('G',2,1)])
        r['slots'][0]['sort']=dict(name='i64',kind='i64')
        a=binding([100,200]);a['eq_ports']=a['eq_ports'][1:]
        a['values'][0]['value']=dict(sort='i64',value=2)
        b=copy.deepcopy(a);b['values'][0]['value']['value']=3
        first,_=instantiate(r,a,TABLES);second,_=instantiate(r,b,TABLES)
        self.assertNotEqual(first['source'],second['source'])


if __name__=='__main__':unittest.main()
