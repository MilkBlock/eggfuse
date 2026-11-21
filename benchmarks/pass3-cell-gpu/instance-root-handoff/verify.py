"""Verify archived native end points, issuance and transfer counts and normal-path RSS."""
from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parent

def load(name):
    return json.loads((HERE/name).read_bytes())


def main():
    for f,digest in load("manifest.json")["files"].items():
        assert hashlib.sha256((HERE/f).read_bytes()).hexdigest()==digest,f
    data=load("results.json");rss=load("rss.json")
    assert set(data)==set(rss)=={"conjugate-gradient","3mm"}
    same=("rhs","raw","multi","wire_hash","commits","physical","source_pass_rhs","root_ids","root_parents",
          "nested_ids","children","state_sha","single_winners","multi_winners","cells","direct_cells",
          "root_allocated","root_row_decodes","root_header_checks","owned_slot_transfers","queue","scores","events")
    for case,arms in data.items():
        ctl=arms["directory"];fast=arms["instance"]
        assert all(ctl[k]==fast[k] for k in same)
        for name,row in (("directory",ctl),("instance",fast)):
            assert row["aligned"] and all(row["checks"].values())
            assert row["rhs"]==row["neural_rhs"]==row["applied"]==arms["vanilla"]["rhs"]
            assert len(row["ms"])==len(row["wall_ms"])==len(row["phase_ms"])==6
            assert len(rss[case][name]["bytes"])==3
            assert row["normal_claims"]["counts"]["archived_comparisons"]==0
        ref=ctl["normal_claims"];native=fast["normal_claims"];audit=fast["claims"]
        assert ref["tickets"]==native["counts"]["attached"]==audit["tickets"]>0
        assert 0<native["counts"]["transferred"]==audit["counts"]["archived_comparisons"]<=ref["tickets"]
        assert ref["directory_bytes"]>0 and native["directory_bytes"]==native["tickets"]==0
        assert "instance claim disagrees" in arms["corruption"]["error"] and arms["corruption"]["completed_runs"]<arms["vanilla"]["runs"]
    print("Two complete neural/source runs, all audited and physical endpoints, corruption controls, resident wall samples and RSS passed.")

if __name__=="__main__":main()
