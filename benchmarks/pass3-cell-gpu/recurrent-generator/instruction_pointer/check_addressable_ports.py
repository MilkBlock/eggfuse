"""Check legal pointer domains, seeded identities, and updates across skipped snapshots."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from addressable_ports import AddressablePorts
from history import History,Snapshot
from typed_content import TypedContentCatalog


def domains():
    tables={0:[(1,0),(2,0)],1:[(2,0),(2,0)],2:[(3,0)],3:[(1,0)]}
    cat=SimpleNamespace(atoms=tables,seminaive=[True,True,True,False])
    projector=AddressablePorts(cat)
    ports=[SimpleNamespace(table=t,version=v) for t in (1,2,3,4) for v in (1,3,5)]
    for rules in ({0:5,1:3,2:5},{0:6},{1:5},{3:6},{}):
        snapshot=Snapshot(1,6,rules,ports,[])
        seen=projector.project(snapshot)
        retained={id(p) for p in seen.ports}
        for rid,wm in rules.items():
            atoms=tables[rid]
            for pivot,(table,_) in enumerate(atoms):
                roots=[p for p in ports if p.table==table and (not cat.seminaive[rid] or p.version>=wm)]
                for root in roots:
                    assert id(root) in retained
                    for role,(other,_) in enumerate(atoms):
                        if role==pivot: continue
                        assert all(id(p) in retained for p in ports if p.table==other and
                                   (not cat.seminaive[rid] or role>pivot or p.version<wm))
        assert not any(p.table==4 for p in seen.ports)
        if rules=={0:6} or not rules:assert not seen.ports


def history(folder):
    cat=TypedContentCatalog(json.loads((folder/'program.json').read_bytes()))
    for skip in (False,True):
        old,new=History(cat,1703),History(cat,1703,cache_ports=True)
        with (folder/'memory.jsonl').open() as data:
            for line in data:
                frame=json.loads(line)
                materialize=not skip or frame['run']%3!=1
                assert old.snapshot(frame,materialize)==new.snapshot(frame,materialize)
                assert old.names==new.names


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path)
    a=p.parse_args()
    domains()
    history(a.folder)
