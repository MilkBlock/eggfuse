"""Verify deployed and audited root behavior, faults, physical allocation and timings."""
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"pair-source-frontier"))
from evidence import checked


def verify(folder):
    cases=checked(folder,("results.json",),("sum-bits","3mm"))
    modes={"off":0,"hash":1,"borrow":2,"atoms":6,"typed":10,"headers":18,"all":31}
    for name,arms in cases.items():
        assert set(arms)==set(modes)|{"vanilla"}
        assert all(len(r["ms"])==4 for r in arms.values())
        ref=arms["off"]
        for label,mode in modes.items():
            row=arms[label]
            prod=row["production"]
            audit=row["audit_lean"]
            assert audit["raw_omitted"]==0 and prod["archived_refs"]==0
            assert prod["raw_omitted"]==(sum(row["emitted"]) if mode&1 else 0)
            assert (prod["fused_header_reads"]>0)==bool(mode&16)
            assert (prod["typed_rows"]>0)==bool(mode&8)
            if mode&8:
                assert prod["typed_rows"]==row["emitted"][0]
                assert prod["wire_bytes_avoided"]==ref["wire_bytes"]-row["wire_bytes"]
            assert (prod["skipped_atom_checks"]>0)==bool(mode&4)
            assert (prod["multi_binds"]>0)==bool(mode&2)
            assert (prod["single_binds"]>0)==bool(mode&2)
            assert audit["archived_refs"]==prod["produced_refs"]
            assert ref["root_header_checks"]==row["root_header_checks"]+prod["skipped_atom_checks"]
            assert row["sealed"]==ref["sealed"] and row["wire_hash"]==ref["wire_hash"]
            if mode&2:
                assert prod["single_binds"]+prod["multi_binds"]==row["sealed"]
        if name=="sum-bits":
            assert set(arms["all"]["faults"])=={"1","2","3","wrong-template","wrong-port","withhold"}
            assert all(msg and n<arms["vanilla"]["runs"] for n,msg in arms["all"]["faults"].values())
    return cases


if __name__=="__main__":
    print("Verified production and audit page receipts on",len(verify(HERE)),"complete Pass 3 programs")
