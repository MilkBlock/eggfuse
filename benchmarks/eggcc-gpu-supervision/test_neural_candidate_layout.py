import unittest
import numpy as np
import mlx.core as mx
from device_snapshot_import import prepare_family,reference_keys
from neural_device_candidates import compile_candidates,candidates,compile_frames
from audit_snapshot_queries import device


class CandidateLayout(unittest.TestCase):
    def test_four_atom_compaction_preserves_exact_join_and_gpu_constraints(self):
        eq=dict(kind='eq',name='E')
        def atom(table,*args):return dict(call=dict(table=table),args=[dict(slot=i) for i in args])
        rule=dict(slots=[dict(sort=eq,definition='query') for _ in range(4)],query=[atom('N',0),atom('F',0,1),atom('F',1,2),atom('F',2,3)],effects=[])
        recipe=dict(tables=[dict(name='N',kind='constructor',schema=[eq]),dict(name='F',kind='constructor',schema=[eq,eq])],rules=[rule])
        val=lambda i:dict(sort='E',eq=str(i))
        rows=[dict(table='N',values=[val(0)],subsumed=False)]+[dict(table='F',values=[val(i),val(i+1)],subsumed=False) for i in range(3)]
        local,state,ids,rows=prepare_family(recipe,dict(rows=rows),[0],1)
        frames=device(compile_frames(local,state['slots'].shape[1]));ds=device(state)
        selected=[]
        for compact in (False,True):
            plan=compile_candidates(local,rule,capacity=4,atoms=4,fields=2,compact_constants=compact)
            batch=mx.compile(lambda x:candidates(x,frames,device(plan),mx.array(True),mx.array(True),mx))(ds);mx.eval(batch)
            self.assertTrue(bool(batch['complete']))
            self.assertEqual(len(batch['live']),64 if compact else 256)
            accept=np.array(batch['live']&batch['constraints_satisfied'])
            keys={tuple([0]+list(x)) for x in np.array(batch['binding_roots'])[accept]}
            selected.append(keys)
        self.assertEqual(selected[0],selected[1]);self.assertEqual(selected[0],reference_keys(rule,rows,ids,5));self.assertEqual(len(selected[0]),1)


if __name__=='__main__':unittest.main()
