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
