"""Verify the combined native arms and the original header tag and fact ledgers."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(n):return json.loads((HERE/n).read_bytes())
def check():
    for f,h in load("manifest.json")["files"].items():assert hashlib.sha256((HERE/f).read_bytes()).hexdigest()==h,f
    data=load("results.json");assert set(data)=={"sum-bits","3mm"}
    for case,t in data.items():
        rows=t["arms"];assert set(rows)=={"leaf","merge","partial2","both"};b=rows["leaf"]
        for name,r in rows.items():
            for k in ("runs","rhs_count","state_sha","digests","root_commits_sha","root_fresh_sha","unions_sha","events_sha","birth_sha","export_original_sha","coalesced_sha","owned_births","effective_births"):assert r[k]==b[k],(case,name,k)
            assert r["packets"]==sum(r["emitted_roots"])+r["selected_children"] and r["fept"]==r["effective_births"]/r["packets"]
            assert sum(v["new"] for v in r["origin_partition"].values())==r["owned_births"]
            assert sum(v["visible"] for v in r["origin_partition"].values())==r["effective_births"]
            w=r["wire"];c=w["counts"];assert sum(c.values())==sum(r["emitted_roots"])
            assert c.get("spine",0)+c.get("both",0)==r["strict_counts"].get("tagged",0)
            assert c.get("merge",0)+c.get("both",0)==r["strict"]["tagged"] and w["bitmaps_bytes"]==r["strict"]["tag_bytes"]
            for role,e in w["examples"].items():
                word=int.from_bytes(bytes(e["original_header_le"]),"little")
                assert word&0xffffffff==e["template"] and ((word>>32)&0x7fffffff)==e["spine_program"]
                signed=bool(e["spine_program"]);marked=bool(word>>63 and e["merge_bitmap_byte"]&(1<<(e["lane"]%8)))
                assert role==("both" if signed and marked else "spine" if signed else "merge" if marked else "none")
            if name in ("merge","both"):
                side=rows["partial2"] if name=="both" else b
                m=r["verified_internal"];s=r["strict"]
                assert m["verified_leaf_physical_returns"]==s["entered"]==s["fresh"]+s["interned"]
                assert m["internal_visible"]==sum(v["visible"] for k,v in r["origin_partition"].items() if k.endswith("/merge_internal"))
                assert m["suppressed_child_proposals"]==side["selected_children"]-r["selected_children"]
            if name in ("partial2","both"):assert r["links"]==r["strict_counts"]["source_commits"] and r["link_depth"].get("2",0)>0
            assert len(r["ms"])==len(r["wall_ms"])==4
        f=t["faults"];assert set(f)=={"merge_bit","spine_bit","old_ref","old_version","stale_partial_fallback"}
        assert all(f[k][0]<b["runs"] for k in ("merge_bit","spine_bit","old_ref","old_version"))
        assert f["stale_partial_fallback"]["state_sha"]==b["state_sha"] and f["stale_partial_fallback"]["partition"]["stale_refs"]>0
    assert 'maximum 31-bit Spine code' in (HERE/"header-test.txt").read_text()
    print("Two source schedules, four native arms, encoded header/bitmap tags, disjoint origins, direct merge returns and fallback controls agree.")
if __name__=="__main__":check()
