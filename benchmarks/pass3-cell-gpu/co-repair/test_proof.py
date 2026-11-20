import unittest
from native import normalize

class SourceIdentityTest(unittest.TestCase):
    def test_concat_preserves_order(self):
        lhs=['TermConcat',['TermConcat','a','b'],'c']
        self.assertEqual(normalize(lhs),normalize(['TermConcat','a',['TermConcat','b','c']]))
        self.assertNotEqual(normalize(lhs),normalize(['TermConcat','a',['TermConcat','c','b']]))

    def test_add_sub_has_two_source_steps(self):
        def op(o,x,y):return ['TermBop',[o],x,y]
        self.assertEqual(normalize(op('Add',op('Sub','x','y'),'z')),
                         normalize(op('Sub',op('Add','x','z'),'y')))
        self.assertNotEqual(normalize(op('Add',op('Sub','x','y'),'z')),
                            normalize(op('Sub',op('Add','x','y'),'z')))
        self.assertNotEqual(normalize(op('Add',op('Add','x','y'),'z')),
                            normalize(op('Add','x',op('Add','y','z'))))
