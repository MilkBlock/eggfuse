import json,unittest
from pathlib import Path
import numpy as np
import mlx.core as mx
from audit_token_state_recovery import recover
from device_completion_readout import compile_state_layout
from device_completion_states import tokens
from audit_snapshot_queries import device
from multi_entry_ridge import scalar


class TokenRecovery(unittest.TestCase):
    def test_every_baked_state_with_dynamic_scalars_on_gpu(self):
        rules=json.loads(Path(__file__).with_name('synthetic-context-recipe.json').read_text())['rules']
        for rule in rules:
            p=compile_state_layout(rule);k=len(p['states']);selected=np.tile(np.arange(k),3)
            codes=np.empty((len(selected),len(p['scalar_slots']),64),np.float32)
            for i,v in enumerate((-1,0,7)):
                codes[i*k:(i+1)*k]=scalar(dict(sort='i64',value=v))
            value=tokens(selected,codes,p['token'],np)
            actual,error,margin=recover(value,codes,p,np)
            np.testing.assert_array_equal(actual,selected)
            self.assertTrue(np.all(error<1e-10));self.assertTrue(np.all(margin>1e-6))
            dp=device(p);result=mx.compile(lambda v,c:recover(v,c,dp,mx))(mx.array(value),mx.array(codes));mx.eval(result)
            np.testing.assert_array_equal(result[0],selected)
            # A nearest state is still available for an invalid vector, but its
            # reconstruction residual must prevent claiming exact recovery.
            _,bad,_=recover(value+1,codes,p,np)
            self.assertTrue(np.all(bad>1e-6))

if __name__=='__main__':unittest.main()
