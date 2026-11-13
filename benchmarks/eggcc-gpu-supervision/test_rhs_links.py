import copy
import unittest
from link_rhs_results import link


def fixture():
    def result(identity,root):
        return dict(slot=1,value={},eq_port=dict(sort='E',identity=identity,at_rhs=identity,after_run=root))
    def producer(identity,root):
        return dict(rule=0,values=[],rhs=dict(completed=True,slots=[result(identity,root)]))
    c=dict(rule=1,values=[dict(slot=0,value={}),dict(slot=1,value={})],
           eq_ports=[dict(slot=0,sort='E',identity=20,before=10),dict(slot=1,sort='E',identity=99,before=99)],
           rhs=dict(completed=True,slots=[]))
    return dict(schema='eggcc-gpu-supervision-rhs-trace/v1',program_sha256='p',
        strict_run_graphs_equal=True,strict_audit_reference_equal=True,run_control_counts_equal=True,
        recipe=dict(rules=[dict(effects=[dict(kind='construct',dst=1)]),dict(effects=[])]),
        steps=[dict(ordinal=i,ruleset='a' if i==1 else 'b',executed_bindings=0 if i==2 else 2,changed=i!=2) for i in (1,2,3)],
        runs=[dict(ordinal=1,audit=dict(bindings=[producer(10,10),producer(20,10)])),
              dict(ordinal=3,audit=dict(bindings=[c,copy.deepcopy(c)]))])


class RhsLinks(unittest.TestCase):
    def test_shared_group_keeps_all_possible_providers_and_boundary(self):
        r=link(fixture());w=r['windows'][0]
        self.assertEqual(len(w['groups']),1)
        self.assertEqual(len(w['groups'][0]['providers']),2)
        self.assertEqual(len(w['consumers']),2)
        self.assertEqual(w['consumers'][0]['external_classes'],1)
        self.assertEqual(w['consumers'][0]['ports'][0]['relation'],'same_identity')
        self.assertEqual(r['counts']['cross_ruleset_consumer_applications'],2)
        self.assertFalse(r['causal_link_proven']);self.assertFalse(r['takeover_authorized'])

    def test_equivalent_but_not_same_identity(self):
        t=fixture()
        for c in t['runs'][1]['audit']['bindings']:c['eq_ports'][0]['identity']=30
        self.assertEqual(link(t)['counts']['equivalent_identity_slots'],2)

    def test_sort_identity_and_availability_are_required(self):
        for mode in ('sort','missing','incomplete','copy'):
            t=fixture()
            for b in t['runs'][0]['audit']['bindings']:
                if mode=='sort':b['rhs']['slots'][0]['eq_port']['sort']='Other'
                if mode=='missing':b['rhs']['slots']=[dict(slot=1,unavailable='expired')]
                if mode=='incomplete':b['rhs']['completed']=False
            if mode=='copy':t['recipe']['rules'][0]['effects'][0]['kind']='copy'
            self.assertFalse(link(t)['windows'],mode)

    def test_changed_empty_run_does_not_authorize_link(self):
        t=fixture();t['steps'][1]['changed']=True
        self.assertFalse(link(t)['windows'])
        t=fixture();t['steps'].pop(1)
        self.assertFalse(link(t)['windows'])

    def test_multiple_providers_for_distinct_inputs(self):
        t=fixture();p=t['runs'][0]['audit']['bindings'][1]['rhs']['slots'][0]['eq_port']
        p['after_run']=99
        r=link(t)
        self.assertEqual(r['counts']['requires_multiple_observed_providers'],2)
        self.assertEqual(r['counts']['external_classes:0'],2)

    def test_rejects_missing_audit_and_reordered_runs(self):
        t=fixture();t['strict_run_graphs_equal']=False
        with self.assertRaises(ValueError):link(t)
        t=fixture();t['runs'].reverse()
        with self.assertRaises(ValueError):link(t)

if __name__=='__main__':unittest.main()
