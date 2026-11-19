"""Post-hoc stride versus common port-feature intervention on the SAME frozen weights."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from data import dataset,audit
from model import AddressModel
from study import ARMS,SEEDS


class ReferenceScale(AddressModel):
    """Keep raw port and rotary addresses; set only the common feature denominator to P_train - 1."""
    def port_content(self,coords,ports):
        return super().port_content(coords,3)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);a=parser.parse_args()
    source=dataset(4,3,3,128,92001);full=dataset(4,3,4,128,92002)
    # Declared after primary results. Every line except full4 uses the same base
    # graph with exactly three candidates per Cell. A fresh target is never synthesized.
    result={}
    for arm in ARMS:
        for seed in SEEDS:
            key=f'{arm}-{seed}';weight=torch.load(a.root/key/'final.pt',map_location='cpu',weights_only=True)
            result[key]={}
            for scale,cls in [('normal',AddressModel),('feature_P3',ReferenceScale)]:
                model=cls(arm).to('mps').eval();model.load_state_dict(weight)
                with torch.inference_mode():
                    for case,stride,shift,d in [('dense3',3,0,source),('stride4_012',4,0,source),('stride4_123',4,1,source),('full4',4,0,full)]:
                        offset=np.array([0,0,shift],np.int32)
                        c=d['coords']+offset;coords=torch.as_tensor(c,device='mps');outputs=[]
                        for i in range(0,128,16):
                            ref=[torch.as_tensor(d[k][i:i+16]+offset,device='mps') for k in ('make_ref','finish_ref')]
                            value=torch.as_tensor(d['value'][i:i+16],device='mps');out=model(coords,*ref,value,3,stride)
                            torch.mps.synchronize()
                            outputs.append({k:out[k].cpu().numpy() for k in ('ptr1','ptr2','pair_origin','pair_value','result_value')})
                        merged={k:np.concatenate([o[k] for o in outputs]) for k in outputs[0]}
                        # Actual carried origin must resolve to the source row chosen by Run 1.
                        np.testing.assert_array_equal(merged['pair_origin'],c[merged['ptr1']])
                        out=audit(d,merged['ptr1'],merged['ptr2'],merged['pair_origin']-offset,merged['pair_value'],merged['result_value'])
                        result[key][f'{case}-{scale}']={'whole_graphs':out['whole_graphs'],'run1_complete':out['run1']['complete_graphs'],
                            'run2_complete':out['run2']['complete_graphs'],'run1_correct':out['run1']['correct'],'run2_correct':out['run2']['correct']}
            print(key,{k:v['whole_graphs'] for k,v in result[key].items()},flush=True)
    (a.root/'stride-probe.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
