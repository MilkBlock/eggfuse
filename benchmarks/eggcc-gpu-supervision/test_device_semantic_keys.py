import unittest
import numpy as np
import mlx.core as mx
import test_device_token_commit as helper
from device_semantic_keys import compile_types,comparison_view
from device_token_commit import commit


def context():
    roots=np.arange(64,dtype=np.int32);roots[21]=20
    return dict(roots=roots,sorts=np.zeros(64,np.int32),types=np.array([[0],[0],[-1]],np.int32),settled=np.array(True))


class SemanticKeys(unittest.TestCase):
    def test_gpu_eq_alias_is_duplicate_without_rewriting_stable_keys(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        s=helper.seed();s['keys'][1]=[1,20]
        for key in ('present','settled','visible'):s[key][1]=True
        p=helper.proposals([[1,21]]);p['transfer_covered'][:]=False
        dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        dp,dc=dev(p),dev(context())
        out,marks=mx.compile(lambda state:commit(state,dp,mx,dc))(dev(s));mx.eval(out,marks)
        self.assertFalse(np.array(marks['accepted']).any());self.assertTrue(np.array(marks['duplicate'])[0])
        np.testing.assert_array_equal(np.array(out['keys']),s['keys'])

    def test_same_round_aliases_deduplicate_but_scalars_do_not(self):
        s=helper.seed();p=helper.proposals([[1,20],[1,21]]);p['transfer_covered'][:]=False
        out,m=commit(s,p,np,context());self.assertEqual(m['accepted'].tolist(),[True,False])
        self.assertEqual(out['keys'][1].tolist(),[1,20])
        p=helper.proposals([[2,20],[2,21]]);p['transfer_covered'][:]=False
        self.assertEqual(commit(s,p,np,context())[1]['accepted'].tolist(),[True,True])

    def test_pending_registry_wrong_sort_and_unknown_resident_are_not_absence(self):
        for mode in ('pending','sort','resident','compression'):
            s=helper.seed();p=helper.proposals([[1,21]]);c=context()
            if mode=='pending':c['settled']=np.array(False)
            if mode=='sort':c['sorts'][21]=1
            if mode=='resident':s['keys'][0,1]=999
            if mode=='compression':c['roots'][20]=19
            out,m=commit(s,p,np,c)
            self.assertFalse(m['accepted'].any(),mode);self.assertTrue(m['needs_attention'],mode)

    def test_typed_layout_uses_original_inputs_not_overwritten_effect_slots(self):
        recipe=dict(rules=[dict(slots=[dict(definition='query',sort=dict(kind='eq',name='E')),
                                      dict(definition='effect',sort=dict(kind='eq',name='E'))])])
        types,names=compile_types(recipe);self.assertEqual(types.tolist(),[[0]]);self.assertEqual(names,['E'])
        c=context();c['types']=types
        view,valid=comparison_view(np.array([[0,21]],np.int32),c,np)
        self.assertEqual(view.tolist(),[[0,20]]);self.assertTrue(valid[0])


if __name__=='__main__':unittest.main()
