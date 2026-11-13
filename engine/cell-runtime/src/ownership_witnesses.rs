//! Static routes select a constructor witness. A single successful immutable
//! query anchor can prove its key through shared wiring and source Copy operations.
//! Other routes retain exact-key checks. Every route retains runtime lifetime checks.
use super::*;
use std::collections::BTreeMap;
/// Ephemeral evidence for the immediately following constructor admission.
/// Compared keys must never survive a mutation, suspension or worker handoff.
#[derive(Clone,Copy)]
pub(crate) enum KeyEvidence { Unchecked, Compiled, Compared }
impl KeyEvidence {
    pub(crate) fn checked(self)->bool { !matches!(self,Self::Unchecked) }
    pub(crate) fn compiled(self)->bool { matches!(self,Self::Compiled) }
}
// Shape, source frame ordinal/code/operation.
type Key = (usize, usize, usize, u32);
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(super) struct Operation { entries: BTreeMap<usize, BTreeMap<Key, smallvec::SmallVec<[Target;1]>>> }
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
struct Target {frame:usize,code:usize,op:u32,key_proved:bool}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
enum Input {Port(usize),Scalar(usize,u32,usize)}
fn prove_key(query:&[Arg], source:&[Input], prefix:&[Op], args:&[Arg], target:&[Input])->bool {
    if query.len()!=source.len() || args.len()!=target.len() {return false;}
    // A successful immutable anchor establishes equality for every repeated
    // query variable. This temporary quotient exists only while compiling routes.
    fn root(mut input:Input, aliases:&[(Input,Input)])->Input {
        while let Some((_,next))=aliases.iter().find(|(from,_)|*from==input) {input=*next;}
        input
    }
    let mut aliases=Vec::new();
    let mut slots=BTreeMap::new();
    for (arg,&input) in query.iter().zip(source) {
        if let Arg::Slot(slot)=arg {
            if let Some(old)=slots.insert(*slot,input) {
                let old=root(old,&aliases);let new=root(input,&aliases);
                if old!=new {aliases.push((new,old));}
            }
        }
    }
    for op in prefix {
        match op {
            Op::Copy(dst,arg)=>{
                let value=match arg {Arg::Slot(slot)=>slots.get(slot).copied(),_=>None};
                if let Some(value)=value {slots.insert(*dst,value);} else {slots.remove(dst);}
            },
            Op::Let(dst,_,_)=>{slots.remove(dst);},
            _=>(),
        }
    }
    args.iter().zip(target).all(|(arg,input)|match arg {
        Arg::Slot(slot)=>slots.get(slot).is_some_and(|value|root(*value,&aliases)==root(*input,&aliases)),_=>false,
    })
}
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(super) struct Routes(pub Vec<Rule>, Vec<Group>);
#[derive(Clone,Debug,Default,PartialEq,Eq)]
pub(super) struct Rule {
    operations:Vec<smallvec::SmallVec<[usize;1]>>,
    entries:BTreeMap<usize,BTreeMap<Key,usize>>,
}
impl Rule {pub(super) fn is_empty(&self)->bool {self.entries.is_empty()}}
#[derive(Clone,Debug,Default,PartialEq,Eq)]
struct Group {operations:Box<[(usize,smallvec::SmallVec<[Target;1]>)]>}
/// Coordinator scratch for a pure lookup in the immutable compiled catalog.
/// The catalog key includes rule/Entry and source layout. Its optional instance
/// address is independently checked against current composition on every use.
/// It may cross Runs; equality, visibility and returned values are never cached.
#[derive(Clone,Copy)]
pub(super) struct Selection {
    rule:usize,entry:usize,key:Key,group:Option<usize>,
    // Only an address, never equality/liveness evidence. The current shape
    // and source ordinal validate it; no mutation-side invalidation is needed.
    address:Option<(FactRef,u32)>,
}
impl Selection {
    fn component<'a>(&self,runtime:&'a composition::Runtime,anchor:FactRef)->Option<(u32,&'a composition::Component)> {
        let (fact,id)=self.address?;
        if fact!=anchor {return None;}
        let component=runtime.components.get(id as usize)?.as_ref()?;
        // Logical source identities and operator codes are immutable. A suffix
        // changes shape; relocation changes the source position.
        (component.shape==self.key.0 && component.frames.get(self.key.1)==Some(&anchor.cell))
            .then_some((id,component))
    }
}
impl Routes {
    fn group(operations:Vec<Vec<Option<Operation>>>)->Self {
        let mut rules=Vec::with_capacity(operations.len());let mut groups=Vec::<Vec<(usize,smallvec::SmallVec<[Target;1]>)>>::new();
        for operations in operations {
            let mut rule=Rule{operations:vec![Default::default();operations.len()],..Default::default()};
            for (op,operation) in operations.into_iter().enumerate() {
                let Some(operation)=operation else {continue;};
                for (entry,candidates) in operation.entries {
                    rule.operations[op].push(entry);
                    let routes=rule.entries.entry(entry).or_default();
                    for (key,targets) in candidates {
                        let group=*routes.entry(key).or_insert_with(||{let n=groups.len();groups.push(Vec::new());n});
                        groups[group].push((op,targets));
                    }
                }
            }
            rules.push(rule);
        }
        Self(rules,groups.into_iter().map(|operations|Group{operations:operations.into_boxed_slice()}).collect())
    }
}

/// Stack scratch scoped to one worker chunk in a single borrowed Run view.
/// Adjacent Cell instances can share a compiled selection (including misses);
/// actual instance addresses, values and lifecycle evidence are never cached.
/// Callers create it at chunk entry, never in the persistent worker frame.
#[derive(Default)]
pub(crate) struct PreparedSelection(Option<Selection>);
#[derive(Default,serde::Serialize)]
pub(crate) struct PreparedWork {
    pub attempts:u64,
    pub anchor_reads:u64,
    pub probes:u64,
    pub operation_checks:u64,
    pub candidates:u64,
    pub lifecycle_checks:u64,
    pub selection_reuses:u64,
    pub hits:u64,
    pub proved_hits:u64,
}
impl PreparedWork {
    pub fn add(&mut self,other:&Self) {
        if other.attempts==0 {return;}
        macro_rules! add {($($f:ident),*)=>{$(self.$f+=other.$f;)*}}
        add!(attempts,anchor_reads,probes,operation_checks,candidates,lifecycle_checks,
            selection_reuses,hits,proved_hits);
    }
}
/// The existing catalog and composition directories, borrowed without the
/// coordinator's mutable Entry/cache. No instances, bindings or rows are copied.
pub(in crate::graph) struct Read<'a> {
    routes:&'a Routes,
    entries:&'a [Vec<usize>],
    frames:composition::FrameRead<'a>,
    components:&'a crate::read_epoch::Slots<Option<composition::Component>>,
}
impl Graph {
    pub(in crate::graph) fn prepared_witness_reader(&self)->Option<Read<'_>> {
        let owner=self.ownership.as_ref()?;
        let plan=&self.program.cell_ownership;
        if plan.witnesses.0.is_empty() {return None;}
        Some(Read{routes:&plan.witnesses,entries:&plan.entries,
            frames:owner.composition.frames.reader(&self.cells),components:&owner.composition.components})
    }
}
impl Read<'_> {
    pub fn find<T>(&self,rule:usize,operation:usize,known:&crate::cell::QueryFacts,
        selection:&mut PreparedSelection,work:&mut PreparedWork,
        mut accept:impl FnMut(FactRef,FactRef,bool,&mut PreparedWork)->Option<T>)->Option<T> {
        work.attempts+=1;
        let routes=self.routes.0.get(rule)?;
        let entries=routes.operations.get(operation)?;
        if entries.is_empty() {return None;}
        for &index in entries {
            let Some(Dependency::Fact(anchor))=known.receipt(self.entries[rule][index]) else {continue;};
            work.anchor_reads+=1;
            let Some(source)=self.frames.get(&anchor.cell) else {continue;};
            let Some(component)=self.components.get(source.component as usize).and_then(Option::as_ref) else {continue;};
            let key=(component.shape,source.ordinal,source.code,anchor.op);
            let group=if let Some(cached)=selection.0.filter(|s|s.rule==rule && s.entry==index && s.key==key) {
                work.selection_reuses+=1;cached.group
            } else {
                work.probes+=1;
                let group=routes.entries[&index].get(&key).copied();
                selection.0=Some(Selection{rule,entry:index,key,group,address:None});group
            };
            let Some(group)=group else {continue;};
            work.operation_checks+=1;
            let operations=&self.routes.1[group].operations;
            let Ok(position)=operations.binary_search_by_key(&operation,|p|p.0) else {continue;};
            for &Target{frame,code,op,key_proved} in &operations[position].1 {
                work.candidates+=1;
                let Some(&cell)=component.frames.get(frame) else {continue;};
                if !self.frames.get(&cell).is_some_and(|f|f.code==code && f.component==source.component) {continue;}
                if let Some(result)=accept(anchor,FactRef{cell,op},key_proved,work) {
                    work.hits+=1;return Some(result);
                }
            }
        }
        None
    }
}
#[derive(serde::Deserialize)]
struct Recipe {
    rule: usize,
    shape: usize,
    frame_codes: Vec<usize>,
    query_sites: Vec<(usize, usize, u32)>,
    rhs_sites: Vec<(usize, usize, u32)>,
}
impl Routes {
    pub(super) fn compile(p: &Program, plan: &Plan) -> Result<Self> {
        let Some(raw) = p.artifact.get("ownership_witnesses") else { return Ok(Self::default()); };
        // Source identity was checked by the enclosing ownership Plan.
        let recipes: Vec<Recipe> = serde_json::from_value(raw["recipes"].clone()).map_err(|e|e.to_string())?;
        if recipes.len() > 4096 { return Err("constructor witness catalog too large".into()); }
        let mut routes: Vec<Vec<Option<Operation>>> = vec![Vec::new(); p.rules.len()];
        for recipe in recipes {
            let rule = p.rules.get(recipe.rule).ok_or("witness rule")?;
            let shape = plan.composition.shapes.get(recipe.shape).ok_or("witness shape")?;
            if recipe.frame_codes.len() != shape.programs.len() { return Err("witness frame codes".into()); }
            for (&code, &program) in recipe.frame_codes.iter().zip(&shape.programs) {
                if plan.code_programs.get(code) != plan.programs.get(program) {
                    return Err("witness code wiring mismatch".into());
                }
            }
            let operator = |frame: usize, op: u32| -> Result<usize> {
                let code = *recipe.frame_codes.get(frame).ok_or("witness frame")?;
                plan.code_operators[code].get(op as usize).copied().ok_or_else(|| "witness operation".into())
            };
            for &(atom, source, source_op) in &recipe.query_sites {
                let query = rule.query.get(atom).ok_or("witness query atom")?;
                let Call::Table(table) = query.call else { return Err("witness query must be a table".into()); };
                if operator(source, source_op)? != table { return Err("witness query operator mismatch".into()); }
            }
            for &(operation, target, target_op) in &recipe.rhs_sites {
                let Some(Op::Let(_, Call::Table(table), _)) = p.templates[rule.template].ops.get(operation) else {
                    return Err("witness RHS must be a constructor".into());
                };
                if !p.tables[*table].constructor || !p.tables[*table].virtual_fact
                    || operator(target, target_op)? != *table { return Err("witness RHS operator mismatch".into()); }
                // One statically selected local anchor, no runtime candidate scan.
                if let Some((entry, source, source_op)) = recipe.query_sites.iter().find_map(|&(atom, frame, op)|
                    plan.entries[recipe.rule].iter().position(|&a|a==atom).map(|entry|(entry,frame,op))) {
                    let rule_routes = &mut routes[recipe.rule];
                    rule_routes.resize_with(p.templates[rule.template].ops.len(), || None);
                    let atom=plan.entries[recipe.rule][entry];
                    let source_table=operator(source,source_op)?;
                    let inputs=|frame:usize,op:u32| {
                        plan.programs[shape.programs[frame]].fields[op as usize].iter().enumerate()
                            .map(|(column,s)|match s {
                                Some(local)=>Input::Port(shape.ports[frame][*local]),
                                None=>Input::Scalar(frame,op,column),
                            }).collect::<Vec<_>>()
                    };
                    let source_fields=inputs(source,source_op);
                    let target_fields=inputs(target,target_op);
                    let Op::Let(_,_,args)=&p.templates[rule.template].ops[operation] else {unreachable!()};
                    let key_proved=p.tables[source_table].constructor && p.tables[source_table].virtual_fact
                        && !target_fields.is_empty()
                        && prove_key(&rule.query[atom].args,&source_fields,&p.templates[rule.template].ops[..operation],
                            args,&target_fields[..target_fields.len()-1]);
                    let targets=rule_routes[operation].get_or_insert_with(Operation::default).entries
                        .entry(entry).or_default().entry((recipe.shape,source,recipe.frame_codes[source],source_op))
                        .or_default();
                    let target=Target{frame:target,code:recipe.frame_codes[target],op:target_op,key_proved};
                    if !targets.contains(&target) {targets.push(target);}
                }
            }
        }
        Ok(Self::group(routes))
    }
}
impl Graph {
    pub(crate) fn cell_constructor_witness(&mut self, cell: u32, operation: usize) -> Option<(FactRef,KeyEvidence)> {
        let rhs_cell=cell;
        if self.program.cell_ownership.witnesses.0.is_empty() { return None; }
        let owner = self.ownership.as_ref()?;
        let entry = owner.composition.entry.as_ref()?;
        if self.rhs_frame(cell)?.template != entry.template { return None; }
        let plans=&self.program.cell_ownership.witnesses;
        let routes = plans.0.get(entry.rule)?;
        for &index in routes.operations.get(operation)? {
            let Some(Some(Dependency::Fact(anchor))) = entry.anchors.get(index) else { continue; };
            self.stats.constructor_cell_route_address_checks+=1;
            let previous=owner.composition.witness_selection.get()
                .filter(|s|s.rule==entry.rule && s.entry==index);
            let direct=previous.and_then(|cached| {
                let (id,component)=cached.component(&owner.composition,*anchor)?;
                Some((id,component,cached.group))
            });
            let (component_id,component,group)=if let Some(selected)=direct {
                self.stats.constructor_cell_route_address_reuses+=1;
                self.stats.constructor_cell_route_selection_reuses+=1;
                selected
            } else {
                let Some(source)=owner.composition.frames.get(&self.cells, &anchor.cell) else {continue;};
                let Some(component)=owner.composition.components.get(source.component as usize).and_then(Option::as_ref) else {continue;};
                self.stats.constructor_cell_route_anchor_reads+=1;
                let key=(component.shape,source.ordinal,source.code,anchor.op);
                let group=if let Some(cached)=previous.filter(|s|s.key==key) {
                    self.stats.constructor_cell_route_selection_reuses+=1;
                    cached.group
                } else {
                    self.stats.constructor_cell_route_probes+=1;
                    routes.entries[&index].get(&key).copied()
                };
                owner.composition.witness_selection.set(Some(Selection{rule:entry.rule,entry:index,key,group,
                    address:Some((*anchor,source.component))}));
                (source.component,component,group)
            };
            let Some(group)=group else {continue;};
            self.stats.constructor_cell_route_operation_checks+=1;
            let operations=&plans.1[group].operations;
            let Ok(position)=operations.binary_search_by_key(&operation,|p|p.0) else {continue;};
            let targets=&operations[position].1;
            for &Target{frame:target,code,op,key_proved} in targets {
            let Some(&cell) = component.frames.get(target) else { continue; };
            if !owner.composition.frames.get(&self.cells, &cell).is_some_and(|f|f.code==code && f.component==component_id) { continue; }
            if key_proved {self.stats.constructor_cell_route_source_checks+=1;}
            let key_proved=key_proved && self.cells.fact_state(*anchor).is_some_and(|s|s.owned && !s.hidden);
            if targets.len()>1 && key_proved {
                // Shared wiring already proves all inputs. Only check candidate
                // existence here; final admission still checks dirty/forwarding.
                if !self.cells.fact_state(FactRef{cell,op}).is_some_and(|s|s.owned && !s.hidden) {continue;}
                self.stats.constructor_cell_route_static_candidate_checks_avoided+=1;
            } else if targets.len()>1 {
                self.stats.constructor_cell_route_alternative_checks+=1;
                let fact=FactRef{cell,op};
                let Ok(Some(row))=self.fact(fact) else {continue;};
                if row.hidden {continue;}
                let Op::Let(_,Call::Table(table),args)=&self.program.templates[entry.template].ops[operation] else {continue;};
                if row.table!=*table || row.values.len()!=args.len()+1 {continue;}
                let mut equal=true;
                for (field,arg) in row.values.iter().zip(args) {
                    self.stats.constructor_cell_route_alternative_fields+=1;
                    if self.argument(rhs_cell,arg).ok().as_ref()!=Some(field) {equal=false;break;}
                }
                if !equal {continue;}
            }
            self.stats.constructor_cell_route_witnesses += 1;
            let evidence=if key_proved {KeyEvidence::Compiled}
                else if targets.len()>1 {KeyEvidence::Compared} else {KeyEvidence::Unchecked};
            return Some((FactRef { cell, op },evidence));
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn selected_address_rechecks_shape_source_position_and_retirement() {
        let mut runtime=composition::Runtime::new(&composition::Plan::default());
        runtime.components.push(Some(composition::Component{shape:4,frames:smallvec::smallvec![9],signals:vec![]}));
        let anchor=FactRef{cell:9,op:3};
        let selected=Selection{rule:0,entry:0,key:(4,0,2,3),group:Some(0),address:Some((anchor,0))};
        assert!(selected.component(&runtime,anchor).is_some());
        assert!(selected.component(&runtime,FactRef{cell:9,op:4}).is_none());
        runtime.components.local_mut(0).as_mut().unwrap().shape=5;
        assert!(selected.component(&runtime,anchor).is_none(),"new suffix needs a fresh catalog selection");
        runtime.components.local_mut(0).as_mut().unwrap().shape=4;
        runtime.components.local_mut(0).as_mut().unwrap().frames[0]=10;
        assert!(selected.component(&runtime,anchor).is_none(),"same-shaped source cannot reuse another instance address");
        runtime.components.retire(0);
        assert!(selected.component(&runtime,anchor).is_none());
    }
    #[test]
    fn repeated_anchor_variables_prove_transitive_port_equality() {
        let query=[Arg::Slot(0),Arg::Slot(1),Arg::Slot(0),Arg::Slot(1)];
        let source=[Input::Port(7),Input::Port(9),Input::Port(9),Input::Port(11)];
        assert!(prove_key(&query,&source,&[],&[Arg::Slot(0)],&[Input::Port(11)]));
        assert!(prove_key(&query,&source,&[Op::Copy(2,Arg::Slot(0))],&[Arg::Slot(2)],&[Input::Port(7)]));
        assert!(!prove_key(&query,&source,&[],&[Arg::Slot(0)],&[Input::Port(13)]));
        assert!(!prove_key(&query,&source,&[Op::Let(0,Call::Table(0),vec![])],&[Arg::Slot(0)],&[Input::Port(11)]));
        assert!(!prove_key(&[Arg::Slot(0),Arg::Slot(1)],&[Input::Port(7),Input::Port(9)],
            &[],&[Arg::Slot(0)],&[Input::Port(9)]));
    }
    #[test]
    fn constructor_key_proof_follows_copies_but_not_overwritten_bindings() {
        assert_eq!(std::mem::size_of::<Target>(),std::mem::size_of::<(usize,usize,u32)>());
        let source=[Input::Port(7),Input::Scalar(0,2,1)];
        let query=[Arg::Slot(0),Arg::Slot(1)];
        let args=[Arg::Slot(3),Arg::Slot(1)];
        assert!(prove_key(&query,&source,&[Op::Copy(3,Arg::Slot(0))],&args,&source));
        assert!(!prove_key(&query,&source,&[Op::Let(0,Call::Table(0),vec![]),Op::Copy(3,Arg::Slot(0))],&args,&source));
        assert!(!prove_key(&query,&source,&[Op::Copy(3,Arg::Slot(0))],&args,
            &[Input::Port(7),Input::Scalar(1,2,1)]));
        assert!(!prove_key(&query,&source,&[],&[Arg::Literal(Value::Int(7)),Arg::Slot(1)],&source));
    }
}
