"""A stale pivot can join a new later atom; a row at the watermark is still new."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from lower import save_device_image
from run import execute


class FreshnessContract(unittest.TestCase):
    def test_late_nonpivot_and_inclusive_watermark(self):
        scalar=dict(name='i64',kind='i64')
        eq=dict(name='E',kind='eq')
        tables=[dict(name='A',kind='constructor',schema=[scalar,eq],merge_expr=None),
                dict(name='B',kind='function',schema=[scalar,scalar],merge='new',merge_expr={'var':'new'})]
        def write(key,value):
            return dict(q=[],e=[['set',1,-1,[key,value]]],inputs=[],n=1,semi=True)
        read=dict(q=[[0,[0,1]],[1,[0,2]]],e=[['set',1,-1,[0,-2]]],inputs=[0,1,2],n=3,semi=True)
        control=[{'run':s} for s in ('init','read','read','read','add','read','read')]
        packet=dict(tables=tables,rules=[write(-1,-1),read,write(-2,-2)],sets={'init':[0],'read':[1],'add':[2]},
                    control=[{'repeat':1,'body':{'sequence':control}}],stage_entries=[],
                    templates=[[[0,[0,1]]]],instances=[[0,[0,2],[0]],[0,[1,3],[0]]],
                    symbols=[{'sort':'i64','value':0},{'sort':'i64','value':1},{'sort':'E','eq':'x'},{'sort':'E','eq':'y'}],
                    eq_order=[0,0,1,2])
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);p=base/'ingress.json';p.write_text(json.dumps(packet));save_device_image(p,base)
            for mode in range(5):
                out=base/str(mode)
                execute(base/'device.json',p,p,9,2,out,reader='exact',spine=False,tiles=1,hot_filter=mode)
                with np.load(out/'output.npz') as z:
                    self.assertEqual(z['runs'][:,1].tolist(),[1,1,1,0,1,1,0])
                    bindings=z['rhs'][z['rhs'][:,1]==1]
                    self.assertEqual(bindings[:,[0,4,6]].tolist(),[[2,0,0],[3,0,1],[6,1,1]])


if __name__=='__main__':unittest.main()
