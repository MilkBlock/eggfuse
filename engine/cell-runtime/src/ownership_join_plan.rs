//! Re-prove observed dual-source candidates from typed query atoms. The output
//! uses the existing Shape representation, plus source-local relocation maps.
use super::*;

#[derive(Serialize)]
struct Compiled {
    pattern: Pattern,
    frame_offsets: [usize; 2],
    symbol_maps: [Vec<usize>; 2],
    shape: Shape,
    aliased_symbols: usize,
}
fn representative(parent:&[usize],mut n:usize)->usize {
    while parent[n]!=n {n=parent[n];}n
}
fn compile(p:&Program,plan:&super::super::super::Plan,pattern:Pattern)->Result<Compiled> {
    if pattern.components.len()!=2 {return Err("dual-source arity".into());}
    let rule=p.rules.get(pattern.rule).ok_or("dual-source rule")?;
    let shapes=pattern.components.iter().map(|(id,codes)| {
        let shape=plan.composition.shapes.get(*id).ok_or("dual-source shape")?;
        if codes.len()!=shape.programs.len() {return Err("dual-source frame count".into());}
        for (&code,&program) in codes.iter().zip(&shape.programs) {
            if plan.code_programs.get(code)!=plan.programs.get(program) {return Err("dual-source code wiring".into());}
        }
        Ok(shape)
    }).collect::<Result<Vec<_>>>()?;
    if shapes.iter().map(|s|s.programs.len()).sum::<usize>()>plan.composition.max_frames {
        return Err("dual-source frame bound".into());
    }
    let mut seen=BTreeSet::new();
    let mut slots=BTreeMap::<usize,Vec<(usize,usize)>>::new();
    for &(entry,component,frame,op) in &pattern.anchors {
        if !seen.insert(entry) {return Err("duplicate dual-source query Entry".into());}
        let atom=*plan.entries[pattern.rule].get(entry).ok_or("dual-source query Entry")?;
        let query=&rule.query[atom];
        let Call::Table(table)=query.call else {return Err("dual-source primitive anchor".into());};
        if !p.tables[table].constructor || !p.tables[table].virtual_fact {return Err("mutable dual-source anchor".into());}
        let shape=shapes.get(component).ok_or("dual-source component ordinal")?;
        let code=*pattern.components[component].1.get(frame).ok_or("dual-source frame ordinal")?;
        if plan.code_operators[code].get(op as usize)!=Some(&table) {return Err("dual-source operator".into());}
        let program=&plan.programs[shape.programs[frame]];
        let fields=program.fields.get(op as usize).ok_or("dual-source operation")?;
        if fields.len()!=query.args.len() {return Err("dual-source field arity".into());}
        for (arg,field) in query.args.iter().zip(fields) {
            if let (Arg::Slot(slot),Some(local))=(arg,field) {
                slots.entry(*slot).or_default().push((component,shape.ports[frame][*local]));
            }
        }
    }
    let mut proved=Vec::new();
    for (slot,mut sites) in slots {
        sites.sort_unstable();sites.dedup();
        if sites.iter().map(|s|s.0).collect::<BTreeSet<_>>().len()>1 {proved.push((slot,sites));}
    }
    // The profile cannot invent an equality or omit a required endpoint. Actual
    // receipts must still establish these exact query atoms at runtime.
    if proved.is_empty() || proved!=pattern.shared_slots {return Err("dual-source substitutions differ from typed query".into());}
    let offsets=[0,shapes[0].signals.len()];
    let total=shapes.iter().map(|s|s.signals.len()).sum::<usize>();
    let mut parent=(0..total).collect::<Vec<_>>();
    for (_,sites) in &proved {
        let first=offsets[sites[0].0]+sites[0].1;
        for &(component,symbol) in &sites[1..] {
            let a=representative(&parent,first);let b=representative(&parent,offsets[component]+symbol);
            parent[b]=a;
        }
    }
    let mut labels=BTreeMap::new();
    let mut map=Vec::with_capacity(total);
    for i in 0..total {
        let next=labels.len();let r=representative(&parent,i);
        map.push(*labels.entry(r).or_insert(next));
    }
    let symbol_maps=[map[..offsets[1]].to_vec(),map[offsets[1]..].to_vec()];
    let frame_offsets=[0,shapes[0].programs.len()];
    let mut joined=Shape{signals:vec![Arc::new(Vec::new());labels.len()],
        origins:vec![(usize::MAX,usize::MAX);labels.len()],..Shape::default()};
    for (component,shape) in shapes.iter().enumerate() {
        joined.programs.extend(&shape.programs);
        for ports in &shape.ports {
            joined.ports.push(Arc::new(ports.iter().map(|&s|symbol_maps[component][s]).collect()));
        }
        for (symbol,steps) in shape.signals.iter().enumerate() {
            let target=symbol_maps[component][symbol];
            if joined.origins[target].0==usize::MAX {
                let (frame,local)=shape.origins[symbol];
                joined.origins[target]=(frame_offsets[component]+frame,local);
            }
            Arc::make_mut(&mut joined.signals[target]).extend(steps.iter().map(|s|Instruction{
                frame:frame_offsets[component]+s.frame,op:s.op}));
        }
    }
    for steps in &mut joined.signals {
        let steps=Arc::make_mut(steps);steps.sort_unstable_by_key(|s|(s.frame,s.op));steps.dedup();
    }
    Ok(Compiled{pattern,frame_offsets,symbol_maps,shape:joined,aliased_symbols:total-labels.len()})
}
impl Graph {
    /// Compile candidates, not installed transitions. Dynamic admission and old
    /// address/query-class migration remain mandatory before runtime takeover.
    pub fn compile_multi_source_candidates(&self,source:&J,trace:&J)->Result<J> {
        if !source.is_string() || self.program.artifact.get("sha256")!=Some(source) {
            return Err("multi-source program identity mismatch".into());
        }
        if trace["schema"]!="matched-multi-source/v1" || trace["inconsistent_slots"]!=0 || trace["dropped_patterns"]!=0 {
            return Err("incomplete multi-source trace".into());
        }
        let rows=trace["patterns"].as_array().ok_or("missing multi-source patterns")?;
        if rows.len()>4096 {return Err("multi-source candidate limit".into());}
        let mut compiled=Vec::new();let mut wider=0;let mut over_bound=0;
        for row in rows {
            let pattern:Pattern=serde_json::from_value(row["pattern"].clone()).map_err(|e|e.to_string())?;
            if pattern.components.len()!=2 {wider+=1;continue;}
            // Reject forged/out-of-range shapes before classifying the bound.
            let frames=pattern.components.iter().map(|(id,_)|
                self.program.cell_ownership.composition.shapes.get(*id).map(|s|s.programs.len()).ok_or("multi-source shape"))
                .collect::<std::result::Result<Vec<_>,_>>()?.into_iter().sum::<usize>();
            if frames>self.program.cell_ownership.composition.max_frames {over_bound+=1;continue;}
            let candidate=compile(&self.program,&self.program.cell_ownership,pattern)?;
            compiled.push(json!({"compiled":candidate,"observed":row["counts"]}));
        }
        Ok(json!({"schema":"compiled-dual-source/v1","source_program":source,"candidates":compiled,
            "unsupported_wider_patterns":wider,"over_frame_bound_patterns":over_bound,
            "scope":"typed candidate layouts using ordinary Cell Shape; not installed or a runtime takeover",
            "runtime_obligations":["exact matched receipt and component identity","visibility and pending/read-epoch exclusion",
                "old stable-field and PortRef addresses","complete query-class masks for all merged uses",
                "boundary-route replacement and source-address migration","source-local retirement and restoration"]}))
    }
}
