"""Export trained weights or static source features for the native Rust forward pass."""
import argparse
import hashlib
import json
from pathlib import Path

from certificate import Policy, packet
import torch


def export_model(checkpoint):
    ck=torch.load(checkpoint,map_location='cpu',weights_only=True)
    net=Policy(ck['tables'],ck['rules'])
    net.load_state_dict(ck['state'])
    return dict(schema='eggfuse.cpu-forest-policy/v1',root_weight=net.root.weight.tolist(),
                root_bias=net.root.bias.tolist(),table=net.table.weight.tolist(),consumer=net.consumer.weight.tolist(),
                child_weight=net.child[0].weight.tolist(),child_bias=net.child[0].bias.tolist(),
                out_weight=net.child[2].weight[0].tolist(),out_bias=net.child[2].bias.item())


def export_inputs(program,image):
    plan=packet(image,program)
    candidates=[dict(entry=row[:4].tolist(),table=int(row[5]),direct=bool(plan['projections'][row[2]]>=0),
                     features=features.tolist()) for row,features in zip(plan['candidates'],plan['child_x'],strict=True)]
    return dict(schema='eggfuse.forest-inputs/v1',program_sha256=hashlib.sha256(program.read_bytes()).hexdigest(),
                roots=plan['roots'],root_features=plan['root_x'].tolist(),candidates=candidates)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    weights=sub.add_parser('weights');weights.add_argument('checkpoint',type=Path)
    inputs=sub.add_parser('inputs');inputs.add_argument('program',type=Path);inputs.add_argument('image',type=Path)
    for cmd in (weights,inputs):cmd.add_argument('output',type=Path)
    args=parser.parse_args()
    data=export_model(args.checkpoint) if args.mode=='weights' else export_inputs(args.program,args.image)
    args.output.write_text(json.dumps(data,separators=(',',':'),allow_nan=False)+'\n')
