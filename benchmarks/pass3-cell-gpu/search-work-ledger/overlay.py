"""Instrument the frozen, single-thread joint executor at candidate consumption."""
from pathlib import Path


def install(crate):
    def edit(file, old, new):
        path = crate / file
        contents = path.read_text()
        if contents.count(old) != 1:
            raise ValueError(f"{path}: incompatible instrumentation site {old!r}")
        path.write_text(contents.replace(old, new))

    # Keep the counter outside both providers so moving a loop preserves its charge.
    from shutil import copyfile
    copyfile(Path(__file__).parent/'work.rs', crate/'src/search_work.rs')
    with (crate/'src/lib.rs').open('a') as out:
        out.write('\npub mod search_work;\n')
    edit('src/runtime.rs','fn matches(&mut self, rid: usize, probe: bool) -> Result<Vec<Binding>> {',
         'fn matches(&mut self, rid: usize, probe: bool) -> Result<Vec<Binding>> { crate::search_work::enter(self.steps.len()+1,rid);')
    def hit(file, site, after, count='1'):
        edit('src/'+file, after, after+' crate::search_work::add('+str(site)+', '+count+');')

    hit('single_witness.rs', 0, 'for w in candidates{', 'usize::from(w.is_some())')
    hit('ordinary_witness.rs', 1, 'let mut visit=|this:&mut Self,row:&Row|->Result<()>{')
    hit('ordinary_shortlist.rs', 1, 'let j=list.as_ref().map_or(pos,|v|v[pos]);')
    hit('ordinary_witness.rs', 2, 'for w in g.witnesses(t){')
    hit('ordinary_witness.rs', 2, 'for (i,row) in f.rows.iter().enumerate(){')
    hit('runtime.rs', 3, 'let mut deliver = |w| {')
    hit('runtime.rs', 4, 'for (seed_index, w) in candidates.into_iter().enumerate() {')
    hit('runtime.rs', 4, 'for (supplied, row) in candidates {')
    hit('runtime.rs', 5, 'for w in witnesses.iter().copied() {', 'usize::from(!query[chosen].args[..query[chosen].args.len()-1].iter().all(|a|operand(a,env,&self.graph).is_some()))')
    hit('execute_kernel.rs', 5, 'for row in &rows[..count] {')
    hit('execute_kernel.rs', 5, '                } else {\n                    for &w in refs.iter() {')
    hit('runtime.rs', 5, 'let refs = self.query_indexes.candidates(&self.graph, *t, &bound)?;', 'refs.len()')
    edit('src/single_witness.rs','self.work[2]+=1;', 'self.work[2]+=1; crate::search_work::add(if send {6} else {9}, usize::from(token.w.is_some()));')
    hit('ordinary_witness.rs', 6, 'for (i,&address) in parents.iter().enumerate(){')
    hit('ordinary_shortlist.rs', 6, 'for (i,&(address,pos)) in packet.iter().enumerate(){')
    hit('ordinary_shortlist.rs', 7, 'for &i in positions{')
    session = 'examples/joint_witness_session.rs'
    edit(session, 'let mut runtime = Executor::new', 'eggfuse_cell_runtime::search_work::take();\n        let mut runtime = Executor::new')
    edit(session, 'writeln!(out, "{}", report)?;', '''let (counts,sites)=eggfuse_cell_runtime::search_work::take();
        report["search_sites"]=json!(sites);
        report["search_work"] = json!(counts);
        writeln!(out, "{}", report)?;''')

    # These controls change keyed independent-parent retrieval only.
    edit('src/ordinary_witness.rs','struct Store {','struct Store {page_weights:Option<[f32;6]>,page_budget:usize,')
    edit('src/ordinary_witness.rs','let s=Store{','let s=Store{page_weights:None,page_budget:0,')
    edit('src/ordinary_witness.rs','struct Frame {','struct Frame {pages:RefCell<HashMap<usize,Vec<Header>>>,')
    edit('src/ordinary_witness.rs','Rc::new(Frame{generation:', 'Rc::new(Frame{pages:RefCell::default(),generation:')
    target = crate/'src/ordinary_witness.rs'
    with target.open('a') as output:
        output.write((Path(__file__).parent/'pages.rs').read_text())
        output.write("""
pub fn page_policy(weights:[f32;6],budget:usize) -> Result<()> {
    if budget==0 || !weights.iter().all(|x|x.is_finite()){return Err("invalid page policy".into());}
    STORE.with_borrow_mut(|s| -> Result<()> {
        let s=s.as_mut().ok_or("missing policy")?;
        if s.accel!=4 || s.views!=3{return Err("requires three-view stack issuer".into());}
        s.page_weights=Some(weights);s.page_budget=budget;Ok(())
    })
}
""")
    edit('src/ordinary_shortlist.rs','let idx=self.index(d.table,col,&d.frame);',
         'if self.page_weights.is_some(){ Some(self.page_choices(&d.frame,col,ports[slot].ok_or("missing query")?)) } else { let idx=self.index(d.table,col,&d.frame);')
    edit('src/ordinary_shortlist.rs','ok_or("missing parent token port")?))','ok_or("missing parent token port")?)) }')
    edit('src/ordinary_shortlist.rs','d.shared.iter().skip(1)', 'd.shared.iter().skip(usize::from(self.page_weights.is_none()))')
    edit(session,'runtime.use_single_witness(Path::new(', """
            if let Some(policy)=req.get("page_policy") {
                ordinary_witness::page_policy(serde_json::from_value(policy["weights"].clone())?,
                    usize::try_from(policy["budget"].as_u64().ok_or("page budget")?)?)?;
            }
            runtime.use_single_witness(Path::new(""")

    edit(session,'report["search_work"] =', """
        if audit {
            let mut visible = Vec::new();
            for (t, table) in program.tables.iter().enumerate() {
                if table.constructor {
                    for w in runtime.graph.witnesses(t) {
                        let eggfuse_cell_runtime::graph::Dependency::Fact(f)=w else {return Err("unexpected constructor witness".into());};
                        let row=runtime.graph.row(w)?.ok_or("missing endpoint row")?;
                        if !row.hidden {visible.push((u64::from(f.cell)<<32)|u64::from(f.op));}
                    }
                }
            }
            report["visible_constructor_refs"] = json!(visible);
        }
        report["search_work"] =""")

    # Oracle labels are collected on the independent reference arm only.
    edit('src/ordinary_witness.rs','struct Ticket {','struct Ticket {audit_pages:Vec<usize>,')
    edit('src/ordinary_witness.rs','self.tickets.push(Ticket{','''let mut audit_pages=Vec::new();
            if self.detailed && self.capture_pages {
                for (i,w) in p.anchors.iter().enumerate() {
                    let Call::Table(t)=c.rule.query[c.inst[i].0].call else{return Err("non-table witness".into())};
                    let f=self.frames.get(&t).ok_or("missing reference frame")?;
                    let index=f.rows.iter().position(|r|r.witness==*w).ok_or("winner outside source frame")?;
                    audit_pages.push(index/PAGE_SIZE);
                }
            }
            self.tickets.push(Ticket{audit_pages,''')
    edit('src/ordinary_witness.rs','struct Store {page_weights:', 'struct Store {capture_pages:bool,page_weights:')
    edit('src/ordinary_witness.rs','let s=Store{page_weights:', 'let s=Store{capture_pages:false,page_weights:')
    with target.open('a') as output:
        output.write('pub fn capture_pages(){ STORE.with_borrow_mut(|s|s.as_mut().unwrap().capture_pages=true); }\n')
    edit(session,'if let Some(policy)=req.get("page_policy") {', '''
            if req["capture_pages"]==true {ordinary_witness::capture_pages();}
            if let Some(policy)=req.get("page_policy") {''')

    copyfile(Path(__file__).parent/'roots.rs',crate/'src/proposal_roots.rs')
    with (crate/'src/lib.rs').open('a') as out:
        out.write('\npub(crate) mod proposal_roots;\n')
    edit('src/single_witness.rs','struct Trial{','struct Trial{root_memory:crate::proposal_roots::RootMemory,pub root_policy:Option<([f32;3],usize)>,')
    edit('src/single_witness.rs','Ok(Self{plans,initial,','Ok(Self{root_memory:Default::default(),root_policy:None,plans,initial,')
    edit('src/single_witness.rs','g.witnesses(t).into_iter().map(Some).collect()',
         '(if let Some((weights,budget))=self.root_policy {self.root_memory.read(g,t,wm,weights,budget)?} else {g.witnesses(t)}).into_iter().map(Some).collect()')
    edit('src/single_witness.rs','if !send&&!self.residual{continue;}',
         'if !send && (!self.residual || self.root_policy.is_some()){continue;}')
    # The old single-provider residual rechecks only the rows given to it. After
    # routing a subset we must restore the ordinary full-domain residual instead.
    edit('src/runtime.rs','routed.append(&mut rows);self.pending[rid].clear();',
         '''routed.append(&mut rows);
            if self.stage_spine.single.as_ref().is_some_and(|s|s.root_policy.is_some() && s.residual) {
                let policy=self.stage_spine.single.take();
                self.dirty[rid]=true;
                let rest=self.matches_before_ordinary_witness(rid,probe);
                self.stage_spine.single=policy;
                routed.extend(rest?);
            }
            self.pending[rid].clear();''')
    with (crate/'src/runtime.rs').open('a') as out:
        out.write("""
impl Executor{
    pub fn select_root_pages(&mut self, weights:[f32;3], budget:usize)->Result<()>{
        if budget==0 || weights.iter().any(|x|!x.is_finite()){return Err("invalid root policy".into());}
        self.stage_spine.single.as_mut().ok_or("missing single issuer")?.root_policy=Some((weights,budget));
        Ok(())
    }
}
""")
    edit(session,'let initial_cells = runtime.graph.stats.cells_created;', '''if let Some(policy)=req.get("root_page_policy") {
            runtime.select_root_pages(serde_json::from_value(policy["weights"].clone())?,
                usize::try_from(policy["budget"].as_u64().ok_or("root page budget")?)?)?;
        }
        let initial_cells = runtime.graph.stats.cells_created;''')

    # Negative control: issue only a table id and move its actual expansion into
    # the receiver. The receiver cannot claim an independently named parent.
    edit('src/single_witness.rs','struct Trial{root_memory:', 'struct Trial{pub relocate:bool,root_memory:')
    edit('src/single_witness.rs','Ok(Self{root_memory:', 'Ok(Self{relocate:false,root_memory:')
    edit('src/single_witness.rs','let candidates=if let Some(a)=p.pivot{','let domain=if let Some(a)=p.pivot{')
    edit('src/single_witness.rs',';(if let Some((weights,budget))=self.root_policy',
        ';if self.relocate {SingleDomain::Table(t)} else {SingleDomain::Named((if let Some((weights,budget))=self.root_policy')
    edit('src/single_witness.rs','into_iter().map(Some).collect()\n        }else{vec![None]};',
        'into_iter().map(Some).collect())}\n        }else{SingleDomain::Named(vec![None])};\n        let (candidates,site)=domain.receive(g);')
    edit('src/single_witness.rs','crate::search_work::add(0, usize::from(w.is_some()))',
        'crate::search_work::add(site, usize::from(w.is_some()))')
    with (crate/'src/single_witness.rs').open('a') as out:
        out.write("""
enum SingleDomain { Named(Vec<Option<Dependency>>), Table(usize) }
impl SingleDomain {
    fn receive(self,g:&Graph)->(Vec<Option<Dependency>>,usize){
        match self {
            Self::Named(rows)=>(rows,0),
            Self::Table(table)=>(g.witnesses(table).into_iter().map(Some).collect(),10),
        }
    }
}
""")
    edit('src/runtime.rs','pub fn select_root_pages(', 'pub fn relocate_single(&mut self){self.stage_spine.single.as_mut().unwrap().relocate=true;}\n    pub fn select_root_pages(')
    edit(session,'if let Some(policy)=req.get("root_page_policy") {','if req["relocate_single"]==true {runtime.relocate_single();}\n        if let Some(policy)=req.get("root_page_policy") {')

    # Filters over index fingerprints still inspect candidate identities.
    hit('query.rs',11,'stats.examined += view.len() as u64;', 'view.len()')
    hit('query.rs',11,'*examined += size as u64;', 'size')
    hit('query.rs',11,'.filter(|w| { let hashes = &index.keys[w];', '1')
    hit('free_join.rs',11,'for &row in rows {')
    edit('src/range_index.rs','.filter(|w| survivors.contains(w))',
         '.filter(|w| {crate::search_work::add(11,1); survivors.contains(w)})')
    hit('range_index.rs',11,'for (_, refs) in bucket.range(bounds) {','refs.len()')
    hit('range_index.rs',12,'for w in g.witnesses(table) {')
    hit('query.rs',12,'for fact in graph.witnesses(table) {')
    hit('query.rs',12,'for (&w,keys) in &self.keys {')

    with target.open('a') as out:
        out.write((Path(__file__).parent/'owner.rs').read_text())
    edit('src/ordinary_witness.rs','struct Store {capture_pages:', 'struct Store {owner_routes:OwnerPorts,capture_pages:')
    edit('src/ordinary_witness.rs','let s=Store{capture_pages:', 'let s=Store{owner_routes:HashMap::new(),capture_pages:')
    with target.open('a') as out:
        out.write("""
pub fn use_owner_ports(program:&Program){
    STORE.with_borrow_mut(|store|{let s=store.as_mut().unwrap();s.owner_routes=owner_ports(program,&s.plans);});
}
""")
    edit(session,'if req["capture_pages"]==true', 'if req["owner_ports"]==true {ordinary_witness::use_owner_ports(&program);}\n            if req["capture_pages"]==true')
    edit('src/ordinary_shortlist.rs','let d=&steps[i];','''let d=&steps[i];
        if self.accel==4 && i==1 && steps.len()==2 && !self.owner_routes.is_empty()
            && let Dependency::Fact(first)=path[0] && let Some(cell)=c.graph.cells.get(&first.cell)
            && let Some(op)=self.owner_routes.get(&(cell.template,first.op,self.rule)).copied(){
            let sibling=Dependency::Fact(crate::graph::FactRef{cell:first.cell,op});
            crate::search_work::add(13,1);
            if let Some(version)=c.graph.visible_epoch(sibling){
                path.push(sibling);
                self.emit_stack(c,steps,2,epoch.max(version),path,ports,raw)?;
                path.pop();
            }
            return Ok(())
        }''')
