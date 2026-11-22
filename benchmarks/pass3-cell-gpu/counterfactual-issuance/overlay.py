from pathlib import Path
from runpy import run_path

edit=run_path(str(Path(__file__).resolve().parent.parent/'ripsat-set-receipt/overlay.py'))['edit']


def install(crate):
    actor=crate/'src/issuance_actor.rs'
    edit(actor,'    weights: [f32; 3],','    weights: [f32; 3],\n    force: Option<(u64,bool)>,')
    edit(actor,'let take = u < 1. / (1. + (-logit).exp());','''let sampled = u < 1. / (1. + (-logit).exp());
                let take = match self.config.force {
                    Some((id,target)) if id==serial=>target,
                    _=>sampled
                };''')
    edit(actor,'    force: Option<(u64,bool)>,','''    force: Option<(u64,bool)>,
    #[serde(default)]
    signed_pair: Option<[u64;2]>,''')
    edit(actor,'"sample" | "greedy" | "leaf" | "full"', '"sample" | "greedy" | "leaf" | "full" | "pair" | "first_context"')
    edit(actor,'            "leaf" => false,','''            "first_context" => {
                let take = self.tokens == [0, 0] && logit >= 0.;
                self.decisions.push((serial, x, take));
                take
            }
            "pair" => {
                let take=self.config.signed_pair.is_some_and(|ids|ids.contains(&serial));
                self.decisions.push((serial,x,take));
                take
            }
            "leaf" => false,''')
    edit(actor,'    tokens: [u64; 2],','    tokens: [u64; 2],\n    pages: Vec<[u64;6]>,')
    edit(actor,'            tokens: [0; 2],','            tokens: [0; 2],pages:Vec::new(),')
    with actor.open('a') as f:
        f.write('''
pub(crate) fn record_pair_address(code:usize, first:u64, run:u64, rid:usize, serial:u64, addr:u64, epoch:u64) {
    if code & (1usize<<63) == 0 { return; }
    S.with_borrow_mut(|s| {
        if let Some(actor)=s.as_mut().and_then(|s|s.actor.as_mut())
            && actor.config.mode=="pair" {
            actor.pages.push([first,run,rid as u64,serial,addr,epoch]);
        }
    });
}
''')
    edit(crate/'src/adaptive_root_page.rs','            let action=crate::strict_named::leaf_bit',
         '            crate::strict_named::record_pair_address(template,first,run,rid,state.serial,addr,version);\n            let action=crate::strict_named::leaf_bit')
    edit(crate/'src/strict_named.rs','"decisions":a.decisions,"tokens":a.tokens','"decisions":a.decisions,"tokens":a.tokens,"pair_pages":a.pages')
    strict=crate/'src/strict_named.rs'
    edit(strict,'struct State {withhold_root:', 'struct State {reuse_returns:bool,withhold_root:')
    edit(strict,'    s.withhold_root=','    s.reuse_returns=spec["reuse_returns"]==true;\n    s.withhold_root=')
    edit(strict,'struct Owner {block:', 'struct Owner {returned:Option<FactRef>,block:')
    edit(crate/'src/ripsat_set_publication.rs','let o = Owner {block:', 'let o = Owner {returned:None,block:')
    edit(strict,'pub(crate) fn output(f: FactRef, t: usize, epoch: u64) {','''
pub(crate) fn output(f: FactRef, t: usize, epoch: u64) {
    register_result(f.cell, f.op as usize, f, t, epoch, false);
}
pub(crate) fn returned(cell:u32, op:usize, dep:Dependency, table:usize, version:u64) {
    if let Dependency::Fact(fact)=dep {
        register_result(cell,op,fact,table,version,true);
    }
}
fn register_result(cell:u32, op:usize, f:FactRef, t:usize, epoch:u64, reused:bool) {''')
    edit(strict,'        if s.terminal_block {','''        if reused && !s.reuse_returns { return; }
        if !reused && s.terminal_block {''')
    edit(strict,'s.physical != Some(f.cell)','s.physical != Some(cell)')
    edit(strict,'&(a.rule, f.op as usize, t)','&(a.rule, op, t)')
    edit(strict,'            path.push([a.rule, f.op as usize, rid]);','''            path.push([a.rule, op, rid]);
            if reused && (!a.block || a.prior.len()!=0 ||
                !s.set_plan.as_ref().is_some_and(|p|path.as_slice()==[p.first]) ||
                s.ports.get(&rid).is_some_and(|ports|ports.contains_key(&Dependency::Fact(f)))) {
                continue;
            }''')
    edit(strict,'            let owner = Owner {','            let owner = Owner {returned:reused.then_some(f),')
    edit(strict,'            if expected[1] != physical.op as usize',
         '            if !o.returned.map_or(expected[1]==physical.op as usize, |actual| actual==physical)')
    edit(crate/'src/graph.rs','            self.stats.constructor_reused += 1;','''            self.stats.constructor_reused += 1;
            if !row.hidden {
                crate::strict_named::returned(cell,op,row.witness,t,row.epoch);
            }''')
    edit(strict,'struct State {reuse_returns:', 'struct State {reuse_log:Vec<[u64;9]>,reuse_returns:')
    edit(strict,'            let owner = Owner {returned:','''            if reused && s.record_links {
                s.reuse_log.push([a.root,a.rule as u64,op as u64,rid as u64,cell as u64,
                                  f.cell as u64,f.op as u64,epoch,a.run as u64]);
            }
            let owner = Owner {returned:''')
    edit(strict,'json!({"issuance_actor":','json!({"actual_reused_returns":s.reuse_log,"issuance_actor":')
    # A producer can license an i64-literal consumer. Recheck the literal on
    # the named physical row at release, including for a complete receipt bank.
    edit(strict,'.all(|v| matches!(v,Arg::Slot(s) if slots.insert(*s)))',
         '''.all(|v| match v {
                        Arg::Slot(s) => slots.insert(*s),
                        Arg::Literal(crate::value::Value::Int(_)) =>
                            spec["literal_consumers"] == true,
                        _ => false,
                    })''')
    edit(strict,'            let mut input = Slots::default();', '''            if atom.args.iter().zip(row.values.iter()).any(|(arg,value)|
                matches!(arg, Arg::Literal(expected) if expected != value)) {
                continue;
            }
            let mut input = Slots::default();''')
    edit(strict,'struct State {reuse_log:', 'struct State {first_edges:Option<BTreeSet<E>>,reuse_log:')
    edit(strict,'    s.reuse_returns=','''    s.first_edges=spec.get("first_edges").map(|x|
        serde_json::from_value(x.clone()).map_err(|e|e.to_string())).transpose()?;
    if s.first_edges.as_ref().is_some_and(|edges| edges.iter().any(|e|
        s.library.as_ref().is_none_or(|lib|!lib.contains(&vec![*e])))){
        return Err("action selected an unsigned edge".into());
    }
    s.reuse_returns=''')
    edit(strict,'            if reused && (!a.block', '''            if a.prior.is_empty() && s.first_edges.as_ref().is_some_and(|edges|!edges.contains(&path[0])){
                continue;
            }
            if reused && (!a.block''')
