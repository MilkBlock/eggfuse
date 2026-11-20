"""Compile one proof check per distinct projected source and one ordered slot-vector transfer."""
from pathlib import Path

def install(crate):
    src=crate/'src'
    path=src/'joint_root.rs'
    def replace(before,after):
        text=path.read_text()
        if text.count(before)!=1:raise ValueError((path.name,before[:72],text.count(before)))
        path.write_text(text.replace(before,after))
    replace('struct Layout{rid:usize,template:usize,fields:Vec<Field>}', 'struct Layout{rid:usize,template:usize,fields:Vec<Field>,checked_atoms:Vec<(usize,usize)>,sorted_slots:Vec<usize>}')
    replace('layout.push(Rc::new(Layout{rid,template:rule.template,fields}));','''let mut checked_atoms:Vec<_>=fields.iter().filter_map(|f|f.kind.map(|t|(f.atom,t))).collect();
        checked_atoms.sort_unstable();checked_atoms.dedup();
        let mut sorted_slots:Vec<_>=rule.inputs.iter().copied().collect();sorted_slots.sort_unstable();
        layout.push(Rc::new(Layout{rid,template:rule.template,fields,checked_atoms,sorted_slots}));''')
    replace('struct State{encoding:Encoding,','struct State{grouped:bool,projection_fault:bool,whole:u64,grouped_headers:u64,ordered_commits:u64,encoding:Encoding,')
    replace('Some(State{encoding:c.encoding','Some(State{grouped:false,projection_fault:false,whole:0,grouped_headers:0,ordered_commits:0,encoding:c.encoding')
    replace('pub(crate) fn issue(origin:', '''pub fn grouped_root_projection(fault:bool){
        STATE.with_borrow_mut(|s|if let Some(st)=s{st.grouped=true;st.projection_fault=fault;});
    }
    pub(crate) fn issue(origin:''')
    replace('enum BoundValues { Retained(Slots), TakeOnce(RefCell<Option<Slots>>) }', 'enum BoundValues { Retained(Slots), TakeOnce(RefCell<Option<Slots>>),Whole(RefCell<Option<Slots>>) }')
    replace('Self::TakeOnce(values)=>values.borrow_mut()', 'Self::TakeOnce(values)|Self::Whole(values)=>values.borrow_mut()')
    replace('let share_checked=STATE.with_borrow(|s|s.as_ref().is_some_and(|state|matches!(state.encoding,Encoding::CheckedSlots)));','''let (share_checked,grouped)=STATE.with_borrow(|s|s.as_ref().map_or((false,false),|st|(matches!(st.encoding,Encoding::CheckedSlots),st.grouped)));''')
    replace('        let mut checks=0;', '        let mut checked:u64=0;let mut checks=0;')
    replace('            checks+=1;\n        }\n        let mut values=Slots::default();','''            if grouped && reference.atom<u64::BITS as usize {checked|=1u64<<reference.atom;}
            checks+=1;
        }
        if grouped && verified.len()==recipe.layout.sorted_slots.len()
            && verified.keys().eq(recipe.layout.sorted_slots.iter()){
            // The checked matcher already produced the complete canonical slot map. Its
            // value vector remains the sole owned payload delivered by the winning recipe.
            for &(atom,table) in &recipe.layout.checked_atoms {
                if atom<u64::BITS as usize && (checked & (1u64<<atom))!=0{continue;}
                let Some(address)=known.get(atom).and_then(|w|*w) else{return rejected();};
                if g.live_table(address)!=Some(table)||g.visible_epoch(address).is_none(){return rejected();}
                checks+=1;
            }
            STATE.with_borrow_mut(|s|{let st=s.as_mut().unwrap();st.whole+=1;st.sealed+=1;
                st.header_checks+=checks;st.grouped_headers+=checks;});
            return Ok(Some(Rc::new(Bound{recipe,values:BoundValues::Whole(RefCell::new(Some(verified.clone())))})));
        }
        let mut values=Slots::default();''')
    replace('let values=bound.values.deliver()?;\n        if r.run!=epoch', '''let mut values=bound.values.deliver()?;
        if state.projection_fault && let Some(field)=r.layout.fields.first(){
            state.projection_fault=false;
            values.remove(&field.slot);
        }
        let whole=matches!(bound.values,BoundValues::Whole(_)) && values.len()==inputs.len();
        let mismatch=if whole{state.ordered_commits+=1;*inputs!=values}else{
            r.layout.fields.iter().any(|f|inputs.get(&f.slot)!=values.get(&f.slot))
        };
        if r.run!=epoch''')
    replace('r.template!=source_template||r.layout.fields.iter().any(|f|inputs.get(&f.slot)!=values.get(&f.slot))','r.template!=source_template||mismatch')
    replace('json!({"root_row_decodes":s.decodes','json!({"whole_projections":s.whole,"grouped_header_checks":s.grouped_headers,"whole_commits":s.ordered_commits,"root_row_decodes":s.decodes')
    driver=crate/'examples/joint_witness_session.rs'
    s=driver.read_text();anchor='        let initial_cells = runtime.graph.stats.cells_created;'
    assert s.count(anchor)==1
    driver.write_text(s.replace(anchor,'        if req["grouped_root"]==true{eggfuse_cell_runtime::joint_root::grouped_root_projection(req["root_projection_fault"]==true);}\n'+anchor))
