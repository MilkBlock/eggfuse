from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def rep(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)


def install(crate):
    src=crate/'src';p=src/'lib.rs';p.write_text(p.read_text()+'\npub mod receipt_tape;\n')
    copyfile(HERE/'tape.rs',src/'receipt_tape.rs')
    p=src/'single_witness.rs';s=p.read_text()
    s=rep(s,'let (offers,delivered,score_sum,n)=if self.rows.active {','''let replay=crate::receipt_tape::singles((g.epoch,rid,wm))?;
        let (offers,delivered,score_sum,n)=if let Some((bank,only))=replay {
            self.replay_single(g,rid,&p,&bank,only)?
        }else if self.rows.active {''')
    anchor='};self.work[0]+=n as u64;'
    s=rep(s,anchor,'''};if crate::receipt_tape::capturing(){
            let rows=offers.iter().map(|(t,f,send)|crate::receipt_tape::SingleRef{
                id:t.id,w:t.w,epoch:t.version,initial:t.initial,score:t.score,guarded:t.guarded,features:*f,send:*send}).collect();
            crate::receipt_tape::save_single((g.epoch,rid,wm),rows,delivered,score_sum,n);
        }self.work[0]+=n as u64;''')
    s=rep(s,'        for (token,f,send) in offers{','        for (mut token,f,send) in offers{')
    a='            let matched=if self.rows.verify.mode==0'
    s=rep(s,a,'''            let fault=token.w.is_some() && crate::receipt_tape::version_fault();
            if fault {token.version=token.version.wrapping_add(1);}
'''+a)
    a='            if self.mode=="capture"{\n                let next=self.dict.len();'
    s=rep(s,a,'''            if fault {return Err(if matched.is_none() {"oracle source version rejected"}else{"invalid version passed source verifier"}.into());}
'''+a)
    s=rep(s,'            if let Some(mut binding)=matched{','            if let Some(mut binding)=matched{\n                if send{crate::receipt_tape::single_success(token.id);}')
    p.write_text(s+'\ninclude!("oracle_single.rs");\n');copyfile(HERE/'single.rs',src/'oracle_single.rs')
    p=src/'ordinary_witness.rs';s=p.read_text()
    anchor='        let mut remaining=vec![0;ins.len()+1];'
    s=rep(s,anchor,'        let replay=crate::receipt_tape::multis((g.epoch,rid,mark))?;\n'+anchor)
    s=rep(s,'remaining[i]=remaining[i].max(s.frame(g,t)?.max_epoch);','remaining[i]=if replay.is_some(){u64::MAX}else{remaining[i].max(s.frame(g,t)?.max_epoch)};')
    a='let mut out=vec![];let mut raw=vec![];if s.accel>=4{'
    s=rep(s,a,'''let mut out=vec![];let mut raw=vec![];if let Some((bank,only))=&replay{
            if !s.page || s.residual || s.cap!=usize::MAX {return Err("oracle requires complete sealed multi pages".into())}
            let width=c.pick_count;
            if *only {
                let count=bank.yes.len()/width;
                let page=if s.page_tuples==0{usize::MAX}else{s.page_tuples.saturating_mul(width)};
                for chunk in bank.yes.chunks(page){
                    s.pending_pages.push(chunk.to_vec());
                }
                s.counts.raw_tuples+=count as u64;
            }else{
                for refs in &bank.all{s.counts.raw_tuples+=(refs.len()/width) as u64;s.pending_pages.push(refs.clone());}
            }
            for page in &s.pending_pages {
                s.counts.raw_root_slots+=page.len() as u64;
                if s.detailed {
                    for tuple in page.chunks_exact(width) {
                        s.raw_digest.update((run as u64).to_le_bytes());s.raw_digest.update((rid as u64).to_le_bytes());
                        s.raw_digest.update((width as u64).to_le_bytes());
                        for parent in tuple {
                            s.raw_digest.update((parent.atom as u64).to_le_bytes());
                            match parent.row {Dependency::Fact(f)=>{s.raw_digest.update([1]);s.raw_digest.update(f.cell.to_le_bytes());s.raw_digest.update(f.op.to_le_bytes());},
                                Dependency::Function(k)=>{s.raw_digest.update([2]);s.raw_digest.update((k as u64).to_le_bytes());}}
                        }
                    }
                }
            }
        }else if s.accel>=4{''')
    s=rep(s,'                s.verify_flat(&c,&p,&mut out)?;','                if replay.is_none(){s.verify_flat(&c,&p,&mut out)?;}')
    a='                    let page=crate::joint_root::multi_page(g.epoch,rid,c.pick_count,refs,s.page_fault)?;'
    s=rep(s,a,'                    crate::receipt_tape::multi_page(&refs);\n'+a)
    a='                    s.descend(&c,c.pick_count,exact,&mut out,&mut no_more)?;'
    s=rep(s,a,'                    let before=out.len();\n'+a+'\n                    if out.len()>before {crate::receipt_tape::multi_success(&parents);}')
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';s=p.read_text();a='        let initial_cells = runtime.graph.stats.cells_created;'
    s=rep(s,a,'        eggfuse_cell_runtime::receipt_tape::begin(req["receipt_oracle"].as_str().unwrap_or("live"))?;\n'+a)
    a='        let profile_work = req.get("cpu_profile").map'
    s=rep(s,a,'''        let oracle=eggfuse_cell_runtime::receipt_tape::finish()?;
        let multi=report["multi"]["neural_committed"].as_u64().unwrap_or(0);
        let total=report["multi"]["total_rhs"].as_u64().unwrap_or(0);
        let online=(if oracle["multi_replayed"]==true {0}else{multi})+(if oracle["single_replayed"]==true{0}else{total-multi});
        if oracle["multi_replayed"]==true {report["multi"]["neural_committed"]=json!(0);report["multi"]["generator"]=json!("oracle-replay");}
        if oracle["single_replayed"]==true {report["single"]["mode"]=json!("oracle-replay");}
        report["receipt_oracle"]=oracle;
        report["online_neural_rhs"]=json!(online);
'''+a)
    p.write_text(s)
