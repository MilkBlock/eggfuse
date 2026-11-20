"""Track the set of rules that can undergo an actual clean-to-dirty transition."""
from pathlib import Path

def change(p,old,new):
    text=p.read_text()
    if text.count(old)!=1:raise RuntimeError((p.name,old,text.count(old)))
    p.write_text(text.replace(old,new))

def install(crate):
    src=crate/'src';p=src/'runtime.rs'
    change(p,'if self.graph.program.rules[rid].seminaive{self.dirty[rid]=false;}','if self.graph.program.rules[rid].seminaive{self.readers_take_dirty(rid);}')
    change(p,'!std::mem::replace(&mut self.dirty[rid], false)','!self.readers_take_dirty(rid)')
    change(p,'p.mode!=0 && p.dedicated[rid]', 'matches!(p.mode,1|2|3|4|5) && p.dedicated[rid]')
    p=src/'strict_publication_readers.rs'
    change(p,'    dirty_transitions: u64,','    dirty_transitions:u64,already_dirty:u64,')
    change(p,'    words: Vec<u64>,','    words:Vec<u64>,clean:Vec<u64>,')
    change(p,'mode > 4','mode > 6')
    s=p.read_text().replace('1 | 3 | 4)', '1 | 3 | 4 | 5)').replace('2 | 3 | 4)', '2 | 3 | 4 | 5)')
    p.write_text(s)
    change(p,'if !dedicated[r] && !self.entry_schedule.accepts(r) {','if (mode==6 || !dedicated[r]) && !self.entry_schedule.accepts(r) {')
    change(p,'        self.notification_readers = Some(ReaderPlan {','''        let mut clean=vec![0;words];
        if mode>=5{for (i,&dirty) in self.dirty.iter().enumerate(){if !dirty{clean[i/64]|=1u64<<(i%64);}}}
        self.notification_readers = Some(ReaderPlan {clean,''')
    change(p,'        let masked = plan.mode == 4;','        let masked = plan.mode>=4;')
    change(p,'                        if plan.dedicated[rid] && !self.entry_schedule.accepts(rid) {','                        if prune && plan.dedicated[rid] && !self.entry_schedule.accepts(rid) {')
    change(p,'                let mut bits = word;','''                let mut bits=if plan.mode>=5{let pending=word & plan.clean[i];plan.clean[i]&=!word;
                    if plan.detailed{plan.stats.already_dirty+=u64::from((word^pending).count_ones());}
                    pending
                }else{word};''')
    # Keep the count of uniquely notified recipients comparable across both bitset variants.
    change(p,'u64::from(bits.count_ones())','u64::from(word.count_ones())')
    with p.open('a') as f:
        f.write('''
impl Executor{
    fn readers_take_dirty(&mut self,rid:usize)->bool{
        if let Some(plan)=self.notification_readers.as_mut().filter(|p|p.mode>=5){
            plan.clean[rid/64]|=1u64<<(rid%64);
        }
        std::mem::replace(&mut self.dirty[rid],false)
    }
    pub fn check_reader_bits(&self)->Result<()>{
        if let Some(plan)=self.notification_readers.as_ref().filter(|p|p.mode>=5 && p.detailed){
            for (rid,&dirty) in self.dirty.iter().enumerate(){
                if dirty==(plan.clean[rid/64]&(1u64<<(rid%64))!=0){return Err("compiled clean bit disagrees with source rule".into());}
            }
        }
        Ok(())
    }
}
''')
    p=crate/'examples/joint_witness_session.rs'
    change(p,'        report["publication_readers"]=','        runtime.check_reader_bits()?;\n        report["publication_readers"]=')

    # Optional profiling only. Timed complexity comparisons keep all stage clocks off.
    p=src/'strict_publication_readers.rs'
    change(p,'    batches: u64,','    batches:u64,meter_ns:[u64;7],')
    change(p,'    detailed: bool,','    detailed:bool,meter:bool,')
    change(p,'            detailed,','            detailed,meter:false,')
    with p.open('a') as f:f.write('''
impl Executor{
    pub fn enable_reader_clock(&mut self,enabled:bool){
        if let Some(p)=self.notification_readers.as_mut(){p.meter=enabled;}
    }
    fn reader_start(&self)->Option<std::time::Instant>{
        self.notification_readers.as_ref().is_some_and(|p|p.meter).then(std::time::Instant::now)
    }
    fn reader_elapsed(&mut self,start:Option<std::time::Instant>,slot:usize){
        if let Some(s)=start{self.notification_readers.as_mut().unwrap().stats.meter_ns[slot]+=s.elapsed().as_nanos() as u64;}
    }
}
''')
    p=src/'runtime_completion.rs'
    change(p,'        if let Some(ready) = ready {\n            self.stage_spine.publish_selected(', '        let meter=self.reader_start();\n        if let Some(ready) = ready {\n            self.stage_spine.publish_selected(')
    change(p,'        #[cfg(feature = "structural-depth")]\n        self.stage_spine.structural.publish', '        self.reader_elapsed(meter,0);\n        #[cfg(feature = "structural-depth")]\n        self.stage_spine.structural.publish')
    change(p,'        #[cfg(feature = "view-consumers")]\n        self.entry_schedule\n', '        let meter=self.reader_start();\n        #[cfg(feature = "view-consumers")]\n        self.entry_schedule\n')
    change(p,'        let matched = self.completion.as_ref().is_some_and(|s| s.matched);\n        if !matched && self.stage_spine.pending_publication_counts().0 == 0 {',
        '        self.reader_elapsed(meter,1);\n        let matched = self.completion.as_ref().is_some_and(|s| s.matched);\n        if !matched && self.stage_spine.pending_publication_counts().0 == 0 {')
    change(p,'        crate::ordinary_witness::changed_frame_rows(&self.graph);','        let meter=self.reader_start();\n        crate::ordinary_witness::changed_frame_rows(&self.graph);\n        self.reader_elapsed(meter,2);\n        let meter=self.reader_start();')
    change(p,'        self.sieve.publish(&mut self.query_indexes);','        self.sieve.publish(&mut self.query_indexes);\n        self.reader_elapsed(meter,3);')
    change(p,'        self.deliver();','        let meter=self.reader_start();\n        self.deliver();\n        self.reader_elapsed(meter,4);')
    change(p,'        self.graph.changes.clear();\n        if !matched {','        let meter=self.reader_start();\n        self.graph.changes.clear();\n        self.reader_elapsed(meter,5);\n        let meter=self.reader_start();\n        if !matched {')
    change(p,'        let end = Instant::now();\n        let delivery_seconds', '        self.reader_elapsed(meter,6);\n        let end = Instant::now();\n        let delivery_seconds')
    p=crate/'examples/joint_witness_session.rs'
    change(p,'        let initial_cells =','        runtime.enable_reader_clock(req["reader_clock"]==true);\n        let initial_cells =')
    p=src/'graph.rs'
    with p.open('a') as f:f.write('''
impl Graph{
    pub(crate) fn equality_subscription_inventory(&self)->serde_json::Value{
        let mut empty=0usize;let mut retired=0usize;let mut scalar_only=0usize;let mut edges=0usize;
        for (&d,refs) in &self.dependencies{
            edges+=refs.len();
            if refs.is_empty(){
                empty+=1;
                match self.live_table(d){
                    None=>retired+=1,
                    Some(t) if self.program.tables[t].schema.iter().all(|v|matches!(v["kind"].as_str(),Some("Unit"|"i64"|"f64"|"String"|"bool")))=>scalar_only+=1,
                    _=>()
                }
            }
        }
        serde_json::json!({"row_records":self.dependencies.len(),"empty_records":empty,
            "empty_retired":retired,"empty_scalar_only":scalar_only,"dependency_edges":edges,
            "eclass_buckets":self.uses.len(),"subscription_calls":self.maintenance.subscription_calls,
            "value_visits":self.maintenance.subscription_value_visits})
    }
}
''')
    p=src/'strict_publication_readers.rs'
    change(p,'"publication":self.publication,','"equality":self.notification_readers.as_ref().filter(|p|p.detailed).map(|_|self.graph.equality_subscription_inventory()),"publication":self.publication,')

    # Count *real* duplicate insertions from one change batch into already-hot native Entry nodes.
    # It is an audit, not a speculative omission of any of those consumers.
    p=src/'entry_schedule.rs'
    anchor='    pub(crate) fn reader_fanout(&self)->Vec<usize>{'
    change(p,anchor,'''    pub(crate) fn hot_publication_overlap(&self,g:&Graph)->(Vec<(usize,[u64;5])>,u64){
        let mut tables=Vec::new();let mut peak=0;
        if !self.enabled{return (tables,peak);}
        for (table,changes) in g.changes.tables(){
            #[cfg(feature="sparse-cells")] if self.publication_nodes[table].is_some(){continue;}
            let hot:Vec<_>=self.plan.tables[table].iter().map(|&i|&self.states[i]).filter(|s|!s.cold).collect();
            if hot.is_empty(){continue;}
            peak=peak.max(hot.len() as u64);
            let mut stats=[changes.len() as u64,changes.len() as u64*hot.len() as u64,0,0,0];
            for w in changes.keys(){
                let count=hot.iter().filter(|s|!s.pending.contains(w)).count() as u64;
                stats[2]+=count;stats[3]+=u64::from(count!=0);stats[4]+=count.saturating_sub(1);
            }
            tables.push((table,stats));
        }
        (tables,peak)
    }
'''+anchor)
    p=src/'strict_publication_readers.rs'
    change(p,'    batches:u64,meter_ns:[u64;7],','    batches:u64,meter_ns:[u64;7],hot_by_table:std::collections::BTreeMap<usize,[u64;5]>,hot_totals:[u64;5],peak_hot_siblings:u64,')
    with p.open('a') as f:f.write('''
impl Executor{
    fn observe_hot_entry_overlap(&mut self){
        let Some(p)=self.notification_readers.as_mut().filter(|p|p.detailed)else{return};
        let (observations,peak)=self.entry_schedule.hot_publication_overlap(&self.graph);
        p.stats.peak_hot_siblings=p.stats.peak_hot_siblings.max(peak);
        for (table,v) in observations{
            let entry=p.stats.hot_by_table.entry(table).or_default();
            for i in 0..5{entry[i]+=v[i];p.stats.hot_totals[i]+=v[i];}
        }
    }
}
''')
    p=src/'runtime_completion.rs'
    change(p,'        let meter=self.reader_start();\n        #[cfg(feature = "view-consumers")]\n        self.entry_schedule','        self.observe_hot_entry_overlap();\n        let meter=self.reader_start();\n        #[cfg(feature = "view-consumers")]\n        self.entry_schedule')
    p=src/'runtime_completion.rs'
    change(p,'        self.reader_elapsed(meter,4);','        self.reader_elapsed(meter,4);\n        self.check_reader_bits()?;')
    p=src/'stage_spine.rs'
    with p.open('a') as f:f.write('''
impl Programs{
    pub(crate) fn publication_reader_counts(&self)->serde_json::Value{
        let s=&self.stats;
        serde_json::json!({"legacy_retirement_checks":s.legacy_retirement_checks,
        "captured_anchors":s.captured_anchors,"distinct_anchor_keys":s.distinct_anchor_keys,
        "anchor_publications":s.anchor_publications,"anchors_retired":s.anchors_retired,
        "context_fact_publications":s.context_fact_publications,"completed_steps":s.completed_steps,
        "pre_resume_port_lookups":s.pre_resume_port_lookups,"publication_seconds":s.publication_seconds})
    }
}
''')
    p=src/'strict_publication_readers.rs'
    change(p,'"publication":self.publication,','"spine":self.stage_spine.publication_reader_counts(),"publication":self.publication,')
