"""Attribute each signed Let hop to the actual source execution of its prefix."""
from collections import Counter


def validate(data, cfg):
    strict = data["strict_named"]
    links = strict["signed_commits"]
    source = {row[2]:row for row in data["root_recipe"]["commits"]}
    born = {row[0]:row for row in data["constructor_births"]["rows"]}
    producers = {row[0]:row[5] for row in data["root_recipe"]["fresh"]}
    returned = {(root, parent, op, child, producers[cell], f, pos, epoch, run)
                for root,parent,op,child,cell,f,pos,epoch,run in strict["actual_reused_returns"]
                if cell in producers}
    heads = {tuple(path[0]) for path in cfg["library"] if len(path)==1}
    pairs = {tuple(map(tuple,path)) for path in cfg["library"] if len(path)==2}
    terminals = {row["consumer"] for row in strict["set_commits"]}
    recorded = strict.get("depth_caps") or []
    caps = {serial: action for serial,_,action in recorded}
    if len(caps)!=len(recorded):
        raise ValueError("duplicate root depth decision")
    prefix_commits = {(root,tuple(map(tuple,path)),tuple(map(tuple,ports))):(serial,run)
                      for serial,root,path,ports,run in links}
    depth = Counter()
    deep_roots = Counter()
    reused = 0
    for serial,root,path,ports,run in links:
        n=len(path)
        depth[n]+=1
        if n>2:
            deep_roots[path[0][0]]+=1
        if n>cfg["depth"] or n!=len(ports) or not n:
            raise ValueError("invalid path depth")
        if "depth_reader" in cfg and path[0][0]==cfg["depth_reader"]["rule"]:
            if root not in caps or caps[root]==1 and n>2:
                raise ValueError(("unlicensed root depth",root,n))
        if serial in terminals:
            continue  # Checked separately by the typed Set validator.
        parent,op,child=path[-1]
        f,pos,epoch,source_run=ports[-1]
        if n==1:
            prior=root
            allowed=tuple(path[0]) in heads
        else:
            prior,prior_run=prefix_commits[root,tuple(map(tuple,path[:-1])),tuple(map(tuple,ports[:-1]))]
            allowed=(tuple(path[-2]),tuple(path[-1])) in pairs and prior_run==source_run and prior not in terminals
        if not allowed or source[prior][3]!=parent or source[serial][3]!=child or run<=source_run:
            raise ValueError(("unproved path prefix",serial,prior,path))
        proof=dict(atom=0,row=dict(Fact=dict(cell=f,op=pos)),version=epoch)
        if proof not in source[serial][6]:
            raise ValueError(("wrong consumer witness",serial))
        fact=born.get((f<<32)|pos)
        if fact and fact[2]==epoch and fact[4]==prior and pos==op and producers.get(f)==prior:
            continue
        if (root,parent,op,child,prior,f,pos,epoch,source_run) not in returned:
            raise ValueError(("no actual constructor return",serial,prior,path,ports))
        reused+=1
    return dict(depth=dict(sorted(depth.items())), reused_commits=reused, deep_roots=dict(sorted(deep_roots.items())))
