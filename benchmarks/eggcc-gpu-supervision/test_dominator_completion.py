import unittest
from dominator_completion import compose
from test_cell_token_successors import rule,atom,make,TABLES


class Dominator(unittest.TestCase):
    def test_target_preserves_unconsumed_source_facts(self):
        source=[('F',(('input',0),('input',1))),('Pair',(('input',2),('input',3),('input',4)))]
        consumer=rule([atom('F',0,1)],[make('G',2,1)],2)
        out,reason=compose(source,consumer,[(0,('input',0)),(1,('input',1))],TABLES)
        self.assertIsNone(reason);self.assertEqual(out['retained_source_facts'],2)
        self.assertIn(source[1],out['facts']);self.assertEqual(out['new_facts'],1)

    def test_union_preserves_source_through_explicit_quotient(self):
        source=[('F',(('input',0),('input',1))),('F',(('input',2),('input',3)))]
        consumer=rule([atom('F',0,1),atom('F',2,3)],[dict(kind='union',args=[dict(slot=0),dict(slot=2)])])
        out,reason=compose(source,consumer,[(i,('input',i)) for i in range(4)],TABLES)
        self.assertIsNone(reason);mapping=dict(out['source_map'])
        self.assertEqual(mapping[('input',1)],mapping[('input',3)])
        self.assertEqual(out['source_equalities_added'],2);self.assertTrue(out['novel'])
        for name,args in source:self.assertIn((name,tuple(mapping[a] for a in args)),out['facts'])

    def test_repeated_effect_is_not_new_information(self):
        source=[('F',(('input',0),('input',1)))]
        consumer=rule([atom('F',0,1)],[make('F',2,0)],2)
        out,reason=compose(source,consumer,[(0,('input',0)),(1,('input',1))],TABLES)
        self.assertIsNone(reason);self.assertFalse(out['novel'])

    def test_missing_premise_cannot_produce_a_target(self):
        out,reason=compose([],rule([atom('F',0,1)],[make('G',2,1)],2),[(0,('input',0)),(1,('input',1))],TABLES)
        self.assertIsNone(out);self.assertEqual(reason,'missing consumer premise')

if __name__=='__main__':unittest.main()
