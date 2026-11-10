//! Executable specialization of the ordinary Cell definition. Query/effect
//! instructions remain in the source rule; this plan substitutes actual result
//! ports only after its entry assumptions have been matched.
use super::{Site, SlotLayout};
use serde_json::{Value as Json, json};
use std::{collections::BTreeMap, rc::Rc};

/// Lowered proof for an already completed constructor-only RHS. Its sources
/// are positions in one actual retained frame; no producer address is invented.
#[derive(Clone,Debug)]
pub(crate) struct CompletedPlan {
    pub rule: usize,
    pub back: usize,
    pub layout: Rc<SlotLayout>,
    pub outputs: Vec<(Site,usize,usize)>,
    pub required_sources: u64,
    pub projections: Vec<(Rc<SlotLayout>,Rc<SlotLayout>)>,
}
impl CompletedPlan {
    pub(crate) fn artifact(&self) -> Json {
        json!({"rule":self.rule,"back":self.back,"outputs":self.outputs,
            "sources":self.layout.sources.iter().map(|p|p.map(|p|(p.rule(),p.slot()))).collect::<Vec<_>>(),
            "composed_projections":self.projections.iter().map(|(a,b)|json!({
                "previous_rule":a.rule,"previous":a.sources.iter().map(|p|p.map(|p|(p.rule(),p.slot()))).collect::<Vec<_>>(),
                "sources":b.sources.iter().map(|p|p.map(|p|(p.rule(),p.slot()))).collect::<Vec<_>>()
            })).collect::<Vec<_>>(),
            "remaining_effects":0,"publication":"original-run-after-completion"})
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
}

