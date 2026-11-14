import copy
import unittest
from native_cell_examples import extract,partition

class NativeExamplesTests(unittest.TestCase):
    def trace(self):
        ports=[dict(slot=i,sort='Expr',before=i+100,after=100) for i in range(2)]
        row=dict(rule=0,eq_ports=ports,values=[dict(slot=i,value=dict(sort='Expr',eq=str(i+100))) for i in range(2)],rhs=dict(completed=True,slots=[dict(slot=i,value=dict(sort='Expr',eq=str(i+100)),eq_port=dict(sort='Expr',identity=i+100,at_rhs=i+100,after_run=100)) for i in range(2)]))
        return dict(relations=True,all_slots=True,strict_run_graphs_equal=True,strict_audit_reference_equal=True,run_control_counts_equal=True,program_sha256='test',recipe=dict(rules=[]),runs=[dict(ordinal=1,audit=dict(bindings=[row]))])

    def test_targets_do_not_leak(self):
        trace=self.trace();a=extract(trace)['examples'][0]
        trace['runs'][0]['audit']['bindings'][0]['eq_ports'][1]['after']=101
        b=extract(trace)['examples'][0]
        self.assertEqual(a['inputs'],b['inputs'])
        self.assertNotEqual(a['targets'],b['targets'])
        self.assertEqual(a['inputs']['eq_partition'],[0,1])
        self.assertEqual(a['targets']['input_partition'],[0,0])
        self.assertEqual(a['ownership'],'unobserved')

    def test_source_evidence_alignment(self):
        trace=self.trace()
        source=dict(ordinal=0,rule=0,parent=dict(cell=8,op=2),continuation=None,
                    direct=False,epoch=0,retained_query_witnesses=[[1,{'Fact':{'cell':8,'op':2}}]])
        trace.update(source_observation_enabled=True,source_observations=[dict(ordinal=1,observation=dict(matches=[source]))])
        result=extract(trace)['examples'][0]
        self.assertEqual(result['source_evidence']['parent'],source['parent'])
        self.assertEqual(result['ownership'],'unobserved')
        source['rule']=1
        with self.assertRaises(ValueError):extract(trace)

    def test_typed_partition(self):
        self.assertEqual(partition([dict(sort=s,before=v) for s,v in [('A',99),('B',99),('A',99)]],'before'),[0,1,0])

    def test_missing_evidence(self):
        trace=self.trace();trace['relations']=False
        with self.assertRaises(ValueError):extract(trace)
        trace=self.trace();trace['runs'][0]['audit']['bindings'][0]['eq_ports']=[]
        with self.assertRaises(ValueError):extract(trace)

if __name__=='__main__':unittest.main()
