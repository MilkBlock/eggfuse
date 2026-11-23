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


if __name__=='__main__':
    unittest.main()
