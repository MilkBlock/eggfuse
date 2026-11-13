//! Static routes select a constructor witness. A single successful immutable
//! query anchor can prove its key through shared wiring and source Copy operations.
//! Other routes retain exact-key checks. Every route retains runtime lifetime checks.
use super::*;
use std::collections::BTreeMap;
// Shape, source frame ordinal/code/operation.
type Key = (usize, usize, usize, u32);
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(super) struct Operation { entries: BTreeMap<usize, BTreeMap<Key, Target>> }
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
pub(super) struct Routes(pub Vec<Vec<Option<Operation>>>);
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
                    rule_routes[operation].get_or_insert_with(Operation::default).entries
                        .entry(entry).or_default().entry((recipe.shape,source,recipe.frame_codes[source],source_op))
                        .or_insert(Target{frame:target,code:recipe.frame_codes[target],op:target_op,key_proved});
                }
            }
        }
        Ok(Self(routes))
    }
}
impl Graph {
    pub(crate) fn cell_constructor_witness(&mut self, cell: u32, operation: usize) -> Option<(FactRef,bool)> {
        if self.program.cell_ownership.witnesses.0.is_empty() { return None; }
        let owner = self.ownership.as_ref()?;
        let entry = owner.composition.entry.as_ref()?;
        if self.rhs_frame(cell)?.template != entry.template { return None; }
        let routes = self.program.cell_ownership.witnesses.0.get(entry.rule)?.get(operation)?.as_ref()?;
        for (&index, candidates) in &routes.entries {
            let Some(Some(Dependency::Fact(anchor))) = entry.anchors.get(index) else { continue; };
            let Some(source) = owner.composition.frames.get(&anchor.cell) else { continue; };
            let Some(component) = owner.composition.components.get(source.component as usize).and_then(Option::as_ref) else { continue; };
            self.stats.constructor_cell_route_probes += 1;
            let Some(&Target{frame:target,code,op,key_proved}) = candidates.get(&(component.shape,source.ordinal,source.code,anchor.op)) else { continue; };
            let Some(&cell) = component.frames.get(target) else { continue; };
            if !owner.composition.frames.get(&cell).is_some_and(|f|f.code==code && f.component==source.component) { continue; }
            self.stats.constructor_cell_route_witnesses += 1;
            if key_proved {self.stats.constructor_cell_route_source_checks+=1;}
            let key_proved=key_proved && self.cells.fact_state(*anchor).is_some_and(|s|s.owned && !s.hidden);
            return Some((FactRef { cell, op },key_proved));
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
