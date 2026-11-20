from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent

def change(s, old, new):
    if s.count(old) != 1:
        raise ValueError(old)
    return s.replace(old, new)

def install(crate):
    src = crate/'src'
    shutil.copy2(HERE/'transfer.rs', src/'verified_transfer.rs')
    with (src/'lib.rs').open('a') as f:
        f.write('\npub mod verified_transfer;\n')
    p = crate/'examples/joint_witness_session.rs'
    s = p.read_text()
    marker = '        let initial_cells = runtime.graph.stats.cells_created;'
    s = change(s, marker, '''        eggfuse_cell_runtime::verified_transfer::configure(req["verified_transfer"].as_u64().unwrap_or(0),audit)?;
'''+marker)
    marker = '        report["header_view"]='
    p.write_text(change(s, marker, '''        report["verified_transfer"]=eggfuse_cell_runtime::verified_transfer::report();
'''+marker))

    p = src/'cell_match.rs'
    s = p.read_text()
    marker = '    pub(crate) fn neural(&self)'
    p.write_text(change(s, marker, '''    pub(crate) fn take_neural(&mut self) -> Option<crate::single_witness::Mark> {
        if !matches!(self,Self::Neural(..)) {return None;}
        let Self::Neural(base,mark)=std::mem::take(self) else {unreachable!()};
        *self=*base;
        Some(mark)
    }
'''+marker))
    p = src/'runtime.rs'
    s = p.read_text()
    old = 'row.known=match row.known.neural(){Some(mark)=>known.tagged(mark.clone()),None=>known};'
    s = change(s,old,'''let mark = if crate::verified_transfer::move_mark(){
                    let mark=row.known.take_neural();
                    if mark.is_some(){crate::verified_transfer::moved(false);}
                    mark
                } else {row.known.neural().cloned()};
                row.known=match mark{Some(mark)=>known.tagged(mark),None=>known};''')
    old = 'if let Some(s)=self.stage_spine.single.as_mut(){s.winner=b.known.neural().cloned();}'
    s = change(s,old,'''// Read the immutable token and recipe before moving the mark to its winner.
        let single_id=b.known.neural().map(|m|m.sealed_token_id());
        let single_root=b.known.neural().and_then(|m|m.root_recipe.clone());
        if let Some(s)=self.stage_spine.single.as_mut(){
            s.winner=if crate::verified_transfer::move_mark(){
                let mark=b.known.take_neural();
                if mark.is_some(){crate::verified_transfer::moved(true);}
                mark
            }else{b.known.neural().cloned()};
        }''')
    s=change(s,'self.graph.epoch,b.known.neural().map(|m|m.sealed_token_id()),b.ordinary_id','self.graph.epoch,single_id,b.ordinary_id')
    s=change(s,'let recipe=b.known.neural().and_then(|m|m.root_recipe.clone()).or_else','let recipe=single_root.or_else')
    p.write_text(s)

    p=src/'joint_root.rs'
    s=p.read_text()
    marker='impl BoundValues {'
    p.write_text(change(s,marker,'''impl Bound {
    pub(crate) fn has_checked_slots(&self)->bool { matches!(self.values,BoundValues::TakeOnce(_)) }
    pub(crate) fn agrees(&self, slots:&Slots, required:&[usize])->bool {
        let BoundValues::TakeOnce(cell)=&self.values else{return false;};
        let owned=cell.borrow();
        owned.as_ref().is_some_and(|proof| required.iter().all(|k|
            proof.get(k).is_some_and(|expected|slots.get(k)==Some(expected))))
    }
}
'''+marker))
    p=src/'single_witness.rs'
    s=p.read_text()
    s=change(s,'token:Token,values:Vec<Value>,witnesses:', 'token:Token,values:Option<Vec<Value>>,witnesses:')
    s=change(s,'                    let values=r.inputs.iter().map(|s|binding.values[s].clone()).collect();\n','')
    marker='                    binding.known=binding.known.tagged'
    s=change(s,marker,'''                    let values=if crate::verified_transfer::reuse_receipt() &&
                        root_recipe.as_ref().is_some_and(|b|b.has_checked_slots()){
                        crate::verified_transfer::receipt(r.inputs.len());
                        if crate::verified_transfer::try_corruption() && !r.inputs.is_empty(){
                            let mut broken=binding.values.clone();
                            broken.remove(&r.inputs[0]);
                            assert!(!root_recipe.as_ref().unwrap().agrees(&broken,&r.inputs));
                            crate::verified_transfer::corrupted();
                        }
                        None
                    }else{Some(r.inputs.iter().map(|s|binding.values[s].clone()).collect())};
'''+marker)
    old='assert!(p.rules[rid].inputs.iter().map(|s|&values[s]).eq(mark.values.iter()));'
    s=change(s,old,'''match mark.values {
                Some(original) => assert!(p.rules[rid].inputs.iter().map(|s|&values[s]).eq(original.iter())),
                None => assert!(mark.root_recipe.as_ref().is_some_and(|b|b.agrees(values,&p.rules[rid].inputs))),
            }''')
    p.write_text(s)

    p=src/'ordinary_witness.rs'
    s=p.read_text()
    s=change(s,'    tickets:Vec<Ticket>,wins:', '    retired:usize,peak_tickets:usize,tickets:Vec<Ticket>,wins:')
    s=change(s,'        tickets:vec![],wins:', '        retired:0,peak_tickets:0,tickets:vec![],wins:')
    marker='        let rule=&g.program.rules[rid];\n        let plan=s.plans[rid]'
    s=change(s,marker,'''        // A source Run collects all proposals, commits its sorted winners, and then advances.
        // All persistent descendants name the absolute serial, never the old local array index.
        if crate::verified_transfer::run_tickets() && s.run!=run {
            s.retired+=s.tickets.len();
            s.tickets.clear();
        }
'''+marker)
    s=change(s,'local_token_id:self.tickets.len()+1','local_token_id:self.retired+self.tickets.len()+1')
    s=change(s,'b.ordinary_id=self.tickets.len();','self.peak_tickets=self.peak_tickets.max(self.tickets.len());b.ordinary_id=self.retired+self.tickets.len();')
    s=s.replace('s.tickets[id-1]', 's.tickets[id.checked_sub(s.retired+1).expect("retired source ticket at commit")]')
    s=change(s,'s.tickets.get(id-1)', 's.tickets.get(id.checked_sub(s.retired+1).expect("retired source ticket at allocation"))')
    s=change(s,'json!({"pages":s.pages', 'json!({"ticket_peak":s.peak_tickets,"ticket_retired":s.retired,"pages":s.pages')
    p.write_text(s)
