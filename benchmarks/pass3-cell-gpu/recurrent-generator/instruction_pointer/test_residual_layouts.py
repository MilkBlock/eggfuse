"""A later independent producer can be a ready entry when the first atom cannot."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ripsat_layout import capture


class AlternateEntryTest(unittest.TestCase):
    def test_second_producer_can_name_the_earlier_external_boundary(self):
        def rule(inputs,outputs):
            return dict(query=[{'call':{'table':t}} for t in inputs],
                        effects=[{'op':'let','call':{'table':t}} for t in outputs])
        program={'recipe':{'rules':[rule([],['L']),rule([],['R']),rule(['L','R'],[])]}}
        def addr(j):
            return {'token':j,'op':0}
        parents=[{'address':addr(i),'version':i} for i in (1,2)]
        tape=[dict(rule=i-1,run=i,token=i,parents=parents if i==3 else []) for i in (1,2,3)]
        frames=[dict(run=i,rules=[[i-1,0]],retired=[],
                     updates=[[addr(i-1),{'version':i-1}]] if i>1 else []) for i in (1,2,3)]
        with TemporaryDirectory() as tmp:
            d=Path(tmp)
            (d/'program.json').write_text(json.dumps(program))
            (d/'tape.json').write_text(json.dumps({'requests':tape}))
            (d/'memory.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in frames))
            _,_,base,_=capture(d,program,2)
            _,_,both,_=capture(d,program,2,each_parent_first=True)
            self.assertEqual(set(base),{0})
            self.assertEqual(set(both),{0,1})
            self.assertEqual(base[0],both[0])
            first=next(iter(both[0].values()))[0]
            self.assertFalse(first[1])
            second=next(iter(both[1].values()))[0]
            self.assertEqual(second,(((1,0,1),),True,True,(2,3)))
            parents[0]['version']+=1
            (d/'tape.json').write_text(json.dumps({'requests':tape}))
            _,_,stale,_=capture(d,program,2,each_parent_first=True)
            self.assertFalse(next(iter(stale[1].values()))[0][1])

    def test_consumer_growth_bakes_fanout_only_when_both_returns_are_live(self):
        # Two downstream rules read different result PCs. Neither is an
        # ancestor of the other, so backwards extraction only finds pairs.
        program = {'recipe': {'rules': [
            {'query': [], 'effects': [{'op': 'let', 'call': {'table': k}} for k in ('L', 'R')]},
            *[{'query': [{'call': {'table': k}}], 'effects': []} for k in ('L', 'R')]
        ]}}
        ports = [{'token': 1, 'op': pc} for pc in (0, 1)]
        tape = [{'rule': 0, 'run': 1, 'token': 1, 'parents': []}]
        tape.extend({'rule': pc + 1, 'run': 2, 'token': pc + 2,
                     'parents': [{'address': p, 'version': 1}]} for pc, p in enumerate(ports))
        frames = [
            {'run': 1, 'rules': [[0, 0]], 'retired': [], 'updates': []},
            {'run': 2, 'rules': [[1, 0], [2, 0]], 'retired': [],
             'updates': [[p, {'version': 1}] for p in ports]}
        ]
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d/'program.json').write_text(json.dumps(program))
            (d/'memory.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in frames))
            (d/'tape.json').write_text(json.dumps({'requests': tape}))
            _, _, old, _ = capture(d, program, 3)
            _, _, joined, _ = capture(d, program, 3, grow_consumers=True)
            fork = ((0, 0, ()), (1, 1, ((0, 0),)), (2, 1, ((0, 1),)))
            self.assertNotIn(fork, old[0])
            self.assertEqual(joined[0][fork], [((), True, True, (1, 2, 3))])
            for pair in old[0]:
                self.assertEqual(old[0][pair], joined[0][pair])
            tape[-1]['parents'][0]['version'] += 1
            (d/'tape.json').write_text(json.dumps({'requests': tape}))
            _, _, stale, _ = capture(d, program, 3, grow_consumers=True)
            self.assertNotIn(fork, stale[0])


if __name__=='__main__':
    unittest.main()
