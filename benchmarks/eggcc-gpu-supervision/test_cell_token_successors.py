import unittest
from cell_token_successors import compile_catalog,complete_template,match_consumer


def rule(query,effects,n=4):
    return dict(metadata=dict(source_set='test'),slots=[dict(sort=dict(kind='eq',name='E'),definition='query') for _ in range(n)],query=query,effects=effects)
def atom(name,*slots):return dict(call=dict(table=name),args=[dict(slot=i) for i in slots])
def make(name,dst,*slots):return dict(kind='construct',call=dict(table=name),dst=dst,args=[dict(slot=i) for i in slots])
TABLES={name:dict(name=name,kind='constructor') for name in ['F','G','Pair']}


class Successors(unittest.TestCase):
    def test_complete_query_not_just_pivot_is_required(self):
        p=rule([atom('F',0,1)],[make('G',2,1)])
        facts,mark=complete_template(p,TABLES);self.assertIsNone(mark)
        q=rule([atom('F',0,1),atom('G',1,2)],[],3)
        matches,budget=match_consumer(q,facts)
        self.assertEqual(len(matches),1);self.assertFalse(budget)
        q['query'].append(atom('Pair',0,1,2))
        self.assertEqual(match_consumer(q,facts)[0],[])

    def test_repeated_slot_constraint_is_not_assumed(self):
        p=rule([], [make('Pair',2,0,1)])
        facts,_=complete_template(p,TABLES)
        q=rule([atom('Pair',0,0,1)],[],2)
        self.assertEqual(match_consumer(q,facts)[0],[])
        p['effects'].insert(0,dict(kind='union',args=[dict(slot=0),dict(slot=1)]))
        facts,_=complete_template(p,TABLES)
        self.assertEqual(len(match_consumer(q,facts)[0]),1)

    def test_copy_and_constructor_reuse_are_baked(self):
        p=rule([atom('F',0,1)],[dict(kind='copy',dst=2,arg=dict(slot=0)),make('F',3,2)])
        facts,_=complete_template(p,TABLES)
        self.assertEqual(facts[0][1],facts[1][1])
        self.assertTrue(facts[1][2]) # produced occurrence, not proof of novel info

    def test_mutable_and_primitive_operations_remain_boundaries(self):
        p=rule([], [dict(kind='compute',dst=0)])
        facts,mark=complete_template(p,TABLES);self.assertIsNone(facts);self.assertIn('compute',mark['reason'])
        p=rule([], [make('M',1,0)])
        facts,mark=complete_template(p,{**TABLES,'M':dict(name='M',kind='function')});self.assertIsNone(facts)

    def test_budget_exhaustion_never_returns_partial_entries(self):
        facts=[('F',(('input',i),('result',i)),True) for i in range(4)]
        entries,exhausted=match_consumer(rule([atom('F',0,1)],[],2),facts,limit=2)
        self.assertEqual(entries,[]);self.assertTrue(exhausted)

    def test_catalog_rejects_guarded_consumer(self):
        p=rule([atom('F',0,1)],[make('G',2,1)])
        q=rule([atom('G',0,1),dict(call=dict(primitive='guard'),args=[])],[],2)
        catalog=compile_catalog(dict(tables=list(TABLES.values()),rules=[p,q]))
        self.assertFalse(any(e['consumer']==1 for e in catalog['edges']))

if __name__=='__main__':unittest.main()
