"""Causal checks on native histories, without learning or providing bindings to the Actor."""
import argparse
from dataclasses import replace
from pathlib import Path
import torch

from actor import InstructionActor
from history import load


def check_live_fields(model,cat,frame,nodes):
    from itertools import combinations
    mem=model.memory(cat,frame,nodes)
    zeros=nodes.new_zeros(len(mem.ports))
    by_table={}
    for j,port in enumerate(mem.ports):
        by_table.setdefault(port.table,[]).append(j)
    for (rid,src,dest),links in cat.field_links.items():
        if not links or rid not in frame.rules:
            continue
        atoms=cat.atoms[rid]
        targets=by_table.get(atoms[dest][0],[])
        if len(targets)<2:
            continue
        for left,right in combinations(by_table.get(atoms[src][0],[]),2):
            a=model.related_fields(cat,mem,rid,[(src,left)],dest,zeros)[targets]
            b=model.related_fields(cat,mem,rid,[(src,right)],dest,zeros)[targets]
            if torch.allclose(a-a[0],b-b[0]):
                continue
            ports=list(frame.ports)
            ports[left]=replace(ports[left],hashes=ports[right].hashes)
            changed=model.memory(cat,replace(frame,ports=ports),nodes)
            assert not torch.allclose(mem.keys[left],changed.keys[left])
            assert torch.equal(changed.fields[left],mem.fields[right])
            return True
    return False


def check(directory):
    torch.manual_seed(1703)
    torch.set_num_threads(1)
    model = InstructionActor().eval()
    cat, snapshots = load(directory,19)
    _, renamed = load(directory,23)
    with torch.no_grad():
        nodes = model.template_graph(cat)
        first = next(i for i,s in enumerate(snapshots) if any(p.kind=='repair' for p in s.ports))
        assert first > 0 and all(p.kind!='repair' for p in snapshots[first-1].ports)
        s = snapshots[first]
        idx = next(i for i,p in enumerate(s.ports) if p.kind=='repair')
        mem = model.memory(cat,s,nodes)
        port = s.ports[idx]
        a,b = port.inputs
        swapped = replace(port,inputs=((a[0],b[1]),(b[0],a[1])))
        ports = list(s.ports)
        ports[idx] = swapped
        ordered = model.memory(cat,replace(s,ports=ports),nodes)
        assert not torch.allclose(mem.keys[idx],ordered.keys[idx])
        altered = model.memory(cat,s,nodes,{p.address[0]:torch.ones(model.width) for p in s.ports})
        assert torch.equal(mem.keys[idx],altered.keys[idx])
        assert any(not torch.equal(mem.keys[j],altered.keys[j]) for j,p in enumerate(s.ports) if p.kind=='generated')
        for frame,other in zip(snapshots,renamed,strict=True):
            m1,m2 = model.memory(cat,frame,nodes),model.memory(cat,other,nodes)
            torch.testing.assert_close(m1.keys.sort(dim=0).values,m2.keys.sort(dim=0).values)
            # This only exercises the address head. Labels never enter free decoding.
            for rid,refs in frame.targets:
                h,_,_ = model.actions(cat,m1,0)
                actual,losses = model.references(cat,m1,h,rid,refs)
                assert actual==refs and all(torch.isfinite(v) for v in losses)
    with torch.no_grad():
        model.field_pointer=True
        assert any(check_live_fields(model,cat,s,nodes) for s in snapshots), 'missing distinct first reads'
    print('system output visibility, ordered collision operands, optional latent, renamed keys, teacher action support: pass')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('program_directory',type=Path)
    check(ap.parse_args().program_directory)
