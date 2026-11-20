from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'expected one hook at {old[:80]}')
    return text.replace(old, new)


def install(crate):
    p = crate / 'src/ordinary_witness.rs'
    s = p.read_text()
    s = replace(s, 'struct Store {', 'struct Store {transactions:Transactions,')
    s = replace(s, 'let s=Store{', 'let s=Store{transactions:Transactions::default(),')
    s = replace(s, '"sealed_before_verifier":s.seal,', '"transactions":s.transactions.stats,"request_digest":s.transactions.digest(),"sealed_before_verifier":s.seal,')
    s = replace(s, '            for parents in raw{', '''            let batch = s.transactions.width_for(rid);
            let mut pending = Vec::new();
            let mut request_cache:Vec<AnswerMap>=Vec::new();
            let mut parent_rows = rustc_hash::FxHashMap::<Dependency,Option<Row>>::default();
            let reuse_parents = batch > 1 && s.transactions.parent_reads;
            for (serial, parents) in raw.into_iter().enumerate(){
                if batch > 0 && serial % batch == 0 {
                    if !pending.is_empty(){s.flush_requests(&c,&mut pending,&mut request_cache,&mut out)?;}
                    for answers in &mut request_cache{answers.clear();}
                    parent_rows.clear();
                    s.transactions.stats.raw_batches += 1;
                }''')
    s = replace(s, 'let Some(row)=g.row(address)? else{ok=false;break};', '''let temporary;
                    let row = if reuse_parents {
                        use std::collections::hash_map::Entry;
                        match parent_rows.entry(address) {
                            Entry::Occupied(e) => {s.transactions.stats.reused_parents += 1; e.into_mut().as_ref()}
                            Entry::Vacant(e) => {s.transactions.stats.parent_reads += 1; e.insert(g.row(address)?).as_ref()}
                        }
                    }else{
                        if batch > 0 {s.transactions.stats.parent_reads += 1;}
                        temporary = g.row(address)?;
                        temporary.as_ref()
                    };
                    let Some(row) = row else{ok=false;break};''')
    for expression, receipt, kind in (
        ('c.graph.lookup(*t,&operands)?','AnswerReceipt::read(reply.as_ref())','row'),
        ('c.graph.primitive(name,&operands,result)?','AnswerReceipt::Scalar(reply.as_ref())','v'),
    ):
        old = f'if let Some({kind})={expression} &&'
        new = f'''let reply={expression};
                    if self.transactions.audit && self.transactions.eligible.get(self.rule)==Some(&true) && !c.sealing{{
                        self.transactions.record(self.rule,id,request_input(self.run,c,&p,&operands),{receipt});
                    }}
                    if let Some({kind})=reply &&'''
        s=replace(s,old,new)
    # All parent streams have already been sealed. No probe below can add a parent.
    s = replace(s, '''                s.descend(&c,c.pick_count,exact,&mut out,&mut no_more)?;
            }
            debug_assert!(no_more.is_empty())''', '''                if batch > 0 {
                    if pending.is_empty() && s.transactions.profile{s.transactions.opened=Some(std::time::Instant::now());}
                    pending.push(exact);
                    if s.transactions.streaming{s.flush_requests(&c,&mut pending,&mut request_cache,&mut out)?;}
                }else{s.descend(&c,c.pick_count,exact,&mut out,&mut no_more)?;}
            }
            if !pending.is_empty(){s.flush_requests(&c,&mut pending,&mut request_cache,&mut out)?;}
            debug_assert!(no_more.is_empty())''')
    p.write_text(s+'\ninclude!("request_transactions.rs");\n')
    shutil.copyfile(HERE / 'requests.rs', crate / 'src/request_transactions.rs')
    driver = crate / 'examples/joint_witness_session.rs'
    marker = '        let initial_cells = runtime.graph.stats.cells_created;'
    driver.write_text(replace(driver.read_text(), marker, '''        if let Some(n)=req["request_batch"].as_u64(){
            ordinary_witness::configure_transactions(&program,n,req["share_requests"].as_bool().unwrap_or(false),req["share_parents"].as_bool().unwrap_or(false),req["tables_only"].as_bool().unwrap_or(false),req["stream_requests"].as_bool().unwrap_or(false),req["request_profile"].as_bool().unwrap_or(false))?;
        }
'''+marker))
