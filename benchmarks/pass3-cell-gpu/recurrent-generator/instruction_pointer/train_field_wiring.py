"""Fit one field-aware readout on the observed independent inputs of higher Cells."""
import argparse
import json
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F
from torch.nn.utils.rnn import pad_sequence

from alternate_proofs import digest
from field_wiring import FieldReader,bake_routes
from higher_cell import read
from marginal_policy import splits
from ripsat_boundary import BoundaryReader, make_steps
from ripsat_layout import signatures
from ripsat_replay import unpack
from train_ripsat import layout_id


def train(root, donor_folder, baked, protocol_file, out,audit_held=False):
    protocol=splits(protocol_file)
    study=read(baked/'study.json')
    donor=read(donor_folder/'program.json')
    fixed=read(baked/'fixed.json')
    fingerprints={f:digest(baked/f) for f in ('catalog.json','codes.pt','boundary.pt','fixed.json')}
    if (set(study['training'])!=set(protocol['train']) or fixed['signatures']!=signatures(donor)
            or fingerprints['catalog.json']!=study['catalog_sha'] or fixed['catalog']!=study['catalog_sha']
            or fingerprints['codes.pt']!=fixed['codes'] or read(baked/'boundary.json')['weights']!=fingerprints['boundary.pt']):
        raise ValueError('incompatible donor, training split or graph library')
    layouts=unpack(read(baked/'catalog.json'))
    known={i for i,g in enumerate(layouts) if int(layout_id(g)[:8],16)%8}
    out.mkdir(parents=True,exist_ok=True)
    frozen=torch.load(baked/'codes.pt',weights_only=True)
    codes=frozen['codes']
    roles=[[(t,frozen['roles'][i]) for t,i in use] for use in fixed['inputs']]
    base=BoundaryReader(codes.shape[1]).eval()
    base.load_state_dict(torch.load(baked/'boundary.pt',weights_only=True))
    for name,sha in study['training'].items():
        if digest(root/name/'program.json')!=protocol['train'][name] or digest(root/name/'tape.json')!=sha:
            raise ValueError('training program changed')
    if audit_held:
        held=set(range(len(layouts)))-known
        reader=FieldReader(out,baked)
        audit={}
        with torch.no_grad():
            for name in study['training']:
                audit[name]={}
                for label,adjust in [('base',None),('field',reader)]:
                    _,audit[name][label]=make_steps(root/name,donor,layouts,held,1703,codes,roles,base,
                        grow_consumers=study['grow_consumers'],field_reader=adjust)
        (out/'held.json').write_text(json.dumps(audit,indent=2)+'\n')
        return
    routes=bake_routes(donor,layouts,out)
    logits,fields=[],[]
    counts={}
    @torch.no_grad()
    def record(uid,slot,bound,rows,ctx,keys,comparison):
        if not routes.bank[routes.uses[uid][slot]] or len(rows)<2:
            return
        logits.append(base(ctx[None],keys[None],comparison[None])[0])
        fields.append(routes.features(uid,slot,bound,rows))
    for name in study['training']:
        folder=root/name
        before=len(fields)
        _,stats=make_steps(folder,donor,layouts,known,1703,codes,roles,
                           grow_consumers=study['grow_consumers'],record_fields=record)
        counts[name]=dict(**stats['counts'],routed_training_reads=len(fields)-before)
    x=pad_sequence(fields,batch_first=True).to('mps')
    prior=pad_sequence(logits,batch_first=True,padding_value=-1e6).to('mps')
    target=torch.zeros(len(fields),dtype=torch.long,device='mps')
    torch.manual_seed(protocol['seed'])
    model=nn.Linear(3,1,bias=False).to('mps')
    nn.init.zeros_(model.weight)
    opt=torch.optim.Adam(model.parameters(),lr=protocol['lr'])
    for _ in range(protocol['epochs']):
        for ix in torch.randperm(len(fields)).split(128):
            scores=prior[ix]+model(x[ix]).squeeze(-1)
            loss=F.cross_entropy(scores,target[ix])
            opt.zero_grad()
            loss.backward()
            opt.step()
    torch.save(model.cpu().state_dict(),out/'field.pt')
    meta=dict(**fingerprints,protocol=digest(protocol_file),routes=digest(out/'routes.json'),
              weights=digest(out/'field.pt'),coefficients=model.weight.detach().flatten().tolist(),
              layouts=len(layouts),withheld=len(layouts)-len(known),unique_slot_programs=len(routes.bank),
              trained=counts,training_tapes=study['training'],device='mps')
    (out/'training.json').write_text(json.dumps(meta,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','donor','baked','protocol','out'):
        p.add_argument(k,type=Path)
    p.add_argument('--audit-held',action='store_true')
    a=p.parse_args()
    torch.set_num_threads(1)
    train(a.root,a.donor,a.baked,a.protocol,a.out,a.audit_held)
