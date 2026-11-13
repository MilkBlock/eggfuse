import unittest
import numpy as np
from audit_generated_constructors import audit,without_rhs_tables
from device_snapshot_import import identity


def fixture():
    rule=dict(slots=[dict(definition='query'),dict(definition='effect'),dict(definition='effect')],query=[dict(call=dict(table='Seed'))],effects=[dict(kind='construct',call=dict(table='F'),args=[dict(slot=0)],dst=1),dict(kind='construct',call=dict(table='G'),args=[dict(slot=1)],dst=2)])
    state=dict(keys=np.array([[0,0],[0,0]],np.int32),slots=np.array([[0,2,1],[0,2,1]],np.int32),slot_roots=np.array([[0,2,1],[0,2,1]],np.int32),slot_valid=np.ones((2,3),bool))
    return rule,state


class GeneratedAudit(unittest.TestCase):
    def test_fresh_ids_can_be_reordered_but_shared_terms_share_ids(self):
        rule,state=fixture();result=audit(rule,[],{'seed':0},state,[0,1],3)
        self.assertTrue(result['passed']);self.assertEqual(result['fresh_terms'],2)
        state['slots'][1,1]=3;state['slot_roots'][1,1]=3
        result=audit(rule,[],{'seed':0},state,[0,1],4)
        self.assertFalse(result['passed']);self.assertGreater(result['wrong'],0)

    def test_aliasing_missing_result_and_unexplained_allocations_fail(self):
        for mode in ('alias','missing','allocation'):
            rule,state=fixture();limit=3
            if mode=='alias':state['slots'][:,2]=2;state['slot_roots'][:,2]=2
            elif mode=='missing':state['slot_valid'][0,1]=False
            else:limit=4
            self.assertFalse(audit(rule,[],{'seed':0},state,[0,1],limit)['passed'],mode)

    def test_query_tables_are_never_removed(self):
        rule,_=fixture();rule['effects'].append(dict(kind='construct',call=dict(table='Seed'),args=[],dst=3))
        snapshot=dict(rows=[dict(table=t) for t in ('Seed','F','G','Unrelated')])
        modified,tables,count=without_rhs_tables(rule,snapshot)
        self.assertEqual(tables,['F','G']);self.assertEqual(count,2)
        self.assertEqual([r['table'] for r in modified['rows']],['Seed','Unrelated'])

    def test_existing_constructor_identity_cannot_be_replaced_by_fresh_one(self):
        rule,state=fixture();a=dict(sort='E',eq='Cell(1)');b=dict(sort='E',eq='Cell(2)')
        rows=[dict(table='F',values=[a,b])];ids={identity(a):0,identity(b):1}
        # The fixture returns fresh 2 for F even though the seed says F(0)=1.
        result=audit(rule,rows,ids,state,[0,1],3)
        self.assertFalse(result['passed']);self.assertEqual(result['wrong'],2)

if __name__=='__main__':unittest.main()
