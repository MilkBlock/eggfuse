import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rep(s, a, b):
    if s.count(a) != 1:
        raise ValueError(f"unsupported source {a[:72]} ({s.count(a)})")
    return s.replace(a, b)


def install(crate):
    src = crate / "src"
    p = src / "graph.rs"
    s = p.read_text()
    s = rep(
        s,
        "pub struct Graph {",
        "pub struct Graph {\n pub(crate) header_mode:u8,pub(crate) header_audit:bool,pub(crate) headers:std::cell::RefCell<HeaderExchange>,",
    )
    s = rep(
        s,
        "            parents: Default::default(),",
        "            header_mode:0,header_audit:false,headers:Default::default(),\n            parents: Default::default(),",
    )
    p.write_text(s + '\ninclude!("header_banks.rs");\n')
    shutil.copyfile(HERE / "banks.rs", src / "header_banks.rs")
    p = src / "runtime_completion.rs"
    s = p.read_text()
    s = rep(
        s,
        "        crate::ordinary_witness::changed_frame_rows(&self.graph);",
        "        self.graph.header_publish();\n        crate::ordinary_witness::changed_frame_rows(&self.graph);",
    )
    p.write_text(s)
    p = src / "adaptive_rows.rs"
    s = p.read_text()
    s = rep(
        s,
        "struct RowEngine {",
        "struct RowEngine {\n   base_features:Vec<Option<[u8;N]>>, inner_headers:[u64;6],",
    )
    s = rep(
        s,
        '"verification":self.verify.stats,',
        '"inner_headers":self.inner_headers,"verification":self.verify.stats,',
    )
    anchor = "        let mut records = Vec::new();"
    s = rep(
        s,
        anchor,
        """        if cert && g.header_mode>=2 {
            let b=g.header_bank(table);
            let records:Vec<SourceHeader>=b.rows.iter().map(|(d,e)|SourceHeader{source:Some(*d),version:*e,initial:initial.contains(d),dynamics:[0;4]}).collect();
            self.stats.snapshot_builds+=1;
            let records=Arc::new(records);self.snapshots.insert(table,(version,records.clone()));return Ok(records)
        }
"""
        + anchor,
    )
    begin = s.index("        let mut base = self.features(")
    end = s.index("        let model =", begin)
    old = s[begin:end]
    s = (
        s[:begin]
        + """        let base=if g.header_mode!=0 && self.rows.base_features.get(rid).and_then(|v|*v).is_some(){self.rows.base_features[rid].unwrap()}else{
"""
        + old
        + """        if g.header_mode!=0 {self.rows.base_features.resize(self.rows.base_features.len().max(rid+1),None);self.rows.base_features[rid]=Some(base);}base};
        let mut header_start=phase;
        macro_rules! header_part{($i:expr)=>{if let Some(start)=header_start{let end=RowClock::now();self.rows.inner_headers[$i]+=(end-start).as_nanos()as u64;header_start=Some(end);}}}
        header_part!(0);
"""
        + s[end:]
    )
    s = rep(
        s,
        "            self.rows.stats.proof_empty_calls += 1;",
        "            header_part!(1);self.rows.stats.proof_empty_calls += 1;",
    )
    s = rep(
        s,
        "        let sources: &[SourceHeader] = if let Some(pivot)",
        "        header_part!(1);\n        let sources: &[SourceHeader] = if let Some(pivot)",
    )
    s = rep(
        s,
        "        let filtered: Vec<SourceHeader>;",
        "        header_part!(2);\n        let filtered: Vec<SourceHeader>;",
    )
    anchor = """            filtered = sources
                .iter()
                .copied()
                .filter(|v| v.version >= wm)
                .collect();"""
    s = rep(
        s,
        anchor,
        """            filtered=if g.header_mode>=2{
                let Call::Table(t)=r.query[p.pivot.unwrap()].call else{unreachable!()};
                let view=g.header_bank(t);g.header_offsets(&view,wm).iter().map(|&i|sources[i as usize]).collect()
            }else{sources.iter().copied().filter(|v|v.version>=wm).collect()};""",
    )
    s = rep(s, "        let guarded;", "        header_part!(3);\n        let guarded;")
    s = rep(
        s,
        "        let n = sources.len();",
        "        header_part!(4);\n        let n = sources.len();",
    )
    s = rep(
        s,
        "        if let Some(t) = phase {",
        "        header_part!(5); let _=header_start;\n        if let Some(t) = phase {",
    )
    p.write_text(s)
    p = src / "adaptive_rows.rs"
    s = p.read_text()
    s = rep(
        s,
        "inner_headers:[u64;6],",
        "inner_headers:[u64;6], snapshot_ns:[u64;2],initial_hash:Option<rustc_hash::FxHashSet<Dependency>>,",
    )
    s = rep(
        s,
        '"inner_headers":self.inner_headers,',
        '"snapshot_ns":self.snapshot_ns,"inner_headers":self.inner_headers,',
    )
    s = rep(
        s,
        "        let version = g.query_versions[table];",
        "        let t=self.profile.then(RowClock::now); let version = g.query_versions[table];",
    )
    s = rep(
        s,
        "            return Ok(rows.clone());",
        "            if let Some(t)=t{self.snapshot_ns[0]+=t.elapsed().as_nanos()as u64;}return Ok(rows.clone());",
    )
    s = rep(
        s,
        "            let b=g.header_bank(table);",
        "            let b=g.header_bank(table);let born=self.initial_hash.get_or_insert_with(||initial.iter().copied().collect());",
    )
    s = rep(s, "initial:initial.contains(d)", "initial:born.contains(d)")
    s = rep(
        s,
        "return Ok(records)",
        "if let Some(t)=t{self.snapshot_ns[1]+=t.elapsed().as_nanos()as u64;}return Ok(records)",
    )
    s = rep(
        s,
        "        Ok(rows)\n",
        "        if let Some(t)=t{self.snapshot_ns[1]+=t.elapsed().as_nanos()as u64;}Ok(rows)\n",
    )
    p.write_text(s)
    p = src / "single_witness.rs"
    s = p.read_text()
    s = rep(
        s,
        "initial:BTreeSet<Dependency>,pub residual",
        "initial:std::sync::Arc<BTreeSet<Dependency>>,pub residual",
    )
    s = rep(
        s,
        "let initial=(0..g.program.tables.len()).flat_map(|t|g.witnesses(t)).collect();",
        "let initial:std::sync::Arc<BTreeSet<Dependency>>=std::sync::Arc::new((0..g.program.tables.len()).flat_map(|t|g.witnesses(t)).collect());g.remember_header_births(initial.clone());",
    )
    p.write_text(s)
    p = src / "adaptive_rows.rs"
    s = p.read_text()
    s = rep(
        s,
        "        if cert && g.header_mode>=2 {",
        """        if cert && g.header_mode>=6{
            let data=g.direct_headers(table);self.snapshots.insert(table,(version,data.clone()));self.stats.snapshot_builds+=1;
            if let Some(t)=t{self.snapshot_ns[1]+=t.elapsed().as_nanos()as u64;}return Ok(data)
        }
        if cert && g.header_mode>=2 {""",
    )
    p.write_text(
        s
        + "\nimpl SourceHeader{pub(crate) fn from_published(d:Dependency,e:u64,initial:bool)->Self{Self{source:Some(d),version:e,initial,dynamics:[0;4]}}pub(crate) fn is_initial(&self)->bool{self.initial}}\n"
    )
    p = src / "adaptive_verification.rs"
    s = p.read_text()
    s = rep(
        s,
        "        if let Some(&(v, e)) = self.frontiers.get(&t)",
        "        if g.header_mode>=2{return g.header_bank(t).max;}\n        if let Some(&(v, e)) = self.frontiers.get(&t)",
    )
    p.write_text(s)
    p = src / "single_epochs.rs"
    s = p.read_text()
    s = rep(
        s,
        "let old = bank.iter().filter(|x| x.version < wm).count();",
        """let old=if g.header_mode>=2{let Call::Table(t)=g.program.rules[rid].query[pivot].call else{unreachable!()};let b=g.header_bank(t);bank.len()-g.header_offsets(&b,wm).len()}else{bank.iter().filter(|x|x.version<wm).count()};""",
    )
    anchor = """                        for w in g.witnesses(t){"""
    s = rep(
        s,
        anchor,
        """                        if g.header_mode>=2{
                            let b=g.header_bank(t);let offsets=g.header_offsets(&b,wm);visible=b.len();
                            for &i in offsets.iter(){let w=b.at(i as usize).0;if let Some(row)=g.row(w)? && !row.hidden{batch.push(row);}}
                            state.typed.stats.skipped_cold_rows+=(visible-offsets.len())as u64;
                        }else{for w in g.witnesses(t){""",
    )
    s = rep(
        s,
        "                        marginal_count=Some(visible);cold=batch;",
        "                        }marginal_count=Some(visible);cold=batch;",
    )
    s = rep(
        s, "struct SingleEpochs {", "struct SingleEpochs {\n    router:HeaderRouter,"
    )
    s = rep(
        s,
        '"typed":self.typed.stats',
        '"typed":self.typed.stats,"header_router":self.router.stats',
    )
    s = rep(
        s,
        "        let mut verdicts = [0u8; 1 << B];",
        """        if (g.header_mode==4 || g.header_mode==7) && let (Some(c),Some(keys))=(shared,typed.as_deref()) && let Some((keep,probes))=state.router.route(g,owner,c,bank,keys,&proofs,wm,&code){
            let skipped=bank.len()-keep.len();counts.pruned+=skipped as u64;counts.hashed+=skipped as u64;counts.probes+=probes;if keep.is_empty(){counts.dead_calls+=1}return Ok(Some(keep))
        }
        let mut verdicts = [0u8; 1 << B];""",
    )
    p.write_text(s + '\ninclude!("header_reverse.rs");\n')
    shutil.copyfile(HERE / "reverse.rs", src / "header_reverse.rs")
    p = crate / "examples/joint_witness_session.rs"
    s = p.read_text()
    anchor = "        let initial_cells = runtime.graph.stats.cells_created;"
    s = rep(
        s,
        anchor,
        """        runtime.graph.configure_header_view(req["header_mode"].as_u64().unwrap_or(0),audit)?;
"""
        + anchor,
    )
    s = rep(
        s,
        '        report["root_recipe"]=',
        '        report["header_view"]=runtime.graph.header_view_report();\n        report["root_recipe"]=',
    )
    p.write_text(s)
