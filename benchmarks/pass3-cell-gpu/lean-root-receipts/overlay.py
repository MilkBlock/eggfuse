from pathlib import Path
from shutil import copyfile

HERE=Path(__file__).resolve().parent


def change(text, old, new):
    if text.count(old)!=1:
        raise ValueError(old)
    return text.replace(old,new)


def install(crate):
    src=crate/'src'
    p=src/'joint_root.rs'
    s=change(p.read_text(),'struct State{','struct State{lean:u8, lean_stats:LeanRootStats,')
    s=change(s,'enum Body {','enum Body {Typed(TypedPage,usize),')
    s=change(s,'        Body::RowPage(page,slot)=>return page.decode(*slot),',
             '        Body::Typed(page,slot)=>return page.decode(*slot),\n        Body::RowPage(page,slot)=>return page.decode(*slot),')
    s=change(s,'Some(State{encoding:', 'Some(State{lean:0,lean_stats:LeanRootStats::default(),encoding:')
    s=change(s,'"raw_hash":s.raw.to_string()', '"lean":s.lean_stats,"raw_hash":s.record_fingerprint().then(||s.raw.to_string())')
    a=s.index('        for word in [state.serial,run,rid as u64,layout.template')
    b=s.index('        if state.mode=="withhold"',a)
    s=s[:a]+"        if state.record_fingerprint(){\n"+s[a:b]+"        }else{state.lean_stats.raw_omitted+=1;}\n"+s[b:]
    anchor='    let rejected=||'
    s=change(s,anchor,'''    if borrowed_page(&packet) {
        return bind_page(&packet,g,rid,|a|known.get(a).copied().flatten(),verified);
    }
'''+anchor)
    s=change(s,'    let deps:Vec<_>=','''    if let Some(packet)=&input && borrowed_page(packet) {
        return bind_page(packet,g,rid,|a|known.receipt(a),verified);
    }
    let deps:Vec<_>=''')
    p.write_text(s+'\ninclude!("lean_root_receipts.rs");\n')
    copyfile(HERE/'lean.rs',src/'lean_root_receipts.rs')

    p=src/'adaptive_root_page.rs'
    original=p.read_text()
    start=original.index('    fn decode(&self, slot: usize)')
    end=original.index('\n}',start)
    # Keep the old decoder untouched for the paired reference arm.
    s=original[start:end].replace('fn decode(&self, slot: usize) -> Option<Decoded>',
                                  'fn decode_head(&self, slot: usize) -> Option<(Decoded, Option<Ref>)>')
    s=change(s,'            0 => vec![],','            0 => None,')
    s=change(s,'                vec![Ref {','                Some(Ref {')
    s=change(s,'                }]','                })')
    s=change(s,'        Some(Decoded {','        Some((Decoded {')
    s=change(s,'            refs,\n            ports: None,\n        })','            refs: vec![],\n            ports: None,\n        },refs))')
    s=original[:end]+'\n'+s+original[end:]
    a=s.index('            for word in [');b=s.index('            let mut v = version;',a)
    s=s[:a]+'            if state.record_fingerprint(){\n'+s[a:b]+'            }else{state.lean_stats.raw_omitted+=1;}\n'+s[b:]
    p.write_text(s)
    p=src/'multi_root_pages.rs'
    s=p.read_text();a=s.index('        for entry in refs.chunks_exact(width)');b=s.index('        st.emitted[1]',a)
    p.write_text(s[:a]+'        if st.record_fingerprint(){\n'+s[a:b]+'''        }else{
            st.serial=st.serial.checked_add(count as u64).ok_or("root serial overflow")?;
            st.lean_stats.raw_omitted+=count as u64;
        }
'''+s[b:])
    p=src/'adaptive_rows.rs'
    anchor='                if let Some(page) = crate::joint_root::single_page(g.epoch, rid, p.pivot, &frozen) {'
    p.write_text(change(p.read_text(),anchor,'''                if crate::joint_root::use_typed_page(){
                    if let Some(page)=crate::joint_root::typed_page(g.epoch,rid,p.pivot,frozen){
                        for (i,(t,_,_)) in shard.iter_mut().filter(|(_,_,send)|*send).enumerate(){
                            t.recipe=Some(page.at(i));
                        }
                    }
                }else '''+anchor.strip()))
    p=src/'graph.rs'
    anchor="    pub(crate) fn visible_epoch(&self, w: Dependency) -> Option<u64> {"
    p.write_text(change(p.read_text(),anchor,'''    pub(crate) fn receipt_header(&self,w:Dependency)->Option<(usize,u64)> {
        match w {
            Dependency::Function(i)=>self.functions.get(i).filter(|r|r.live).map(|r|(r.table,r.epoch)),
            Dependency::Fact(f)=>{
                let cell=self.cells.get(&f.cell)?;
                let state=cell.facts.get(&f.op).filter(|r|!r.hidden)?;
                match self.program.templates[cell.template].ops.get(f.op as usize)? {
                    Op::Let(_,Call::Table(t),_) | Op::Set(t,_,_)=>Some((*t,state.epoch)),
                    _=>None,
                }
            }
        }
    }
'''+anchor))
    p=crate/'examples/joint_witness_session.rs'
    anchor='        if let Some(file)=req["baked_codes"].as_str(){'
    p.write_text(change(p.read_text(),anchor,'''        if let Some(bits)=req["lean_root"].as_u64() {
            eggfuse_cell_runtime::joint_root::configure_lean_root(bits)?;
        }
'''+anchor))
