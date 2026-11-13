import copy,unittest
from test_rhs_links import fixture
from historical_cell_sources import candidates,link_history

class HistoricalSources(unittest.TestCase):
    def test_older_source_fills_only_uncovered_inputs(self):
        t=fixture();last=copy.deepcopy(t['runs'][-1]);last['ordinal']=4;t['runs'].append(last)
        t['steps'].append(dict(ordinal=4,ruleset='c',executed_bindings=2,changed=True))
        _,extra,counts=candidates(t)
        self.assertNotIn((3,0,0),extra)
        self.assertEqual(extra[(4,0,0)][0]['run'],1)
        self.assertNotIn((4,0,1),extra)
        result=link_history(t);self.assertFalse(result['takeover_authorized'])
        self.assertTrue(any(w['consumer_run']==4 for w in result['windows']))

    def test_latest_run_retains_all_alternatives_and_incomplete_states_do_not_supply_tokens(self):
        t=fixture();t['steps'][1]['changed']=True
        # Disable adjacent links, so history candidates can be inspected directly.
        t['runs'][0]['audit']['bindings'][0]['rhs']['slots'][0]['eq_port']['identity']=20
        choices=candidates(t)[1][(3,0,0)]
        self.assertEqual(len(choices),2)
        t['runs'][0]['audit']['bindings'][0]['rhs']['slots'].append(dict(slot=5,unavailable='missing'))
        self.assertEqual(len(candidates(t)[1][(3,0,0)]),1)
        # A constructor in Run 3 supersedes prior observations only for later Runs.
        new=copy.deepcopy(t['runs'][0]['audit']['bindings'][1]);new['eq_ports']=[];t['runs'][1]['audit']['bindings'].append(new)
        last=copy.deepcopy(t['runs'][1]);last['audit']['bindings']=last['audit']['bindings'][:2];last['ordinal']=4;t['runs'].append(last)
        t['steps'].append(dict(ordinal=4,ruleset='c',executed_bindings=3,changed=True))
        # The normal adjacent path covers this input; no duplicate history is added.
        self.assertNotIn((4,0,0),candidates(t)[1])
        last=copy.deepcopy(last);last['ordinal']=5;t['runs'].append(last)
        t['steps'].append(dict(ordinal=5,ruleset='c',executed_bindings=2,changed=True))
        self.assertEqual({p['run'] for p in candidates(t)[1][(5,0,0)]},{3})
        first=candidates(t,earliest=True)[1][(5,0,0)]
        self.assertEqual({p['run'] for p in first},{1})
        self.assertEqual(len(first),1)

    def test_fallback_leaves_partly_connected_cell_unchanged(self):
        t=fixture();port=t['runs'][0]['audit']['bindings'][0]['rhs']['slots'][0]['eq_port']
        port.update(identity=99,at_rhs=99,after_run=99)
        last=copy.deepcopy(t['runs'][1]);last['ordinal']=4;t['runs'].append(last)
        t['steps'].append(dict(ordinal=4,ruleset='c',executed_bindings=2,changed=True))
        producer=copy.deepcopy(t['runs'][0]['audit']['bindings'][1]);producer['eq_ports']=[]
        t['runs'][1]['audit']['bindings'].append(producer)
        def ports(fallback):
            window=next(w for w in link_history(t,fallback_only=fallback)['windows'] if w['consumer_run']==4)
            return next(c for c in window['consumers'] if c['binding']==0)['ports']
        self.assertEqual({p['slot'] for p in ports(False) if 'group' in p},{0,1})
        self.assertEqual({p['slot'] for p in ports(True) if 'group' in p},{0})

    def test_same_run_results_are_not_input_sources(self):
        t=fixture();b=t['runs'][0]['audit']['bindings'][0]
        b['eq_ports']=[dict(slot=0,sort='E',identity=20,before=10)]
        self.assertNotIn((1,0,0),candidates(t)[1])

    def test_identity_not_just_equal_root_and_no_scalar_or_copy_sources(self):
        for kind in ['copy','set']:
            t=fixture();t['recipe']['rules'][0]['effects'][0]['kind']=kind
            self.assertFalse(candidates(t)[1])
        t=fixture();t['steps'][1]['changed']=True
        for b in t['runs'][-1]['audit']['bindings']:b['eq_ports'][0]['identity']=30
        self.assertFalse(candidates(t)[1])

if __name__=='__main__':unittest.main()
