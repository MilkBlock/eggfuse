import copy
import unittest
from proven_unions import compile_unions, Closure, complete_known_congruence, audit

EQ={'name':'Expr','kind':'eq'}


def slot():return dict(definition='query',sort=EQ)
def port(i,before,after):return dict(slot=i,sort='Expr',identity=before,before=before,after=after)
def binding(rule,ports):
    return dict(rule=rule,eq_ports=ports,values=[dict(slot=p['slot'],value=dict(sort='Expr',eq=str(p['before']))) for p in ports])


class ProvenUnions(unittest.TestCase):
    def test_identical_query_constructor_discharges_return_port(self):
        rule=dict(slots=[slot(),slot()],query=[dict(call={'table':'F'},args=[{'slot':0},{'slot':1}])],effects=[
            dict(kind='construct',dst=2,sort=EQ,call={'table':'F'},args=[{'slot':0}]),
            dict(kind='union',args=[{'slot':2},{'slot':0}])])
        plan=compile_unions(rule,{'F'})
        self.assertEqual(plan['unions'],[dict(operation=1,slots=[1,0])])
        # A potentially failing primitive prevents hoisting the later union.
        rule['effects'].insert(0,dict(kind='compute',dst=3))
        self.assertEqual(compile_unions(rule,{'F'})['unions'],[])

    def test_congruence_waits_for_all_inputs(self):
        c=Closure();facts=[('F',(('eq','Expr',1),('eq','Expr',3)),('eq','Expr',5)),
                           ('F',(('eq','Expr',2),('eq','Expr',4)),('eq','Expr',6))]
        c.union(('Expr',1),('Expr',2));complete_known_congruence(c,facts)
        self.assertNotEqual(c.find(('Expr',5)),c.find(('Expr',6)))
        c.union(('Expr',3),('Expr',4));complete_known_congruence(c,facts)
        self.assertEqual(c.find(('Expr',5)),c.find(('Expr',6)))

    def fixture(self):
        r0=dict(slots=[slot(),slot()],query=[dict(call={'table':'F'},args=[{'slot':0},{'slot':1}])],effects=[])
        r1=dict(slots=[slot(),slot(),slot()],query=[],effects=[
            dict(kind='set',call={'table':'F'},args=[{'slot':0}],value={'slot':1})])
        return dict(program_sha256='test',recipe=dict(tables=[dict(name='F',kind='constructor')],rules=[r0,r1]),
            steps=[dict(ruleset='first'),dict(ruleset='second')],runs=[
                dict(ordinal=1,audit={'bindings':[binding(0,[port(0,10,10),port(1,30,30)])]}),
                dict(ordinal=2,audit={'bindings':[binding(1,[port(0,10,10),port(1,20,20),port(2,30,20)])]})])

    def test_constructor_assignment_requires_prior_stage_fact(self):
        trace=self.fixture();local,_=audit(trace);history,_=audit(trace,True)
        self.assertEqual(local['totals']['proven_new_eq_pairs'],0)
        self.assertEqual(history['totals']['proven_new_eq_pairs'],1)
        self.assertEqual(history['totals']['false_proven_pairs'],0)

    def test_visibility_effect_discards_history(self):
        trace=self.fixture();trace['recipe']['rules'][1]['effects'].append(dict(kind='subsume'))
        report,_=audit(trace,True)
        self.assertEqual(report['totals']['proven_new_eq_pairs'],0)

    def test_post_run_target_is_checked_not_used_to_generate_edges(self):
        trace=copy.deepcopy(self.fixture());trace['runs'][1]['audit']['bindings'][0]['eq_ports'][2]['after']=30
        with self.assertRaises(ValueError):audit(trace,True)


if __name__=='__main__':unittest.main()
