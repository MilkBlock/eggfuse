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
    let mut slots=BTreeMap::new();
    for (arg,&input) in query.iter().zip(source) {
        if let Arg::Slot(slot)=arg {
            if slots.insert(*slot,input).is_some_and(|old|old!=input) {return false;}
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
        Arg::Slot(slot)=>slots.get(slot)==Some(input),_=>false,
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
struct Group {operations:Vec<(usize,smallvec::SmallVec<[Target;1]>)>}
/// Coordinator scratch for a pure lookup in the immutable compiled catalog.
/// The full key includes rule/Entry and source layout, not an instance address.
/// It may cross Runs: every use resolves current facts and rechecks admission.
/// Never place equality, visibility or returned-value evidence here.
#[derive(Clone,Copy)]
pub(super) struct Selection {rule:usize,entry:usize,key:Key,group:Option<usize>}
impl Routes {
    fn group(operations:Vec<Vec<Option<Operation>>>)->Self {
        let mut rules=Vec::with_capacity(operations.len());let mut groups=Vec::<Group>::new();
        for operations in operations {
            let mut rule=Rule{operations:vec![Default::default();operations.len()],..Default::default()};
            for (op,operation) in operations.into_iter().enumerate() {
                let Some(operation)=operation else {continue;};
                for (entry,candidates) in operation.entries {
                    rule.operations[op].push(entry);
                    let routes=rule.entries.entry(entry).or_default();
                    for (key,targets) in candidates {
                        let group=*routes.entry(key).or_insert_with(||{let n=groups.len();groups.push(Group::default());n});
                        groups[group].operations.push((op,targets));
                    }
                }
            }
            rules.push(rule);
        }
        Self(rules,groups)
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
    pub fn compile(p: &Program, plan: &Plan) -> Result<Self> {
        let Some(raw) = p.artifact.get("ownership_witnesses") else { return Ok(Self::default()); };
        if raw["source"] != composition::source_digest(&p.artifact) {
            return Err("constructor witness source mismatch".into());
        }
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
            let Some(source) = owner.composition.frames.get(&anchor.cell) else { continue; };
            let Some(component) = owner.composition.components.get(source.component as usize).and_then(Option::as_ref) else { continue; };
            self.stats.constructor_cell_route_anchor_reads += 1;
            let key=(component.shape,source.ordinal,source.code,anchor.op);
            let group=if let Some(cached)=owner.composition.witness_selection.get()
                .filter(|s|s.rule==entry.rule && s.entry==index && s.key==key) {
                self.stats.constructor_cell_route_selection_reuses+=1;
                cached.group
            } else {
                self.stats.constructor_cell_route_probes+=1;
                let group=routes.entries[&index].get(&key).copied();
                owner.composition.witness_selection.set(Some(Selection{rule:entry.rule,entry:index,key,group}));
                group
            };
            let Some(group)=group else {continue;};
            self.stats.constructor_cell_route_operation_checks+=1;
            let operations=&plans.1[group].operations;
            let Ok(position)=operations.binary_search_by_key(&operation,|p|p.0) else {continue;};
            let targets=&operations[position].1;
            for &Target{frame:target,code,op,key_proved} in targets {
            let Some(&cell) = component.frames.get(target) else { continue; };
            if !owner.composition.frames.get(&cell).is_some_and(|f|f.code==code && f.component==source.component) { continue; }
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
