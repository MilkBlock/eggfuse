import argparse
import json
from pathlib import Path
import sys
import torch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'join-port-diagnosis'))
from transfer import JoinReader
from frozen_read import FrozenRead

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('checkpoint','out'):
        p.add_argument(name,type=Path)
    args=p.parse_args()
    model=JoinReader(32,True).eval()
    model.load_state_dict(torch.load(args.checkpoint,weights_only=True))
    reader=FrozenRead(model)
    if not reader.full_overlap_only:
        raise ValueError('native wide confirmation requires a full-overlap checkpoint')
    args.out.write_text(json.dumps(dict(left=reader.left.tolist(),sender=reader.sender.tolist(),
        follow=reader.pair[:,:,4].tolist()),indent=2)+'\n')
