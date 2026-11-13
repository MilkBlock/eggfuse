import copy
import unittest
from pool import pool

class PoolTest(unittest.TestCase):
    def sample(self, name, reverse=False):
        programs=[{'fields':[1]}, {'fields':[2]}]
        rules=[{'query':'F','effects':'G'}, {'query':'G','effects':'H'}]
        if reverse:
            programs.reverse(); rules.reverse()
        index=1 if reverse else 0
        interface=dict(tables=[{'name':'F'}], programs=programs, rules=rules,
                       entries=[[3],[3]], profile_source=name)
        profile=dict(schema='eggfuse-ownership-fragment-profile/v2', source=name,
                     records=[dict(fragment=dict(root=index,hops=[dict(rule=index,entry=0,source_frame=0,op=2)]),
                       static_instruction_handles=4,
                       observed=dict(activations=1,binding_records_saved=2,transition_probes=1))])
        return name,interface,profile

    def test_ids_are_remapped_and_actual_counts_aggregated(self):
        a=self.sample('a'); b=self.sample('b',True)
        b[1]['entries'][1]=[9,3]
        b[2]['records'][0]['fragment']['hops'][0]['entry']=1
        merged, projected, summary=pool([a,b])
        self.assertEqual(summary['records'],1)
        self.assertEqual(summary['shared_across_samples'],1)
        self.assertEqual(merged['records'][0]['observed']['activations'],2)
        self.assertEqual(projected['a']['records'][0]['fragment']['root'],0)
        self.assertEqual(projected['b']['records'][0]['fragment']['root'],1)
        self.assertEqual(projected['b']['records'][0]['fragment']['hops'][0]['rule'],1)
        self.assertEqual(projected['b']['records'][0]['fragment']['hops'][0]['entry'],1)

    def test_unseen_fragment_can_transfer_when_definitions_exist(self):
        a=self.sample('a');b=self.sample('b',True);b[2]['records']=[]
        _, projected, summary=pool([a,b])
        self.assertEqual(summary['shared_across_samples'],0)
        self.assertEqual(len(projected['b']['records']),1)
        self.assertEqual(projected['b']['records'][0]['fragment']['root'],1)

    def test_source_and_types_are_checked(self):
        a=self.sample('a');b=self.sample('b')
        b[2]['source']='wrong'
        with self.assertRaises(ValueError):pool([a,b])
        b=self.sample('b');b[1]['tables'][0]['name']='Other'
        with self.assertRaises(ValueError):pool([a,b])

    def test_equal_local_ids_do_not_merge_different_rules(self):
        a=self.sample('a');b=self.sample('b');b[1]['rules'][0]['effects']='Different'
        _, _, summary=pool([a,b])
        self.assertEqual(summary['records'],2)
        self.assertEqual(summary['shared_across_samples'],0)

    def test_static_cost_mismatch_is_not_silently_summed(self):
        a=self.sample('a');b=self.sample('b');b[2]['records'][0]['static_instruction_handles']=5
        with self.assertRaises(ValueError):pool([a,b])
        with self.assertRaises(ValueError):pool([a,copy.deepcopy(a)])

if __name__=='__main__':unittest.main()
