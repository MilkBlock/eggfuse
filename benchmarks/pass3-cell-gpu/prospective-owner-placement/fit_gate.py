"""Fit the same physical return head on actions which occurred under natural placement."""
import hashlib
import json


def fit(paths, output):
    import torch
    torch.set_num_threads(1)
    samples=[]
    train={}
    for name,path in zip(("dot-product","stable-argmax"),paths):
        row=json.loads(path.read_bytes())[name]["defer/merge"]
        events=row["events"]
        assert all(e["selected"] for e in events) and len(events)==row["issued"]
        dataset=[(e["features"],e["saved_bytes"]) for e in events]
        train[name]={"events":len(dataset),"source":row["source_sha"],"samples_sha":hashlib.sha256(json.dumps(dataset,separators=(",",":")).encode()).hexdigest()}
        samples.extend(dataset)
    x=torch.tensor([k for k,_ in samples],dtype=torch.float64)/8.
    y=torch.tensor([v for _,v in samples],dtype=torch.float64)/256.
    # The previous prepared-data regression's model, input normalization,
    # optimizer, regularizer, update count and dyadic export are held fixed.
    w=torch.zeros(8,dtype=torch.float64,requires_grad=True)
    b=torch.zeros((),dtype=torch.float64,requires_grad=True)
    opt=torch.optim.Adam([w,b],lr=.04)
    for _ in range(160):
        loss=(x@w+b-y).square().mean()+.001*(w.square().mean()+b.square())
        opt.zero_grad();loss.backward();opt.step()
    rounded=lambda t:torch.round(t.detach()*4096)/4096
    frozen=dict(weights=rounded(w/8).tolist(),intercept=rounded(b).item(),training=train)
    output.write_text(json.dumps(frozen,indent=1)+"\n")
    return frozen
