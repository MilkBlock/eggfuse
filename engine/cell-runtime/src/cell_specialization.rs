//! Executable specialization of the ordinary Cell definition. Query/effect
//! instructions remain in the source rule; this plan substitutes actual result
//! ports only after its entry assumptions have been matched.
use super::{Site, SlotLayout};
use crate::program::{Arg, Op, Program};
use serde::Serialize;
use serde_json::{Value as Json, json};
use std::{collections::BTreeMap, rc::Rc};

/// An opaque equality operand. Constructor identity stays in the checked entry
/// and result proofs, never in this shared union program. Aliasing is preserved
/// by using the same input/result port, including across several union effects.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
pub(crate) enum UnionPort {
    Input(usize),
    Result(usize),
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
pub(crate) enum UnionEffect {
    Source([UnionPort; 2]),
    Constructor([UnionPort; 2]),
}
pub(crate) type LazyUnions = Rc<[UnionEffect]>;

/// Compile only operand wiring; the ordinary ordered union queue still owns
/// submission and the source Run owns visibility. No runtime binding is copied.
pub(crate) fn compile_unions(p: &Program, rule: usize, exports: &[Site],
    equal_output: impl Fn(usize) -> bool) -> Option<Option<LazyUnions>> {
    let cell = super::Definition::new(p, rule).ok()?;
    let mut program = vec![];
    for (position, op) in cell.template.ops.iter().enumerate() {
        let port = |arg: &Arg| {
            let Arg::Slot(slot) = cell.value(arg) else { return None };
            let sort = cell.template.sorts.get(slot)?;
            if sort["kind"] != "eq" { return None; }
            let source = if cell.rule.inputs.contains(&slot) {
                UnionPort::Input(slot)
            } else {
                let op = cell.template.ops[..position].iter().position(|op|
                    matches!(op, Op::Let(dst, ..) if *dst == slot))?;
                UnionPort::Result(exports.binary_search(&Site::Effect(op)).ok()?)
            };
            Some((source, sort))
        };
        match op {
            Op::Union(a,b) => {
                let (a, ta)=port(a)?; let (b,tb)=port(b)?;
                if ta!=tb {return None;}
                program.push(UnionEffect::Source([a,b]));
            },
            Op::Set(table,_,value) if !equal_output(position) => {
                let (value,sort)=port(value)?;
                if p.tables[*table].schema.last()? != sort {return None;}
                let result=UnionPort::Result(exports.binary_search(&Site::Effect(position)).ok()?);
                program.push(UnionEffect::Constructor([result,value]));
            },
            _ => (),
        }
    }
    Some((!program.is_empty()).then(|| program.into()))
}

/// Lowered proof for an already completed constructor RHS plus optional queued
/// equality effects. Its sources
/// are positions in one actual retained frame; no producer address is invented.
#[derive(Clone,Debug)]
pub(crate) struct CompletedPlan {
    pub rule: usize,
    pub back: usize,
    pub layout: Rc<SlotLayout>,
    pub outputs: Vec<(Site,usize,usize)>,
    pub required_sources: u64,
    pub projections: Vec<(Rc<SlotLayout>,Rc<SlotLayout>)>,
    pub unions: Option<LazyUnions>,
}
impl CompletedPlan {
    pub(crate) fn artifact(&self) -> Json {
        let mut result = json!({"rule":self.rule,"back":self.back,"outputs":self.outputs,
            "sources":self.layout.sources.iter().map(|p|p.map(|p|(p.rule(),p.slot()))).collect::<Vec<_>>(),
            "composed_projections":self.projections.iter().map(|(a,b)|json!({
                "previous_rule":a.rule,"previous":a.sources.iter().map(|p|p.map(|p|(p.rule(),p.slot()))).collect::<Vec<_>>(),
                "sources":b.sources.iter().map(|p|p.map(|p|(p.rule(),p.slot()))).collect::<Vec<_>>()
            })).collect::<Vec<_>>(),
            "remaining_effects":self.unions.as_ref().map_or(0, |p| p.len()),"publication":"original-run-after-completion"});
        if let Some(unions) = &self.unions {
            result["lazy_unions"] = json!({"schema":"cell-union-ports/v1", "program":unions,
                "submission":"original-source-order", "commit":"original-run-boundary"});
        }
        result
    }
}

/// Close finite layout transitions during Bake. A runtime projection only
/// selects one of these static maps; it never builds or composes a map itself.
/// The cap limits optional coverage, never the ordinary execution fallback.
pub(crate) fn compile_projections(plans:&mut [Option<Rc<CompletedPlan>>],
    existing:impl Iterator<Item=Rc<SlotLayout>>) {
    let mut pool=BTreeMap::new();
    for layout in existing.chain(plans.iter().flatten().map(|p|p.layout.clone())) {
        pool.entry((layout.rule,layout.sources.clone())).or_insert(layout);
    }
    loop {
        let mut additions=BTreeMap::new();
        for plan in plans.iter().flatten() {
            for previous in pool.values().filter(|l|l.rule==plan.layout.source_rule) {
                let sources=plan.layout.sources.iter().map(|s|previous.sources.get(s.unwrap().slot()).copied().flatten()).collect::<Vec<_>>();
                if sources.iter().any(Option::is_none) {continue;}
                let key=(plan.rule,sources.clone());
                if !pool.contains_key(&key) && !additions.contains_key(&key)
                    && pool.len()+additions.len()<256 {
                    if let Some(layout)=SlotLayout::compile(plan.rule,sources) {additions.insert(key,layout);}
                }
            }
        }
        if additions.is_empty() {break;}
        pool.extend(additions);
    }
    for plan in plans.iter_mut().flatten() {
        let plan=Rc::make_mut(plan);
        for previous in pool.values().filter(|l|l.rule==plan.layout.source_rule) {
            let sources=plan.layout.sources.iter().map(|s|previous.sources.get(s.unwrap().slot()).copied().flatten()).collect::<Vec<_>>();
            if sources.iter().any(Option::is_none) {continue;}
            if let Some(composed)=pool.get(&(plan.rule,sources)) {
                plan.projections.push((previous.clone(),composed.clone()));
            }
        }
    }
    // Entries share identical executable specializations, not a second graph.
    let mut shared = BTreeMap::new();
    let mut unions = BTreeMap::<Vec<UnionEffect>, LazyUnions>::new();
    for plan in plans.iter_mut().flatten() {
        if let Some(program) = &Rc::make_mut(plan).unions {
            let program = unions.entry(program.to_vec()).or_insert_with(|| program.clone()).clone();
            Rc::make_mut(plan).unions = Some(program);
        }
        let key = serde_json::to_string(&plan.artifact()).unwrap();
        *plan = shared.entry(key).or_insert_with(|| plan.clone()).clone();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cell::ResultPort;

    #[test]
    fn union_code_shares_across_constructor_contexts_but_preserves_aliases_and_order() {
        let make = |rule, table, pairs:Vec<[UnionPort;2]>| {
            Some(Rc::new(CompletedPlan { rule, back:1,
                layout:SlotLayout::compile(rule,vec![Some(ResultPort::new(0,0))]).unwrap(),
                outputs:vec![(Site::Effect(0),table,0)], required_sources:1,
                projections:vec![], unions:Some(pairs.into_iter().map(UnionEffect::Source).collect::<Vec<_>>().into()) }))
        };
        use UnionPort::{Input,Result};
        let mut plans=[
            make(1,10,vec![[Input(0),Result(0)],[Input(1),Result(0)]]),
            make(2,20,vec![[Input(0),Result(0)],[Input(1),Result(0)]]),
            make(3,10,vec![[Input(0),Result(0)],[Input(0),Result(0)]]),
            make(4,10,vec![[Input(1),Result(0)],[Input(0),Result(0)]]),
        ];
        compile_projections(&mut plans,std::iter::empty());
        let programs=plans.iter().map(|p|p.as_ref().unwrap().unions.as_ref().unwrap()).collect::<Vec<_>>();
        assert!(Rc::ptr_eq(programs[0],programs[1]));
        assert!(!Rc::ptr_eq(programs[0],programs[2]));
        assert!(!Rc::ptr_eq(programs[0],programs[3]));
        assert_ne!(plans[0].as_ref().unwrap().artifact(),plans[1].as_ref().unwrap().artifact(),
            "shared union code does not identify different constructor contracts");
    }
}
