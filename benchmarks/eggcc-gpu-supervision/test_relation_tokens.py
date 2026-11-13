import unittest
from relation_tokens import audit, partition


def port(slot, before, after, sort='Expr'):
    return dict(slot=slot,sort=sort,identity=before,before=before,after=after)


class Relations(unittest.TestCase):
    def test_identity_renaming_and_sort_separation(self):
        ports=[port(0,7,7),port(1,7,7),port(2,7,7,'Type')]
        self.assertEqual(partition(ports,'before'),(0,0,2))
        self.assertEqual(partition(ports,'before',lambda n:2**100+n*19),(0,0,2))

    def test_pre_run_boundary_context_distinguishes_local_conflict(self):
        trace=dict(relations=True,runs=[dict(ordinal=1,audit=dict(bindings=[
            dict(rule=0,values=[],eq_ports=[port(0,10,10),port(1,11,10)]),
            dict(rule=0,values=[],eq_ports=[port(0,20,20),port(1,21,21)]),
            dict(rule=1,values=[],eq_ports=[port(0,10,10)])]))])
        _,_,conflicts,_,errors,context=audit(trace)
        self.assertEqual(len(conflicts),1)
        self.assertEqual(errors,1)
        self.assertEqual(context['same_run_ambiguous_groups'],0)
        self.assertEqual(context['deterministic_minimum_errors'],0)

    def test_equivalence_splitting_is_rejected(self):
        trace=dict(relations=True,runs=[dict(ordinal=1,audit=dict(bindings=[
            dict(rule=0,values=[],eq_ports=[port(0,10,10),port(1,10,11)])]))])
        with self.assertRaises(AssertionError):audit(trace)


if __name__=='__main__':unittest.main()
