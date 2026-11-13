import copy
import unittest
from cell_token_successors import continuation_contract, complete_template, match_consumer
from test_cell_token_successors import rule, atom, make, TABLES


class Contracts(unittest.TestCase):
    def fixture(self):
        producer=rule([atom('F',0,1)],[make('G',2,1)])
        consumer=rule([atom('F',0,1),atom('G',1,2)],[],3)
        facts,_=complete_template(producer,TABLES)
        entry=match_consumer(consumer,facts)[0][0]
        return producer,consumer,facts,entry

    def test_full_query_and_prefix_without_ownership_claim(self):
        p,c,f,e=self.fixture();contract=continuation_contract(p,c,f,e)
        self.assertEqual(contract['completed_effect_prefix'],1)
        self.assertEqual(len(contract['query_projection']),2)
        self.assertFalse(contract['ownership_transfer_authorized'])
        c['metadata']['source_set']='later'
        self.assertEqual(continuation_contract(p,c,f,e)['boundary'],'source_run_boundary')

    def test_corrupted_projection_rejected(self):
        p,c,f,e=self.fixture()
        for mode in ('missing','duplicate','binding','table'):
            entry=copy.deepcopy(e);facts=copy.deepcopy(f)
            if mode=='missing':entry['witnesses']=entry['witnesses'][:1]
            if mode=='duplicate':entry['witnesses']+=entry['witnesses'][:1]
            if mode=='binding':entry['inputs']=((0,('input',99)),)+entry['inputs'][1:]
            if mode=='table':facts[0]=('Wrong',facts[0][1],facts[0][2])
            with self.assertRaises(ValueError,msg=mode):continuation_contract(p,c,facts,entry)


if __name__=='__main__':unittest.main()
