import unittest
import numpy as np
import mlx.core as mx
from audit_neural_gpu_rhs import initial_case
from device_constructor_completion import complete
from device_slot_owners import compile_transfer,read
from device_snapshot_import import identity
from reference_union_family import Reference,compare_graph
from reference_cell_closure import facts_from_cells
from audit_snapshot_queries import device
from test_neural_cell_chains import recipe as base_recipe


def fixture():
    recipe=base_recipe();eq=recipe['tables'][0]['schema'][0]
    recipe['rules'].append(dict(slots=[dict(sort=eq,definition='query') for _ in range(4)],query=[dict(call=dict(table='F'),args=[dict(slot=i),dict(slot=i+1)]) for i in range(3)],effects=[]))
    ids={identity(dict(sort='E',eq=str(i))):i for i in range(3)}
    ref=Reference(recipe,[],ids);ref.construct('F',[0],1);ref.construct('F',[1],2)
    plan=compile_transfer(recipe,dict(producer=0,consumer=0,projection=[1,2],projection_valid=[True,True]),4)
    assert plan['covered']
    return recipe,dict(plan=plan,initial_reference=ref,initial_binding={0:1,1:2},source_binding={0:0,1:1})


class NeuralGPURhs(unittest.TestCase):
    def test_rhs_starts_empty_and_gpu_constructs_result(self):
        recipe,record=fixture()
        local,state,plan,ctx,tp,src,dst,n,oracle=initial_case(recipe,record)
        self.assertFalse(read(state,'slot_valid',np.array(dst),np.array(2),np))
        self.assertEqual(int(state['effect_pc'][dst]),0)
        out,next_id,marks=complete(device(state),device(plan),mx.array(n),mx.array(len(ctx['roots'])),mx.array(64),mx.array(True),mx.array(True),mx,device(ctx),eq_rounds=8)
        mx.eval(out,next_id,marks)
        self.assertEqual(int(marks['new_constructors']),1)
        self.assertFalse(bool(marks['needs_attention']))
        host={k:np.array(v) for k,v in out.items()}
        facts,covered=facts_from_cells(local,host)
        self.assertTrue(covered)
        check=compare_graph(oracle,facts,np.array(marks['eq_context']['roots'])[:int(next_id)],n)
        self.assertTrue(check['passed'],check)
        self.assertTrue(read(host,'slot_valid',np.array(dst),np.array(2),np))


if __name__=='__main__':unittest.main()
