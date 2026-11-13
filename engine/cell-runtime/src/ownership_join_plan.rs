//! Re-prove observed dual-source candidates from typed query atoms. The output
//! uses the existing Shape representation, plus source-local relocation maps.
use super::*;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(in crate::graph::cell_ownership) struct Compiled {
    pub(in crate::graph::cell_ownership) pattern: Pattern,
    pub(in crate::graph::cell_ownership) frame_offsets: [usize; 2],
    pub(in crate::graph::cell_ownership) symbol_maps: [Vec<usize>; 2],
    pub(in crate::graph::cell_ownership) shape: Arc<Shape>,
    #[serde(skip)]
    pub(in crate::graph::cell_ownership) target: usize,
    pub(in crate::graph::cell_ownership) aliased_symbols: usize,
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
    Ok(Compiled{pattern,frame_offsets,symbol_maps,shape:Arc::new(joined),target:0,aliased_symbols:total-labels.len()})
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

pub(in crate::graph::cell_ownership) type RouteKey=[(usize,usize,u32,usize);2];
pub(in crate::graph::cell_ownership) type RuleRoutes=BTreeMap<(usize,usize),BTreeMap<RouteKey,Vec<usize>>>;

// Keep every existing suffix on either source. An incomplete closure rejects
// the join instead of stealing an old productive append route at runtime.
fn closure(p:&Program,plan:&crate::graph::cell_ownership::Plan,join:&Compiled,
    outgoing:&BTreeMap<usize,Vec<(Hop,usize)>>)->Option<(Vec<Shape>,Vec<(usize,Hop,usize)>)> {
    type State=(Shape,[usize;2],[Vec<usize>;2]);
    let initial:State=((*join.shape).clone(),[join.pattern.components[0].0,join.pattern.components[1].0],
        [ (0..join.pattern.components[0].1.len()).collect(),
          (join.frame_offsets[1]..join.shape.programs.len()).collect() ]);
    let mut states=vec![initial.clone()];let mut seen=HashMap::default();seen.insert(initial,0);
    let mut edges=Vec::new();let mut cursor=0;
    while cursor<states.len() {
        let (shape,parents,maps)=states[cursor].clone();
        for side in 0..2 {
            for (hop,next) in outgoing.get(&parents[side]).into_iter().flatten() {
                if shape.programs.len()>=32 {return None;}
                let lifted=Hop{source_frame:maps[side][hop.source_frame],..hop.clone()};
                let subst=super::super::substitutions(&plan.composition.sources,&plan.programs,&shape,&lifted)?;
                let program=plan.markers[p.rules[hop.rule].template].program_id;
                let target=shape.append(program,&plan.programs[program],&subst).0;
                let mut parents=parents;parents[side]=*next;
                let mut maps=maps.clone();maps[side].push(shape.programs.len());
                let state=(target,parents,maps);
                let target=if let Some(&id)=seen.get(&state) {id} else {
                    if states.len()>=128 {return None;}
                    let id=states.len();seen.insert(state.clone(),id);states.push(state);id
                };
                edges.push((cursor,lifted,target));
            }
        }
        cursor+=1;
    }
    Some((states.into_iter().map(|s|s.0).collect(),edges))
}
pub(in crate::graph::cell_ownership) fn install(p:&Program,plan:&mut crate::graph::cell_ownership::Plan)->Result<()> {
    let Some(raw)=p.artifact.get("ownership_dual_sources") else {return Ok(());};
    // Source identity was checked by the enclosing ownership Plan.
    if raw["schema"]!="dual-source-patterns/v1" {return Err("dual-source source/schema".into());}
    let patterns:Vec<Pattern>=serde_json::from_value(raw["patterns"].clone()).map_err(|e|e.to_string())?;
    if patterns.len()>4096 {return Err("dual-source budget".into());}
    let mut joins=Vec::new();
    for pattern in patterns {joins.push(compile(p,plan,pattern)?);}
    let seed_shapes=plan.composition.shapes.len();
    let mut outgoing=BTreeMap::<usize,Vec<(Hop,usize)>>::new();
    let mut transitions=plan.composition.transitions.iter().cloned().collect::<BTreeMap<_,_>>();
    for (key,target) in &plan.composition.transitions {outgoing.entry(key.shape).or_default().push((key.hop.clone(),*target));}
    let mut intern=plan.composition.shapes.iter().enumerate().map(|(id,s)|((**s).clone(),id)).collect::<HashMap<_,_>>();
    plan.composition.join_rules=vec![RuleRoutes::new();p.rules.len()];
    for mut join in joins {
        let Some((shapes,edges))=closure(p,plan,&join,&outgoing) else {plan.composition.join_rejected+=1;continue;};
        if plan.composition.shapes.len()-seed_shapes+shapes.len()>8192 {plan.composition.join_rejected+=1;continue;}
        let mut ids=Vec::with_capacity(shapes.len());
        for shape in shapes {
            let id=if let Some(&id)=intern.get(&shape) {id} else {
                let id=plan.composition.shapes.len();intern.insert(shape.clone(),id);
                Arc::make_mut(&mut plan.composition.shapes).push(Arc::new(shape));id
            };
            ids.push(id);
        }
        join.target=ids[0];join.shape=plan.composition.shapes[join.target].clone();
        for (from,hop,to) in edges {
            if transitions.insert(Key{shape:ids[from],hop},ids[to]).is_some_and(|old|old!=ids[to]) {
                return Err("conflicting inherited dual-source transition".into());
            }
        }
        let first=join.pattern.anchors.iter().find(|a|a.1==0).ok_or("missing first join anchor")?;
        let second=join.pattern.anchors.iter().find(|a|a.1==1).ok_or("missing second join anchor")?;
        let key=[(join.pattern.components[0].0,first.2,first.3,join.pattern.components[0].1[first.2]),
            (join.pattern.components[1].0,second.2,second.3,join.pattern.components[1].1[second.2])];
        let index=plan.composition.joins.len();
        plan.composition.active_rules[join.pattern.rule]=true;
        plan.composition.join_rules[join.pattern.rule].entry((first.0,second.0)).or_default().entry(key).or_default().push(index);
        plan.composition.joins.push(Arc::new(join));
    }
    if !plan.composition.joins.is_empty() {plan.composition.max_frames=32;}
    plan.composition.transitions=transitions.into_iter().collect();
    Ok(())
}
