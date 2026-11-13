import unittest
from constant_prefixes import fixed_prefix

TABLES={'N':{'kind':'constructor'},'F':{'kind':'constructor'},'Cost':{'kind':'function'}}
def let(dst,table,args):
    return dict(op='let',dst=dst,call={'table':table},args=args)

class PrefixTests(unittest.TestCase):
    def test_slot_renaming_does_not_change_constructor_expression(self):
        def rule(a,b):
            return {'effects':[let(a,'N',[]),let(b,'F',[{'slot':a}])]}
        self.assertEqual(fixed_prefix(rule(2,3),TABLES),fixed_prefix(rule(5,9),TABLES))

    def test_parameter_or_mutable_read_cannot_become_a_constant(self):
        for effects in ([let(2,'N',[{'slot':0}])],
                        [let(2,'Cost',[]),let(3,'F',[{'slot':2}])]):
            self.assertEqual(fixed_prefix({'effects':effects},TABLES),{})

    def test_effect_boundary_and_literal_sort_are_preserved(self):
        a=let(2,'N',[{'literal':0,'sort':{'kind':'i64'}}])
        b=let(2,'N',[{'literal':0,'sort':{'kind':'Unit'}}])
        self.assertNotEqual(fixed_prefix({'effects':[a]},TABLES),fixed_prefix({'effects':[b]},TABLES))
        self.assertEqual(list(fixed_prefix({'effects':[a,{'op':'union'},let(4,'N',[])]},TABLES)),[0])

if __name__=='__main__':unittest.main()
