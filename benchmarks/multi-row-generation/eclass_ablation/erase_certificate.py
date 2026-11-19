"""Post-hoc intervention: withdraw only granted class links at consumer input."""
import argparse
import json
from pathlib import Path
import torch
import numpy as np
from model import AliasSystem
from encoder import ARMS
from fit import study, device, transfer, digest, SEEDS
from data import dataset, audit
from evaluate import host


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args()
    _,_,held,schema=study();dev=device();out={}
    for arm in ARMS:
        for seed in SEEDS:
            name=f'{arm}-{seed}';folder=args.root/name
            meta=json.loads((folder/'fit.json').read_text());assert meta['weight_sha256']==digest(folder/'final.pt')
            model=AliasSystem(schema,seed).to(dev)
            model.load_state_dict(torch.load(folder/'final.pt',map_location=dev,weights_only=True));model.eval()
            checks=[]
            with torch.inference_mode():
                for template in held:
                    d=dataset('test',template);args_gpu=transfer(d,slice(None),dev)
                    table=model.encoder.encode_bank(schema.bank(template,arm,dev))
                    full=model(*args_gpu,table)
                    # Active post+committed view (index 3) is replaced by the same
                    # template's post view without its local proof (index 2).
                    erased=table.index_select(0,torch.tensor([0,1,2,2],device=dev))
                    _,_,req,_,req_ports,phase,receipt,external,ep=args_gpu
                    finish,rel=model.resume(full[1],req,req_ports,phase,receipt,external,ep,
                                            erased,model.operand[1].unsqueeze(0).expand(len(req),-1,-1))
                    st1,token,interpret=host(full)
                    st2,reused,altered=host(((full[0][0],finish),full[1],rel))
                    np.testing.assert_array_equal(token,reused)
                    base=audit(d,*st1);intervention=audit(d,*st2);tr=np.asarray(base['request_legal'])
                    def row(report,scores):
                        return dict(complete=report['run2']['nonempty_complete_graphs'],wrong_parent=report['run2']['wrong_parent'],
                                    missed=report['run2']['missing'],relation_correct=int((scores.argmax(-1)==tr).sum()),
                                    relation_fp=int(((scores.argmax(-1)==1)&(tr==0)).sum()),relation_fn=int(((scores.argmax(-1)==0)&(tr==1)).sum()))
                    vals=dict(template=template['id'],base=row(base,interpret),erased=row(intervention,altered),
                              relation_changes=int((interpret.argmax(-1)!=altered.argmax(-1)).sum()),
                              finish_changed_graphs=int(np.logical_or.reduce([(st1[1][k]!=st2[1][k]).reshape(len(req),-1).any(1) for k in st2[1]]).sum()))
                    if arm in ('explicit','singleton'): assert vals['relation_changes']==vals['finish_changed_graphs']==0
                    checks.append(vals)
            out[name]=checks
    (args.root/'erase-certificate.json').write_text(json.dumps(out,indent=2)+'\n')
    print({k:sum(v['relation_changes'] for v in rows) for k,rows in out.items()})

if __name__=='__main__':main()
