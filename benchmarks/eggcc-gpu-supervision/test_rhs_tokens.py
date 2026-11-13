import unittest
from rhs_tokens import compile_rule, instantiate


EQ = {'name':'Expr','kind':'eq'}


class TokenWiring(unittest.TestCase):
    def test_alias_and_actual_return_port_are_distinct(self):
        rule = dict(slots=[dict(definition='query',sort=EQ)],effects=[
            dict(kind='copy',dst=1,arg={'slot':0}),
            dict(kind='construct',dst=2,sort=EQ,call={'table':'F'},args=[{'slot':1}]),
            dict(kind='union',args=[{'slot':1},{'slot':2}])])
        plan = compile_rule(rule)
        self.assertEqual(plan['operations'][0]['args'],[0])
        self.assertEqual(plan['operations'][1]['args'],[0,1])
        refs = instantiate(plan,[dict(slot=0,value=dict(sort='Expr',eq='Cell(554050781281)'))])
        self.assertEqual(refs[0]['eq'],'Cell(554050781281)')
        self.assertEqual(refs[1],dict(returned_port=1,sort='Expr'))
        self.assertNotIn('eq',refs[1])

    def test_undefined_read_rejected(self):
        with self.assertRaises(ValueError):
            compile_rule(dict(slots=[],effects=[dict(kind='union',args=[{'slot':0},{'slot':0}])]))

    def test_ordered_cpu_effect_is_retained(self):
        plan=compile_rule(dict(slots=[],effects=[dict(kind='panic')]))
        self.assertEqual(plan['operations'][0]['kind'],'panic')
        self.assertEqual(plan['boundary_marks'][0]['operation'],0)

    def test_unknown_effect_rejected(self):
        with self.assertRaises(ValueError):
            compile_rule(dict(slots=[],effects=[dict(kind='unknown')]))


if __name__=='__main__':unittest.main()
