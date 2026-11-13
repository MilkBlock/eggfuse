import copy
import unittest
from unittest.mock import patch
import numpy as np
from multi_entry_ridge import template, neighborhood_template, input_seed, dataset


def fixture(literal):
    return dict(slots=[dict(sort=dict(kind='eq',name='E'),definition='query') for _ in range(2)],
        query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(literal=literal,sort='i64'),dict(slot=1)])],effects=[])


class NeighborhoodFeatures(unittest.TestCase):
    def test_neighbor_literal_previously_invisible(self):
        a,b=fixture(2),fixture(3)
        np.testing.assert_array_equal(template(a)[0],template(b)[0])
        self.assertFalse(np.array_equal(neighborhood_template(a)[0],neighborhood_template(b)[0]))

    def test_slot_renaming_equivariance(self):
        a=fixture(2);b=copy.deepcopy(a)
        for arg in b['query'][0]['args']:
            if 'slot' in arg:arg['slot']=1-arg['slot']
        ra,qa=neighborhood_template(a);rb,qb=neighborhood_template(b)
        np.testing.assert_allclose(ra,rb[::-1],atol=1e-7)
        np.testing.assert_allclose(qa,qb,atol=1e-7)

    def test_added_columns_preserve_existing_inputs_and_ignore_rhs_labels(self):
        b=dict(rule=0,eq_ports=[dict(slot=i,sort='E',before=i) for i in (0,1)],
               values=[dict(slot=i,value={}) for i in (0,1)],
               rhs=dict(completed=True,slots=[dict(slot=i,value={},eq_port=dict(sort='E',after_run=i)) for i in (0,1)]))
        trace=dict(recipe=dict(rules=[fixture(2)]),runs=[dict(ordinal=1,audit=dict(bindings=[b]))])
        with patch('historical_cell_sources.link_history',return_value=dict(windows=[])):
            old=dataset(trace,4,False,'class-history-earliest')[0]
            new=dataset(trace,4,False,'class-history-neighborhood-input')[0]
            for key in ('seed','target'):np.testing.assert_array_equal(old[key],new[key])
            np.testing.assert_array_equal(old['q'],new['q'][:64])
            self.assertEqual(new['q'].shape,(256,))
            b['rhs']['slots'][1]['eq_port']['after_run']=0
            changed=dataset(trace,4,False,'class-history-neighborhood-input')[0]
            for key in ('seed','q'):np.testing.assert_array_equal(new[key],changed[key])

    def test_only_current_inputs_and_no_numeric_identity(self):
        roles,_=neighborhood_template(fixture(2))
        def b(root):
            return dict(eq_ports=[dict(slot=i,sort='E',before=root) for i in (0,1)],values=[dict(slot=i,value={}) for i in (0,1)])
        np.testing.assert_array_equal(input_seed(b(4),roles,{0},'class-history-neighborhood'),input_seed(b(999),roles,{0},'class-history-neighborhood'))


if __name__=='__main__':unittest.main()
