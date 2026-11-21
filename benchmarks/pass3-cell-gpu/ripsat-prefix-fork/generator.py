"""Paired root-policy readout on independently archived verifier interventions."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import torch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"recurrent-generator"))
from compound_model import CompoundActor


def pair(e,name,model):
    study=e/"compound-pending-pass3-v1"
    folders=[study/sub/(name+"-1709-batch") for sub in ("paired","reject-one")]
    with np.load(folders[0]/"compound-output.npz") as z:
        c=z["claims"]
    t=int(np.flatnonzero((c[:,0,7]>0)&(c[:,1,7]>0)&(c[:,0,2]!=c[:,1,2]))[0])
    target=int(c[t,0,7]); sibling=int(c[t,1,7]); boundary=int(c[t,0,5])
    leaf=int(model.joins[int(c[t,0,1]),3]);anchor=int(c[t,0,3])
    with np.load(folders[1]/"compound-output.npz") as z:
        other=z["claims"]
        assert other[t,0,7]==0 and other[t,1,7]==sibling
        assert target not in other[:,:,7]
    with np.load(e/"recurrent-receipts-20261120"/name/"training.npz") as z:
        features=torch.from_numpy(z["features"][boundary-1:boundary])
    with np.load(folders[0]/"output.npz") as a,np.load(folders[1]/"output.npz") as b:
        image=(e/"pass3-release-reproduction-20261120"/("release-input-"+name) if name in ("sum-bits","dot-product")
               else e/"repair-bake-families-20261120"/name/"input")
        tables=json.loads((image/"ingress.json").read_text())["tables"]
        for i,table in enumerate(tables):
            live=a["meta"][:,0]==i
            width=len(table["schema"])
            np.testing.assert_array_equal(a["rows"][live,:width],b["rows"][live,:width])
        for key in ("meta","parents","unions","runs","writes","resumes"):
            np.testing.assert_array_equal(a[key],b[key])
        np.testing.assert_array_equal(a["rhs"][:,:2],b["rhs"][:,:2])
        np.testing.assert_array_equal(a["rhs"][:,4:],b["rhs"][:,4:])
        assert a["rhs"][target-1,0]==boundary and b["rhs"][target-1,0]==boundary
    arms=[]
    evidence=[]
    for folder in folders:
        with np.load(folder/"neural-output.npz") as z:
            raw=z["raw"]
            parent=int(c[t,0,0])
            code=int(z["verdict"][t,parent,0])
            ordinal=int(z["rhs_ordinal"][t,parent])
            assert (code,ordinal)==((1,int(c[t,0,2])) if not evidence else (2,0))
            evidence.append(dict(available_by_root_run=t+2,issue_run=t+1,parent_row=parent,
                                 verdict=code,committed_parent_ordinal=ordinal))
            prev=torch.from_numpy(raw[boundary-2:boundary-1,2:])
            assert target not in z["rhs_ordinal"]
        logits,roots=model.root.step(features,prev)
        np.testing.assert_array_equal(roots[0,:,8:].numpy(),raw[boundary-1,:2,8:])
        arms.append((prev,logits))
    for x,y in zip(*arms): assert torch.equal(x,y)
    ranks=np.flatnonzero(features[0,leaf*8:leaf*8+8,0].numpy()==anchor)
    return dict(issue_run=t+1,decision_run=boundary,target=target,sibling=sibling,
                prior_events=evidence,target_available_at_ranks=ranks.tolist(),identical_previous_children=True,
                equal_reconstructed_logits=True,feature_source="shared source-aligned reference capture")


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("exp",type=Path);p.add_argument("output",type=Path)
    a=p.parse_args();torch.set_num_threads(1)
    trained=a.exp/"compound-pending-pass3-v1/train-1709"
    model=CompoundActor(json.loads((trained/"policy.json").read_text())["joins"])
    model.load_state_dict(torch.load(trained/"actor.pt",map_location="cpu",weights_only=True));model.eval()
    with torch.no_grad():
        out={name:pair(a.exp,name,model) for name in ("sum-bits","dot-product","gemm-bias-relu","stable-argmax")}
    a.output.write_text(json.dumps(out,indent=2)+"\n")
