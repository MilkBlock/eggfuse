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
    from shutil import copyfile
    copyfile(Path(__file__).with_name("live_reader.rs"), crate/"src/live_reader.rs")
    with strict.open("a") as f:
        f.write('\ninclude!("live_reader.rs");\n')
    edit(strict,"struct State {first_edges:", "struct State {reader:Option<RouteReader>,route:Option<usize>,first_edges:")
    edit(strict,"    s.first_edges=spec", '    s.reader=RouteReader::load(&spec["route_reader"],g,&s)?;\n    s.first_edges=spec')
    edit(strict,"        s.active = None;\n        s.terminal_block=false;",'''        let route = code >> 32;
        let code = code & 0xffff_ffff;
        s.route = if route==0 {None} else if (4..8).contains(&route) &&
            s.reader.as_ref().is_some_and(|m|m.edges[0][0]==rid) {Some(route-4)}
            else {return Err("invalid per-root route selection".into())};
        s.active = None;
        s.terminal_block=false;''')
    edit(strict,"            if a.prior.is_empty() && s.first_edges",'''            if a.prior.is_empty() && let Some(mask)=s.route
                && let Some(i)=s.reader.as_ref().and_then(|m|m.edges.iter().position(|e|e==&path[0]))
                && mask & (1<<i)==0 { continue; }
            if a.prior.is_empty() && s.first_edges''')
    edit(strict,'json!({"actual_reused_returns"', 'json!({"route_fallback":s.reader.as_ref().map(|m|m.fallback),"route_observations":s.reader.as_ref().filter(|m|m.training_fork).map(|m|&m.observations),"route_choices":s.reader.as_ref().map(|m|(m.decisions,m.runs.len())),"actual_reused_returns"')
    page=crate/"src/adaptive_root_page.rs"
    edit(page,"pub(crate) fn single_page(\n","pub(crate) fn single_page(\n    graph:&crate::graph::Graph,\n")
    for filename in ("strict_partial.rs","adaptive_rows.rs"):
        edit(crate/"src"/filename,"single_page(g.epoch","single_page(g,g.epoch")
    edit(page,"        for &(dep, version) in inputs {","        let context=crate::strict_named::route_page(graph,rid);\n        for &(dep, version) in inputs {")
    edit(page,"            words.extend([tag|action, addr, v]);",'''            let route=context.as_ref().map_or(0,|rows|crate::strict_named::route_bits(graph,rows,dep,state.serial));
            words.extend([tag|action|route, addr, v]);''')
    # Bits 56..58 carry the learned route; the original strict code is 32 bits.
    text=page.read_text().replace("!(1u64<<63)","!((1u64<<63)|(7u64<<56))")
    page.write_text(text.replace("(w[4]>>32) as usize","((w[4]>>32) | (((w[i]>>56)&7)<<32)) as usize"))
    # The root licenses a bounded walk through the compiled Let edge pairs.
    # A Set receipt has its own proof and ends its path.
    edit(strict,"struct State {reader:", "struct State {walk:bool,reuse_let:bool,reader:")
    edit(strict,"    if depth > 2 {",'''    let walk = spec["pair_walk"] == true;
    if walk && (spec["library"].is_null() || spec["explore_second"]==true) {
        return Err("pair walk requires an explicit library".into());
    }
    if depth > 2 && !walk {''')
    edit(strict,"    s.reader=RouteReader::load","""    s.walk=walk;
    s.reuse_let=spec["reuse_let"]==true;
    s.reader=RouteReader::load""")
    edit(strict,"p.is_empty()\n                || p.len() > depth",
         "p.is_empty() || p.len()>2\n                || p.len() > depth")
    edit(strict,"if internal.path.len() < s.depth {","if internal.path.len() < s.depth && internal.set_data.is_none() {")
    edit(strict,"&& s.library.as_ref().is_some_and(|lib| !lib.contains(&path))",
         """&& s.library.as_ref().is_some_and(|lib| {
                        let start=if s.walk {path.len().saturating_sub(2)} else {0};
                        !lib.contains(&path[start..])
                    })""")
    edit(strict,"if reused && (!a.block || a.prior.len()!=0 ||\n                !s.set_plan.as_ref().is_some_and(|p|path.as_slice()==[p.first]) ||",
         """if reused && (!s.reuse_let && (!a.block || !a.prior.is_empty() ||
                !s.set_plan.as_ref().is_some_and(|p|path.as_slice()==[p.first])) ||""")
    edit(crate/"src/ripsat_set_publication.rs","|| s.depth != 2","|| s.depth < 2")
    edit(strict,"struct State {walk:",'''struct State {set_ops:BTreeSet<(usize,usize,usize)>,
        staged_sets:Vec<(u32,usize,FactRef,usize,u64,bool)>,walk:''')
    edit(strict,"let crate::program::Op::Let(_, Call::Table(t), _) = ins else {\n                    continue;",
         '''let t = match ins {
                    crate::program::Op::Let(_, Call::Table(t), _) => t,
                    crate::program::Op::Set(t,_,_) if spec["set_edges"]==true
                        && g.program.tables[*t].constructor && g.program.tables[*t].virtual_fact => {
                        s.set_ops.insert((rid,op,*t));
                        t
                    }
                    _ => continue,''')
    edit(strict,"    register_result(f.cell, f.op as usize, f, t, epoch, false);",
         """    if !stage_set_edge(f.cell,f.op as usize,f,t,epoch,false) {
        register_result(f.cell, f.op as usize, f, t, epoch, false);
    }""")
    with strict.open("a") as f:
        f.write('''
pub(crate) fn stage_set_edge(cell:u32,op:usize,f:FactRef,t:usize,epoch:u64,reused:bool)->bool{
    S.with_borrow_mut(|v|{
        let Some(s)=v else{return false};
        let Some(a)=&s.active else{return false};
        if s.physical!=Some(cell) || !s.set_ops.contains(&(a.rule,op,t)){return false;}
        s.staged_sets.push((cell,op,f,t,epoch,reused));
        true
    })
}
pub(crate) fn finish_set_edges(success:bool){
    let rows=S.with_borrow_mut(|v|v.as_mut().map(|s|std::mem::take(&mut s.staged_sets)));
    if success && let Some(rows)=rows {
        for (cell,op,f,t,epoch,reused) in rows {register_result(cell,op,f,t,epoch,reused);}
    }
}
''')
    # Leave the certified Set terminal to its typed receipt, including fault tests.
    edit(strict,"            if path.len() > s.depth",'''            if s.set_plan.as_ref().is_some_and(|p|path.as_slice()==[p.first,p.second]) {
                continue;
            }
            if path.len() > s.depth''')
    edit(crate/"src/graph.rs","            if signed_set{crate::strict_named::set_existing();}",
         """            if !old.hidden && let Dependency::Fact(f)=old.witness {
                crate::strict_named::stage_set_edge(cell,op,f,t,old.epoch,true);
            }
            if signed_set{crate::strict_named::set_existing();}""")
    edit(crate/"src/runtime.rs","        crate::strict_named::finish_set(result.is_ok())?;",
         """        crate::strict_named::finish_set(result.is_ok())?;
        crate::strict_named::finish_set_edges(result.is_ok());""")
    edit(strict,"struct State {set_ops:", "struct State {root_limit:Option<[usize;3]>,set_ops:")
    edit(strict,"    s.walk=walk;",'''    s.root_limit=spec.get("root_limit").map(|v|
        serde_json::from_value(v.clone()).map_err(|e|e.to_string())).transpose()?;
    if s.root_limit.is_some_and(|[rid,run,limit]|rid>=g.program.rules.len() || run==0 ||
        limit==0 || limit>depth){return Err("invalid signed root depth".into());}
    s.walk=walk;''')
    edit(strict,"struct Permit {block:", "struct Permit {limit:usize,block:")
    edit(strict,"struct Owner {returned:", "struct Owner {limit:usize,returned:")
    edit(strict,"if internal.path.len() < s.depth", "if internal.path.len() < internal.limit")
    edit(strict,"                    root: internal.root,", "                    limit:internal.limit,root: internal.root,")
    edit(strict,"                root: serial,",'''                limit:s.root_limit.filter(|p|p[0]==rid && p[1]==s.run).map_or(s.depth,|p|p[2]),
                root: serial,''')
    edit(strict,"let owner = Owner {returned:", "let owner = Owner {limit:a.limit,returned:")
    edit(strict,"if path.len() > s.depth","if path.len() > a.limit")
    edit(crate/"src/ripsat_set_publication.rs","let o = Owner {returned:", "let o = Owner {limit:2,returned:")
    edit(strict,"struct State {root_limit:","struct State {limited_roots:Vec<u64>,root_limit:")
    edit(strict,"            s.stats.external_roots += 1;",'''            if s.root_limit.is_some_and(|p|p[0]==rid && p[1]==s.run) && s.record_links {
                s.limited_roots.push(serial);
            }
            s.stats.external_roots += 1;''')
    edit(strict,'json!({"route_fallback":','json!({"limited_roots":s.limited_roots,"route_fallback":')
    edit(strict,"            if path.len() > a.limit",'''            // Keep the typed Set receipt reserved until RHS success. A deferred
            // Set also leaves any already registered owner of this witness intact.
            if s.pending_set.as_ref().is_some_and(|p|p.fact==f &&
                s.set_plan.as_ref().is_some_and(|plan|plan.second[2]==rid)) ||
                s.set_ops.contains(&(a.rule,op,t)) && s.ports.get(&rid)
                    .is_some_and(|ports|ports.contains_key(&Dependency::Fact(f))) {
                continue;
            }
            if path.len() > a.limit''')
    copyfile(Path(__file__).with_name("depth_reader.rs"),crate/"src/depth_reader.rs")
    with strict.open("a") as f:
        f.write('\ninclude!("depth_reader.rs");\n')
    edit(strict,"struct State {limited_roots:","struct State {depth_reader:Option<DepthReader>,limited_roots:")
    edit(strict,"    s.reader=RouteReader::load","    s.depth_reader=DepthReader::load(&spec[\"depth_reader\"],g,depth)?;\n    s.reader=RouteReader::load")
    edit(strict,"        let route = code >> 32;","""        let depth_action=code>>36;
        if depth_action>2 || depth_action!=0 && !s.depth_reader.as_ref().is_some_and(|m|m.rule==rid) {
            return Err("invalid signed depth selection".into());
        }
        let route = (code >> 32)&7;""")
    edit(strict,"            s.stats.external_roots += 1;","""            if let Some(m)=s.depth_reader.as_mut() && m.rule==rid {
                m.applied[depth_action]+=1;
                if s.record_links {m.caps.push((serial,s.run,depth_action));}
                if depth_action!=0 {m.runs.insert(s.run);}
            }
            s.stats.external_roots += 1;""")
    edit(strict,"limit:s.root_limit.filter","limit:if depth_action==1 {2} else if depth_action==2 {8} else {s.root_limit.filter")
    edit(strict,".map_or(s.depth,|p|p[2]),",".map_or(s.depth,|p|p[2])},")
    edit(strict,'json!({"limited_roots":','json!({"depth_caps":s.depth_reader.as_ref().map(|m|&m.caps),"depth_choices":s.depth_reader.as_ref().map(|m|(m.applied,m.runs.len())),"limited_roots":')
    edit(page,"        let context=crate::strict_named::route_page","        let depths=crate::strict_named::depth_page(graph,rid);\n        let context=crate::strict_named::route_page")
    edit(page,"            words.extend([tag|action|route, addr, v]);","""            let depth=depths.as_ref().map_or(0,|rows|crate::strict_named::depth_bits(graph,rows,dep));
            words.extend([tag|action|route|depth, addr, v]);""")
    text=page.read_text().replace("!((1u64<<63)|(7u64<<56))","!((1u64<<63)|(7u64<<56)|(3u64<<54))")
    page.write_text(text.replace("(((w[i]>>56)&7)<<32)", "(((w[i]>>56)&7)<<32) | (((w[i]>>54)&3)<<36)"))
    copyfile(Path(__file__).with_name("row_guards.rs"),crate/"src/row_guards.rs")
    with strict.open("a") as f:
        f.write('\ninclude!("row_guards.rs");\n')
    edit(strict,"struct State {depth_reader:","struct State {row_guards:BTreeMap<usize,Vec<RowGuard>>,guard_pass:u64,guard_fail:u64,depth_reader:")
    edit(strict,"if !r.seminaive || r.query.len() != 1 {", """if !r.seminaive || r.query.is_empty()
                || r.query.len()>1 && spec["row_guards"]!=true {""")
    edit(strict,"|| !r.inputs.iter().all(|v| slots.contains(v))","|| r.query.len()==1 && !r.inputs.iter().all(|v| slots.contains(v))")
    edit(strict,"            s.targets.entry(t).or_default().push(rid);","""            if r.query.len()>1 {
                let Some(guards)=RowGuard::compile(&r.query) else {continue};
                if !guards.iter().all(|test|slots.insert(test.dst)) ||
                    !r.inputs.iter().all(|v|slots.contains(v)){continue;}
                s.row_guards.insert(rid,guards);
            }
            s.targets.entry(t).or_default().push(rid);""")
    edit(strict,"            let mut input = Slots::default();","""            let mut input = Slots::default();
            if let Some(guards)=s.row_guards.get(&rid) {
                let mut passed=true;
                for test in guards {
                    let Some(value)=test.accepts(g,&row.values)? else {passed=false;break;};
                    input.insert(test.dst,value);
                }
                if !passed {
                    s.guard_fail+=1;
                    live-=1;
                    continue;
                }
                s.guard_pass+=1;
            }""")
    edit(strict,"            for &slot in rule.inputs.iter() {","            for &slot in rule.inputs.iter() {\n                if input.get(&slot).is_some(){continue;}")
    edit(strict,'json!({"depth_caps":','json!({"row_guard_checks":[s.guard_pass,s.guard_fail],"depth_caps":')
    edit(crate/"src/strict_partial.rs","|| p.order.len() != 0","|| !p.order.is_empty() && !crate::strict_named::row_guarded(rid)")
    with strict.open("a") as f:
        f.write('pub(crate) fn row_guarded(rid:usize)->bool{S.with_borrow(|s|s.as_ref().is_some_and(|v|v.row_guards.contains_key(&rid)))}\n')
    edit(crate/"src/stage_spine.rs",'if rule.query.len()!=1{return Err("strict Spine needs a sole pivot".into())}',
         'if rule.query.len()!=1 && !crate::strict_named::row_guarded(rid){return Err("strict Spine needs a sole table pivot".into())}')
    edit(strict,'matches!(arg, Arg::Literal(expected) if expected != value)) {\n                continue;',
         '''matches!(arg, Arg::Literal(expected) if expected != value)) {
                if s.row_guards.contains_key(&rid) { live-=1; }
                continue;''')
    # Audit output coordinates at the actual constructor return, including reused rows.
    root=crate/"src/joint_root.rs"
    edit(root,"audit:bool,emitted:", "history_issuer:Option<HistoryIssuer>,history:Option<([usize;2],Vec<[u64;8]>)>,pair_issuer:Option<PairIssuer>,pair_trace:Option<(Vec<usize>,Vec<[u64;7]>)>,audit:bool,emitted:")
    edit(root,"State{stage_watch:false,", "State{pair_issuer:None,history_issuer:None,history:None,pair_trace:None,stage_watch:false,")
    edit(root,'"root_row_decodes":s.decodes', '"pair_checks":s.pair_issuer.as_ref().map(|p|[p.checked,p.verified]),"pair_proposals":s.pair_issuer.as_ref().map(|p|&p.proposals),"history_tail_misses":s.history_issuer.as_ref().and_then(|h|h.tail.as_ref()).map(|t|&t.omitted),"point_stale_omissions":s.history_issuer.as_ref().and_then(|h|h.tail.as_ref()).map(|t|t.points.stale_omissions),"point_union_probes":s.history_issuer.as_ref().and_then(|h|h.tail.as_ref()).map(|t|t.points.union_probes),"point_rekeyed":s.history_issuer.as_ref().and_then(|h|h.tail.as_ref()).map(|t|t.points.rekeyed),"point_skips":s.history_issuer.as_ref().and_then(|h|h.tail.as_ref()).map(|t|&t.points.skipped),"point_claims":s.history_issuer.as_ref().and_then(|h|h.tail.as_ref()).map(|t|(&t.points.attempts,&t.points.children,&t.points.misses)),"history_scale":s.history_issuer.as_ref().and_then(|h|h.tail.as_ref()).map(|t|t.scale),"history_tail":s.history_issuer.as_ref().and_then(|h|h.tail.as_ref()).map(|t|(t.attempts,&t.children)),"history_suppressed":s.history_issuer.as_ref().map(|h|&h.suppressed),"history_updates":s.history_issuer.as_ref().map(|h|&h.updates),"history_initial":s.history_issuer.as_ref().map(|h|&h.seeds),"history_access":s.history_issuer.as_ref().map(|h|[h.probes,h.visits]),"history_online":s.history_issuer.as_ref().map(|h|(&h.checked,&h.pending)),"history_returns":s.history.as_ref().map(|h|&h.1),"pair_returns":s.pair_trace.as_ref().map(|(_,rows)|rows),"root_row_decodes":s.decodes')
    with root.open("a") as f:
        f.write("""
pub fn enable_return_history(program:&Program)->Result<()> {
    let table=|name:&str|program.tables.iter().position(|t|t.name==name).ok_or("missing history table");
    let tables=[table("Get")?,table("HasArgType")?];
    STATE.with_borrow_mut(|s|if let Some(s)=s{s.history=Some((tables,Vec::new()))});
    Ok(())
}
pub(crate) fn history_return(table:usize,key:&[Value],result:&Value,op:usize,dep:Dependency,version:u64,epoch:u64){
    STATE.with_borrow_mut(|s|{
        let Some(s)=s else{return};
        if s.point_authorized && let Some((owner,_,_,rid,_))=s.active && let Dependency::Fact(f)=dep
            && let Some(wires)=s.layout[rid].point_wires.get(&op)
            && let Some(tail)=s.history_issuer.as_mut().and_then(|h|h.tail.as_mut()){
            for &(child,projection) in wires {
                let prefix=projection.and_then(|i|if i==key.len(){Some(result)}else{key.get(i)});
                let prefix=match prefix { Some(Value::Eq(id))=>Some(*id), _=>None };
                tail.points.pending.entry(child).or_default()
                    .entry([u64::from(f.cell),u64::from(f.op),version])
                    .or_insert((owner,epoch,prefix));
            }
        }
        if s.active.is_some() && let Some(t)=s.history_issuer.as_mut().and_then(|h|h.tail.as_mut())
            && let Dependency::Fact(f)=dep {t.returned(table,key,result,[f.cell as u64,f.op as u64,version]);}
        let Some((tables,rows))=&mut s.history else{return};
        let Some(role)=tables.iter().position(|t|*t==table) else{return};
        let Some((ordinal,_,_,_,_))=s.active else{return};
        if let (Some(Value::Eq(subject)),Dependency::Fact(f))=(key.first(),dep){
            if let Some(h)=&mut s.history_issuer {
                if let Some(t)=&mut h.tail && role==1 && let Some((owner,effect,depth))=t.active && owner==ordinal && effect==op {t.pending.entry([f.cell as u64,f.op as u64,version]).or_insert((ordinal,epoch,depth));}
                h.observe(epoch,role,(ordinal,op as i64),[f.cell as u64,f.op as u64,version],*subject);}
            rows.push([epoch,ordinal as u64,op as u64,role as u64,f.cell as u64,f.op as u64,version,*subject]);
        }
    })
}
pub fn trace_pair_rules(rules:Vec<usize>) {
    STATE.with_borrow_mut(|s| if let Some(s)=s {s.pair_trace=Some((rules,Vec::new()));});
}
pub(crate) fn trace_pair_return(op:usize,dep:Dependency,version:u64,reused:bool) {
    STATE.with_borrow_mut(|s|{
        let Some(s)=s else{return};
        let Some((ord,_,_,rule,_))=s.active else{return};
        if let Some(p)=&mut s.pair_issuer && p.policy.wiring.contains_key(&rule)
            && let Dependency::Fact(f)=dep {
            p.frame.insert(op,([u64::from(f.cell),u64::from(f.op),version],reused));
        }
        let Some((rules,rows))=&mut s.pair_trace else{return};
        if !rules.contains(&rule){return}
        if let Dependency::Fact(f)=dep{
            rows.push([ord as u64,rule as u64,op as u64,u64::from(f.cell),u64::from(f.op),version,u64::from(reused)]);
        }
    });
}
""")
    copyfile(Path(__file__).with_name("history_tail.rs"),crate/"src/history_tail.rs")
    with root.open("a") as f:
        f.write('\ninclude!("history_tail.rs");\n')
    copyfile(Path(__file__).with_name("history_issuer.rs"),crate/"src/history_issuer.rs")
    with root.open("a") as f:
        f.write('\ninclude!("history_issuer.rs");\n')
    edit(root,'if state.audit{state.commits.push','if let Some(h)=&mut state.history_issuer{h.cite(epoch,state.ordinal,r.serial,rid,&r.refs,inputs);}\n        if state.audit{state.commits.push')
    copyfile(Path(__file__).with_name("pair_issuer.rs"),crate/"src/pair_issuer.rs")
    with root.open("a") as f:
        f.write('\ninclude!("pair_issuer.rs");\n')
    edit(crate/"src/runtime.rs","        crate::joint_root::end();",
         "        crate::joint_root::finish_pair(self.graph.epoch,result.is_ok());\n        crate::joint_root::end();")
    session=crate/"examples/joint_witness_session.rs"
    anchor="eggfuse_cell_runtime::joint_root::configure(&program,root_config.as_deref(),audit)?;"
    edit(session,anchor,anchor+"""
        if !req["history_head"].is_null(){eggfuse_cell_runtime::joint_root::configure_history_issuer(&runtime.graph,&req["history_head"])?;}
        if req["history_ports"].as_bool()==Some(true){eggfuse_cell_runtime::joint_root::enable_return_history(&program)?;}
        if !req["pair_policy"].is_null(){
            eggfuse_cell_runtime::joint_root::configure_pair_policy(serde_json::from_value(req["pair_policy"].clone()).map_err(|e|e.to_string())?,&program,&program_bytes)?;
        }
        if let Some(rules)=req["pair_trace_rules"].as_array(){
            let rules=rules.iter().map(|r|r.as_u64().map(|x|x as usize).ok_or("invalid trace rule")).collect::<std::result::Result<Vec<_>,_>>()?;
            eggfuse_cell_runtime::joint_root::trace_pair_rules(rules);
        }""")
    edit(crate/"src/graph.rs","crate::strict_named::returned(cell,op,row.witness,t,row.epoch);",
         "crate::joint_root::history_return(t,&row.values,row.values.last().unwrap(),op,row.witness,row.epoch,self.epoch);\n                crate::joint_root::trace_pair_return(op,row.witness,row.epoch,true);\n                crate::strict_named::returned(cell,op,row.witness,t,row.epoch);")
    edit(crate/"src/graph.rs","let value = self.insert_constructor(cell, op, t, &key, dst)?;",
         """let value = self.insert_constructor(cell, op, t, &key, dst)?;
        crate::joint_root::history_return(t,&key,&value,op,Dependency::Fact(FactRef{cell,op:op as u32}),self.epoch,self.epoch);
        crate::joint_root::trace_pair_return(op,Dependency::Fact(FactRef{cell,op:op as u32}),self.epoch,false);""")
    edit(crate/"src/ordinary_witness.rs","let rule=&g.program.rules[rid];\n        let plan=s.plans",
         "crate::joint_root::check_pairs(g,rid,mark)?;\n        let history_pairs=crate::joint_root::check_history_issuer(g,rid,mark)?;\n        let rule=&g.program.rules[rid];\n        let plan=s.plans")
    copyfile(Path(__file__).with_name("pair_takeover.rs"),crate/"src/pair_takeover.rs")
    with root.open("a") as f:
        f.write('\ninclude!("pair_takeover.rs");\n')
    edit(root,'struct Layout{rid:','struct Layout{axiom:bool,pair_program:bool,rid:')
    edit(root,'Layout{rid,template:','Layout{axiom:rule.query.is_empty() && rule.inputs.is_empty(),pair_program:false,rid,template:')
    edit(root,'pair_issuer:Option<PairIssuer>,pair_trace:', 'pair_authorized:bool,pair_issuer:Option<PairIssuer>,pair_trace:')
    edit(root,'State{pair_issuer:None,','State{pair_authorized:false,pair_issuer:None,')
    edit(root,'state.active=Some((state.ordinal,r.origin','state.pair_authorized=r.layout.pair_program && (!r.refs.is_empty() || r.layout.axiom);\n        state.active=Some((state.ordinal,r.origin')
    edit(root,'if let Some(p)=&mut s.pair_issuer && p.policy.wiring.contains_key(&rule)',
         'if let Some(p)=&mut s.pair_issuer && (!p.policy.takeover || s.pair_authorized) && p.policy.wiring.contains_key(&rule)')
    edit(root,'"pair_checks":s.pair_issuer','"pair_external":s.pair_issuer.as_ref().map(|p|&p.external),"pair_children":s.pair_issuer.as_ref().map(|p|&p.children),"pair_checks":s.pair_issuer')
    edit(session,'        let ingest_start=Instant::now();','        eggfuse_cell_runtime::joint_root::prepare_pair_degree(&program,&req["pair_policy"])?;\n        let ingest_start=Instant::now();')
    g=crate/"src/graph.rs"
    edit(g,'        self.stats.logical_facts_created += 1;', '        crate::joint_root::pair_birth(self,t,&v);\n        self.stats.logical_facts_created += 1;')
    edit(g,'        self.parents.insert(hi, lo);','        crate::joint_root::pair_union(hi,lo);\n        self.parents.insert(hi, lo);')
    witness=crate/"src/ordinary_witness.rs"
    edit(witness,'struct Store {wave:', 'struct Store {pair_queue:Vec<(usize,crate::joint_root::ReturnedPair)>,wave:')
    edit(witness,'let s=Store{wave:', 'let s=Store{pair_queue:vec![],wave:')
    edit(witness,'            for refs in groups{\n                let bank=', '''            let mut direct=std::mem::take(&mut s.pair_queue).into_iter().peekable();
            let count=groups.len();let mut groups=groups.into_iter();
            for j in 0..=count{
                while direct.peek().is_some_and(|x|x.0==j){
                    let (_,pair)=direct.next().unwrap();
                    pages.push(crate::joint_root::pair_child(g.epoch,rid,pair)?);
                    tuples+=1;
                }
                let Some(refs)=groups.next() else{continue};
                let bank=''')
    pairs=crate/"src/incremental_raw.rs"
    a='        let full_left = left.frame.rows.len();'
    edit(pairs,a,'''        let mut protected=BTreeMap::new();
        if self.wave.preparing{
            for (pivot, pair) in crate::joint_root::take_pair_pivots(self.rule){
                if left.atom!=0 || right.atom!=1{return Err("unsupported protected pair ordering".into())}
                let pos=left.frame.rows.binary_search_by_key(&pivot,|r|r.witness)
                    .map_err(|_|"missing verified pivot position")?;
                protected.insert(pos,pair);
            }
        }
'''+a)
    a='                            for &l in indices {'
    edit(pairs,a,a+'\n                                if protected.contains_key(&l){continue;}')
    edit(pairs,'            active.sort_unstable();','            active.extend(protected.keys().copied());active.sort_unstable();active.dedup();')
    a='            let l = if selective { active[pos] } else { pos };'
    edit(pairs,a,a+'''
            if let Some(pair)=protected.remove(&l){
                if !self.page_refs.is_empty(){self.pending_pages.push(std::mem::take(&mut self.page_refs));}
                self.pair_queue.push((self.pending_pages.len(),pair));continue;
            }''')
    a='        self.flat_offsets.clear();\n        Ok(())\n    }\n}'
    edit(pairs,a,'        if !protected.is_empty(){return Err("unplaced pair continuation".into())}\n'+a)
    pages=crate/"src/multi_root_pages.rs"
    anchor="        for entry in refs.chunks_exact(width) {"
    edit(pages,anchor,anchor+"""
            if st.audit && let Some(p)=&mut st.pair_issuer && p.policy.target==rid {
                let a=entry.first().filter(|r|r.atom==0).ok_or("missing residual pivot")?;
                let Dependency::Fact(f)=a.row else{return Err("invalid residual pivot".into())};
                p.external.push([run,u64::from(f.cell),u64::from(f.op)]);
            }""")
    copyfile(Path(__file__).with_name("ept.rs"),crate/"src/ept.rs")
    with (crate/"src/lib.rs").open("a") as f:
        f.write('\npub mod ept;\n')
    edit(session,'        let start = Instant::now();','        eggfuse_cell_runtime::ept::start(req["ept"]==true);\n        let start = Instant::now();')
    edit(session,'        report["root_recipe"]=', '        report["ept"]=json!(eggfuse_cell_runtime::ept::finish());\n        report["root_recipe"]=')
    runtime=crate/"src/runtime.rs"
    edit(runtime,'        crate::transfer_audit::rhs(rid);','        crate::transfer_audit::rhs(rid);\n        crate::ept::rhs();')
    edit(runtime,'        crate::joint_root::end();','        crate::ept::end_rhs();\n        crate::joint_root::end();')
    text=runtime.read_text().replace('crate::transfer_audit::end_writes();','crate::transfer_audit::end_writes();\n        crate::ept::boundary(&self.graph)?;')
    runtime.write_text(text)
    edit(g,'        self.pending_unions.push((a, b));','        crate::ept::queue(a,b);\n        self.pending_unions.push((a, b));')
    a="    fn union(&mut self, a: u64, b: u64) -> Result<()> {\n        let a = root(&self.parents, a);\n        let b = root(&self.parents, b);"
    edit(g,a,a.replace("        let a =", "        let requested=(a,b);\n        let a =")+
         "\n        crate::ept::union(requested.0,requested.1,a.max(b),a.min(b))?;")
    edit(g,'        crate::transfer_audit::birth(t, key, &v, f.ordered_id());','        crate::transfer_audit::birth(t, key, &v, f.ordered_id());\n        crate::ept::birth(f,t);')
    a='    pub fn hide(&mut self, t: usize, key: &[Value], delete: bool) -> Result<bool> {'
    edit(g,a,a+"""
        self.ept_hide(t,key,delete,true)
    }
    fn ept_hide(&mut self,t:usize,key:&[Value],delete:bool,existing:bool)->Result<bool>{""")
    edit(g,'                self.hide(t, key, false)?;', '                self.ept_hide(t,key,false,false)?;')
    a='        match row.witness {\n            Dependency::Fact(f) => {\n                let born'
    edit(g,a,'        if existing && !row.hidden {crate::ept::hide(t,row.witness);}\n'+a)
    audit=crate/"src/transfer_audit.rs"
    edit(audit,'    event(|| serde_json::json!(["write",', '    crate::ept::write(table,index);\n    event(|| serde_json::json!(["write",')
    copyfile(Path(__file__).with_name("size_reader.rs"),crate/"src/size_reader.rs")
    with (crate/"src/lib.rs").open("a") as f:
        f.write('\npub mod size_reader;\n')
    edit(session,'        let initial_graph_ms=', '        eggfuse_cell_runtime::size_reader::configure(&runtime.graph,&req["size_reader"],audit)?;\n        let initial_graph_ms=')
    edit(session,'        report["ept"]=', '        report["size_omission_checks"]=json!(eggfuse_cell_runtime::size_reader::audit_count());report["size_predictions"]=eggfuse_cell_runtime::size_reader::forecasts(); report["size_reader"]=eggfuse_cell_runtime::size_reader::report();\n        report["ept"]=')
    a='            let recipe = if send && !self.rows.batch {'
    edit(crate/"src/adaptive_rows.rs",a,'''            if send && self.rows.batch && !self.residual
                && crate::size_reader::reject(g,rid,p.pivot,h.source,wm,self.serial)? {
                crate::size_reader::omitted(rid,(self.serial,h.source,h.version,h.initial,score));
                omitted+=1;
                continue;
            }
'''+a)
    single=crate/"src/single_witness.rs"
    a="        if let Some(omitted)=self.rows.scalar.skipped.remove(&rid){"
    edit(single,a,"""        if let Some(batch)=crate::size_reader::audit_batch(rid){
            let saved=self.work;
            for &(id,w,version,initial,score) in &batch{
                let token=Token{recipe:None,id,rid,w,version,initial,score,guarded:false};
                if self.check(g,r,&p,&token,wm)?.is_some(){return Err("omitted a valid source binding".into())}
            }
            crate::size_reader::audited(batch.len());
            self.work=saved;
        }
"""+a)

    edit(witness,'if rule.query.iter().any(|a|matches!(a.call,Call::Table(t) if g.witness_count(t)==0))',
         'if history_pairs.is_none() && rule.query.iter().any(|a|matches!(a.call,Call::Table(t) if g.witness_count(t)==0))')
    edit(witness,'remaining.clone_from(&saved.remaining);} else {','remaining.clone_from(&saved.remaining);} else if history_pairs.is_none() {')
    edit(witness,'if deferred.is_some(){}else if s.accel>=4{','''if deferred.is_some(){}else if let Some(mut pairs)=history_pairs {
            if !s.page || !c.sealing || c.inst.len()!=2 || c.pick_count!=2 || s.residual {
                return Err("history takeover requires two explicit parents and no residual".into())
            }
            pairs.sort_by_key(|pair|[pair[c.inst[0].0],pair[c.inst[1].0]]);
            for pair in pairs {
                for &(atom,_,_) in c.inst {
                    let [cell,op,version]=pair[atom];
                    s.page_refs.push(crate::joint_root::Ref{atom,row:Dependency::Fact(crate::graph::FactRef{cell:cell as u32,op:op as u32}),version});
                }
            }
        }else if s.accel>=4{''')

    completion = crate/"src/runtime_completion.rs"
    edit(completion,'crate::ordinary_witness::changed_frame_rows(&self.graph);',
         'crate::joint_root::history_updates(&self.graph)?;\n        crate::ordinary_witness::changed_frame_rows(&self.graph);')

    edit(single,'pub(crate) struct Trial{','pub(crate) struct Trial{tail_bindings:BTreeMap<(usize,Dependency,u64),Instance>,')
    edit(single,'Ok(Self{waiting_wave:', 'Ok(Self{tail_bindings:BTreeMap::new(),waiting_wave:')
    anchor='let matched=if self.rows.verify.mode==0'
    edit(single,anchor,'let prior=token.w.and_then(|w|self.tail_bindings.remove(&(rid,w,token.version)));\n            let matched=if prior.is_some(){prior}else if self.rows.verify.mode==0')
    rows=crate/"src/adaptive_rows.rs"
    anchor='        let model = self\n            .policy'
    edit(rows,anchor,'''        let claims=crate::joint_root::history_tail_claims(rid,g,wm);
        let mut inherited=BTreeMap::new();
        let mut failed_tail=BTreeMap::new();
        for (w,version,owner,depth,pivot) in claims {
            if p.pivot!=Some(pivot) || p.order.as_slice()!=[1-pivot] || self.residual || !self.rows.batch {
                return Err("incompatible signed point plan".into())
            }
            let token=Token{recipe:None,id:0,rid,w:Some(w),guarded:false,version,initial:false,score:0.};
            if let Some(binding)=self.check(g,r,p,&token,wm)?{
                inherited.insert((w,version),(owner,depth,binding));
            } else {failed_tail.insert((w,version),owner);}
        }
'''+anchor)
    anchor='            if send && self.rows.batch && self.rows.scalar.enabled'
    edit(rows,anchor,'''            if let Some((w,(owner,depth,binding)))=h.source.and_then(|w|inherited.remove(&(w,h.version)).map(|v|(w,v))) {
                if !send{return Err("signed child lost source ownership".into())}
                let recipe=crate::joint_root::history_tail_recipe(g.epoch,rid,w,h.version,owner,depth)?;
                if self.tail_bindings.insert((rid,w,h.version),binding).is_some(){return Err("duplicate signed child".into())}
                result.push((Token{recipe:Some(recipe),id:self.serial,rid,w:h.source,version:h.version,initial:h.initial,score,guarded:false},base,true));
                emitted+=1;
                continue
            }
'''+anchor)
    edit(rows,'        if self.rows.batch && !result.is_empty() {','        if !inherited.is_empty(){return Err("source missed a signed child".into())}\n        if self.rows.batch && !result.is_empty() {')
    for prefix in ('.iter()\n                    ', 'shard.iter_mut()'):
        edit(rows,prefix+'.filter(|(_, _, send)| *send)',prefix+'.filter(|(t, _, send)| *send && t.recipe.is_none())')

    anchor='            let recipe = if send && !self.rows.batch {'
    edit(rows,anchor,'''            if send && let Some((w,owner))=h.source.and_then(|w|failed_tail.remove(&(w,h.version)).or_else(||crate::joint_root::owned_stale_point(g,rid,wm,w,h.version)).map(|o|(w,o)))
                && crate::joint_root::history_tail_miss(rid,g.epoch,w,h.version,owner) {
                omitted+=1;
                continue
            }
'''+anchor)

    copyfile(Path(__file__).with_name("point_claims.rs"),crate/"src/point_claims.rs")
    with root.open("a") as f:
        f.write('\ninclude!("point_claims.rs");\n')
    edit(root,"struct Layout{axiom:","struct Layout{point_wires:BTreeMap<usize,Vec<(usize,Option<usize>)>>,axiom:")
    edit(root,"Layout{axiom:rule.query","Layout{point_wires:Default::default(),axiom:rule.query")
    edit(root,"struct State{stage_watch:", "struct State{point_authorized:bool,stage_watch:")
    edit(root,"State{pair_authorized:false,","State{point_authorized:false,pair_authorized:false,")
    edit(root,"state.active=Some((state.ordinal", "state.point_authorized=!r.refs.is_empty() && !r.layout.point_wires.is_empty();\n        state.active=Some((state.ordinal")
    edit(crate/"src/history_issuer.rs","    Ok(())\n}\n\nimpl HistoryIssuer", '    configure_point_claims(g,&spec["point_claims"])\n}\n\nimpl HistoryIssuer')

    edit(g,"crate::joint_root::pair_union(hi,lo);","crate::joint_root::point_claim_union(hi,lo);\n        crate::joint_root::pair_union(hi,lo);")
