"""Generate exact one- and two-relation witness tokens on Metal for a live Rust Run."""
import json
import os
import sys
from pathlib import Path
from time import perf_counter

os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '0'
import torch

KERNEL = (Path(__file__).resolve().parents[3] / 'engine/cell-runtime/src/gpu_bindings.metal').read_text()


def tensor(values):
    return torch.tensor(values, dtype=torch.int32, device="mps")

def main():
    shader = torch.mps.compile_shader(KERNEL)
    print(json.dumps({"device": "metal", "protocol": 1}), flush=True)
    for line in sys.stdin.buffer:
        left, right, tests, lw, rw = json.loads(line)
        left_count, right_count = len(left)//lw, len(right)//rw
        pairs = left_count*right_count
        if pairs > 2**31-1:
            raise ValueError("binding product exceeds Metal token address space")
        l, r, rules = tensor(left), tensor(right), tensor(tests or [0])
        found = []
        start = perf_counter()
        for offset in range(0,pairs,65536):
            width = min(65536,pairs-offset)
            count = torch.zeros(1,device="mps",dtype=torch.int32)
            result = torch.empty((width,2),device="mps",dtype=torch.int32)
            shape = tensor([left_count,right_count,lw,rw,len(tests)//2,offset])
            shader.bindings(l,r,rules,shape,count,result,threads=width)
            size = int(count.item())
            found.extend(result[:size].cpu().tolist())
        print(json.dumps([found,perf_counter()-start],separators=(',',':')),flush=True)

if __name__ == '__main__':
    main()
