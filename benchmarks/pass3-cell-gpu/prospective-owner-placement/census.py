"""Instrument the prospective layout's full owner supply and retained heap."""
from pathlib import Path


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(old)
    return text.replace(old, new)


def install(src, driver):
    p = src / "old_pair_graph.rs"
    s = replace(p.read_text(), "skip: &mut usize, accounting:", """skip: &mut usize,
            available:&mut TrialSet<(usize,Vec<(u32,usize)>)>, observed:&mut TrialSet<Vec<(u32,usize)>>, reader_stats:&mut [u64;3],
            accounting:""")
    s = replace(s, "            domain[6] += 1;", """            domain[6] += 1;
            let group=ids.iter().copied().zip(old.iter().map(|x|x.0)).collect::<Vec<_>>();
            available.insert((shape,group.clone()));
            if observed.contains(&group) {continue;}
""")
    s = replace(s, "            let previous = mapping(self);", """            observed.insert(group);
            let previous = mapping(self);""")
    s = replace(s, '        let mut event = JV::Null;', '        let mut event = JV::Null;\n        let mut reader_index=None;')
    s = replace(s, '            let initial = self.existing_owner_read(&ids)?;', """            if reader_index.is_none() {reader_stats[0]+=1; reader_index=Some(self.owner_trial_reader_index()?);}
            if !self.trial_has_reader(&ids,reader_index.as_ref().unwrap())? {
                reader_stats[1]+=1;
                if (component as u64+self.epoch)%251==0 {
                    reader_stats[2]+=1;
                    if !self.external_readers(&ids)?.is_empty() {return Err("negative owner reader filter missed an external reader".into());}
                }
                continue;
            }
            let initial = self.existing_owner_read(&ids)?;""")
    s = replace(s, 'if initial["external_readers"].as_array().unwrap().is_empty() {\n                continue;',
        'if initial["external_readers"].as_array().unwrap().is_empty() {\n                return Err("positive owner reader filter disagrees with full readers".into());')
    p.write_text(s+'\n'+Path(__file__).with_name("readers.rs").read_text())
    s = driver.read_text()
    s = replace(s, '"defer"=>2,_=>', '"defer"=>2,"defer-only"=>3,"multi-prefix"=>4,_=>')
    s = replace(s, '    let mut owner_peak=', '''    let streaming=a.get(8).is_some_and(|v|v=="stream");
    let mut available=std::collections::BTreeSet::new();
    let mut observed=std::collections::BTreeSet::new();
    let mut reader_stats=[0u64;3];
    let mut owner_peak=''')
    s = replace(s,'physical_mode, !action, &seed, weights.as_ref(), cut, &mut skip, accounting',
                'physical_mode, streaming||!action, &[], weights.as_ref(), cut, &mut skip, &mut available, &mut observed, &mut reader_stats, accounting')
    s=replace(s,'                action = true;\n                seed', '                if !action {\n                seed')
    s=replace(s,'                base_unions = e.graph.stats.unions;', '                base_unions = e.graph.stats.unions;\n                }\n                action = true;')
    start=s.index('    fs::write(\n')
    value=s.index('            &json!(',start)
    end=s.index('}),\n',value)
    s=s[:start]+ '    let mut result='+s[value:end+2].strip()[1:]+';\n' + '''    result["distinct"]=json!(available.len());
    result["issued_distinct"]=json!(observed.len());
    result["reader_filter"]=json!(reader_stats);
    let live=LIVE.load(Relaxed);
    drop(e.graph);
    let drop_bytes=live-LIVE.load(Relaxed);
    result["graph_drop_bytes"]=json!(drop_bytes);
    fs::write(&a[2],serde_json::to_vec(&result)?)?;
    Ok(())
}
'''
    anchor = "    let _initial_unions = audit::take_trial_unions();"
    s = replace(s, anchor, anchor + "\n" + Path(__file__).with_name("bench.rs").read_text())
    driver.write_text(s)
    p = src/'shared_owner_transfer.rs'
    s=replace(p.read_text(),'if existing==0 && extendable {','if existing==0 && extendable && mode!=3 && (mode!=4 || ids.len()>1) {')
    s=replace(s,'if mode==2 && !self.cells.completed_owner_has_external_sources',
                'if mode>=2 && !self.cells.completed_owner_has_external_sources')
    p.write_text(s)
