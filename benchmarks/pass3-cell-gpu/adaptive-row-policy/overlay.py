"""Route disjoint typed candidate address ranges to shared recurrent CPU scoring rows."""

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def swap(s, old, new):
    if s.count(old) != 1:
        raise ValueError(f"unsupported source near {old[:80]!r}")
    return s.replace(old, new)


def install(crate):
    p = crate / "src/single_witness.rs"
    s = p.read_text()
    s = swap(
        s, "pub(crate) struct Trial{", "pub(crate) struct Trial{\n    rows:RowEngine,"
    )
    s = swap(
        s,
        "        Ok(Self{plans,initial,residual,",
        "        Ok(Self{rows:RowEngine::default(),plans,initial,residual,",
    )
    a = s.index("        let candidates=if let Some(a)=p.pivot")
    b = s.index("self.work[0]+=n as u64;", a)
    original = s[a:b]
    original = swap(
        original,
        "            delivered+=usize::from(send);",
        """            if self.rows.detailed{self.rows.observe(self.serial,w,row.as_ref().map_or(0,|r|r.epoch),rid,s,send);}
            delivered+=usize::from(send);""",
    ).replace(
        "        let n=offers.len();",
        "        let n=offers.len();(offers,delivered,score_sum,n)",
    )
    s = (
        s[:a]
        + """        let (offers,delivered,score_sum,n)=if self.rows.active {
            self.generate_rows(g,rid,wm,&p)?
        }else{
"""
        + original
        + "\n        };"
        + s[b:]
    )
    s = swap(
        s,
        "            self.work[2]+=1;",
        """            if self.rows.active && self.rows.prune && r.seminaive && p.pivot.is_some()
                && token.version<wm && p.order.iter().all(|&i|matches!(r.query[i].call,Call::Primitive(..))){
                self.rows.stats.stale_proofs+=1;continue;
            }
            self.work[2]+=1;""",
    )
    s = swap(
        s,
        'json!({"mode":self.mode,',
        'json!({"adaptive_rows":self.rows.report(),"mode":self.mode,',
    )
    s = swap(
        s,
        "        let mut answers=Vec::new();let mut hist=BTreeMap::new();",
        "        self.rows.verify.begin(g,r,&p,rid);\n        let mut answers=Vec::new();let mut hist=BTreeMap::new();",
    )
    s = swap(
        s,
        "            let matched=self.check(g,r,&p,&token,wm)?;",
        "            let matched=if self.rows.verify.mode==0{self.check(g,r,&p,&token,wm)?}else{self.rows.verify.check(g,r,&p,&token,wm,&mut self.work)?};",
    )
    p.write_text(
        s + '\ninclude!("adaptive_rows.rs");\ninclude!("adaptive_verification.rs");\n'
    )
    shutil.copyfile(HERE / "verification.rs", crate / "src/adaptive_verification.rs")
    shutil.copyfile(HERE / "rows.rs", crate / "src/adaptive_rows.rs")
    p = crate / "src/runtime.rs"
    s = p.read_text()
    s = swap(
        s,
        "    pub fn single_report(&self)",
        """    pub fn configure_rows(&mut self,config:&serde_json::Value,audit:bool)->Result<()>{
        self.stage_spine.single.as_mut().ok_or("missing single policy")?.configure_rows(config,audit)
    }
    pub fn single_report(&self)""",
    )
    p.write_text(s)
    p = crate / "examples/joint_witness_session.rs"
    s = p.read_text()
    s = swap(
        s,
        "        let initial_cells = runtime.graph.stats.cells_created;",
        """        if !baseline{runtime.configure_rows(&req["rows"],audit)?;}
        let initial_cells = runtime.graph.stats.cells_created;""",
    )
    p.write_text(s)

    p = crate / "src/joint_root.rs"
    s = p.read_text()
    s = swap(s, "enum Body {", "enum Body {\n    RowPage(RootPage,usize),")
    s = swap(
        s,
        "        Body::Resident(decoded)=>",
        "        Body::RowPage(page,slot)=>return page.decode(*slot),\n        Body::Resident(decoded)=>",
    )
    # Packed proposals carry the same dynamic refs as resident and shared-wire recipes.
    p.write_text(s + '\ninclude!("adaptive_root_page.rs");\n')
    shutil.copyfile(HERE / "page.rs", crate / "src/adaptive_root_page.rs")
