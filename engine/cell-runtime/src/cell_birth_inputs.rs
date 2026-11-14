//! Compile the external slot demands of a terminal constructor continuation.
//! Runtime capture extends the original instance, never a second binding array.
use super::*;

#[derive(Clone,Copy,Debug,PartialEq,Eq,Hash)]
struct Demand {slot:usize,available:usize}
#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
struct Span {start:usize,constructors:usize,end:usize}
#[derive(Clone,Debug,Default,PartialEq,Eq)]
pub(super) struct CapturePlan {spans:Vec<Option<Span>>,slots:Vec<Demand>}
impl CapturePlan {
    pub(super) fn derive(steps:&[Step],units:Option<&units::Tail>,defs:&BTreeMap<usize,usize>,queued:bool,
        eligible:impl Fn(usize)->bool)->Self {
        if !queued {return Self::default();}
        let mut result=Self {spans:vec![None;steps.len()],slots:Vec::new()};
        let mut layouts=HashMap::default();
        let last=steps.last().unwrap().region;
        // Admission already requires a root, isolated tail or dependent cone.
        // Ineligible starts must not materialize quadratic suffix layouts.
        for (from,first) in steps.iter().enumerate().filter(|(i,s)|s.region==last && eligible(*i)) {
            let mut demands=Vec::new();let mut seen=BTreeSet::new();
            let mut add=|arg:&Arg| {
                let Arg::Slot(slot)=arg else {return false;};
                let available=defs.get(slot).map_or(0,|op|op+1);
                if available<=first.operation && seen.insert(*slot) {
                    demands.push(Demand {slot:*slot,available});
                    return true;
                }
                false
            };
            let mut constructors=0;
            for arg in steps[from..].iter().flat_map(|s|&s.keys) {constructors+=usize::from(add(arg));}
            // Preserve first-use order, including Unit-only operands after
            // all constructor operands. A shorter capture never reads them.
            for arg in units.into_iter().flat_map(|u|&u.sites).flat_map(|s|&s.keys) {add(arg);}
            let key=(demands,constructors);
            let span=if let Some(&span)=layouts.get(&key) {span} else {
                let start=result.slots.len();result.slots.extend_from_slice(&key.0);
                let span=Span {start,constructors:start+constructors,end:result.slots.len()};
                layouts.insert(key,span);span
            };
            result.spans[from]=Some(span);
        }
        result
    }
    pub(super) fn storage_bytes(&self)->usize {
        self.spans.capacity()*std::mem::size_of::<Option<Span>>()+self.slots.capacity()*std::mem::size_of::<Demand>()
    }
}
impl Graph {
    pub(super) fn capture_worker_inputs(&mut self,cell:u32,plan:&CapturePlan,from:usize,first:usize,
        units:bool,counts:&mut Counts)->Result<()> {
        let span=plan.spans[from].expect("compiled worker input boundary");counts.capture_layout_reads+=1;
        for demand in &plan.slots[span.start..if units {span.end}else{span.constructors}] {
            counts.capture_slot_checks+=1;
            // A local prefix may already own results before this entry. Keep
            // those in its existing fact slots rather than capturing them.
            if demand.available>first || self.rhs_frame(cell).unwrap().values.contains_key(&demand.slot) {continue;}
            let value=self.slot(cell,demand.slot)?;
            counts.captured_reads+=1;counts.captured_writes+=1;
            let values=&mut self.rhs_frame_mut(cell).unwrap().values;
            let before=values.capacity_bytes();values.insert(demand.slot,value);
            let growth=values.capacity_bytes()-before;
            counts.slot_growths+=u64::from(growth!=0);counts.slot_bytes+=growth as u64;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cell::{Effects,RhsFrame};
    use std::{rc::Rc,sync::Arc};

    fn projected_child()->(Graph,u32) {
        let mut p=super::super::tests::graph().program;
        let eq=p.tables[0].schema[0].clone();
        p.tables[0].schema.insert(0,eq.clone());
        let mut unit=p.tables[0].clone();unit.name="Done".into();unit.constructor=false;
        unit.virtual_fact=false;unit.schema=vec![eq.clone(),eq.clone(),json!({"kind":"Unit"})];
        unit.merge=json!({"var":"old"});p.tables.push(unit);p.table_templates.push(0);
        let template=&mut p.templates[0];template.sorts.push(eq);
        template.parent_columns=[(0,2),(5,0)].into_iter().collect();
        for op in Arc::make_mut(&mut template.ops) {if let Op::Let(_,_,keys)=op {keys.push(keys[0].clone());}}
        Arc::make_mut(&mut template.ops).push(Op::Set(1,vec![Arg::Slot(4),Arg::Slot(5)],Arg::Literal(Value::Int(0))));
        p.rules[0].inputs=vec![0,5].into();p.known_results.static_skip=vec![Rc::new(vec![false;5])];
        p.executions=vec![crate::cell::execution::Plan::derive(&p.tables,&p.templates[0],&[0,5])];
        p.executions[0].births=Plan::derive(&p,0).map(Arc::new);
        let mut g=Graph::new(p).unwrap();
        let parent=g.begin_transient(0,[(0,Value::Eq(100))].into_iter().collect(),None).unwrap();
        g.construct(parent,0,0,&[Arg::Slot(0),Arg::Slot(0)],1).unwrap();g.promote_active();
        let child=g.begin_transient(0,Default::default(),Some(FactRef {cell:parent,op:0})).unwrap();
        (g,child)
    }
    fn execute(g:&mut Graph,cell:u32,start:usize) {
        let ops=g.program.templates[0].ops.clone();
        for (position,op) in ops.iter().enumerate().skip(start) {
            RhsFrame {cell,receipts:&mut Effects::default()}.execute(g,position,op,None).unwrap();
            g.rhs_frame_mut(cell).unwrap().completed_prefix=position+1;
        }
    }
    #[test]
    fn root_and_local_tail_preserve_projected_values_unit_only_inputs_and_later_union() {
        let (mut expected,reference)=projected_child();execute(&mut expected,reference,0);
        for local in [false,true] {
            let (mut g,cell)=projected_child();let mut effects=Effects::default();
            let (counts,job)=if local {
                g.construct(cell,0,0,&[Arg::Slot(0),Arg::Slot(0)],1).unwrap();
                g.rhs_frame_mut(cell).unwrap().completed_prefix=1;
                let mut window=Window::seed(&g,cell,1);
                g.take_local_job(0,cell,&mut window,5,true).unwrap()
            } else {g.take_root_job(0,cell,5,&[],0,&mut effects.writer(),
                #[cfg(feature="storage-metrics")] &crate::cell::QueryFacts::None,|_,_|false).unwrap()};
            assert_eq!(counts.captured_reads,if local {1}else{2},"Unit-only input must survive capture; duplicates need no second read");
            assert_eq!(counts.capture_layout_reads,1);
            assert_eq!(counts.capture_slot_checks,2,"internal operands never enter runtime capture");
            let pool=rayon::ThreadPoolBuilder::new().num_threads(2).build().unwrap();
            let done=pool.install(||job.unwrap().run(g.parents.reader(),&mut effects.writer(),&mut Counts::default()));
            g.commit_local_job(done,&mut effects.writer()).unwrap();
            assert_eq!(g.export().unwrap(),expected.export().unwrap());
            g.union(100,50).unwrap();g.repair().unwrap();
            let (mut repaired,reference)=projected_child();execute(&mut repaired,reference,0);
            repaired.union(100,50).unwrap();repaired.repair().unwrap();
            assert_eq!(g.export().unwrap(),repaired.export().unwrap());
        }
    }
    #[test]
    fn constructor_only_capture_does_not_read_a_later_unit_input() {
        let (mut g,cell)=projected_child();
        let plan=g.program.executions[0].births.clone().unwrap();let mut counts=Counts::default();
        g.capture_worker_inputs(cell,&plan.inputs,0,0,false,&mut counts).unwrap();
        assert_eq!(counts.captured_reads,1);assert!(!g.rhs_frame(cell).unwrap().values.contains_key(&5));
        g.capture_worker_inputs(cell,&plan.inputs,0,0,true,&mut counts).unwrap();
        assert_eq!(counts.captured_reads,2);assert_eq!(g.rhs_frame(cell).unwrap().values.get(&5),Some(&Value::Eq(100)));
    }
    #[test]
    fn independent_constructor_prefix_does_not_duplicate_suffix_inputs() {
        let mut p=super::super::tests::graph().program;
        let n=512;let eq=p.tables[0].schema[0].clone();
        let t=&mut p.templates[0];
        t.sorts=vec![eq;2*n];
        t.ops=(0..n).map(|i|Op::Let(n+i,Call::Table(0),vec![Arg::Slot(i)])).collect::<Vec<_>>().into();
        t.defs=(0..n).map(|i|(n+i,i)).collect();
        p.rules[0].inputs=(0..n).collect::<Vec<_>>().into();
        p.known_results.static_skip=vec![Rc::new(vec![false;n])];
        let plan=Plan::derive(&p,0).unwrap();
        assert_eq!(plan.inputs.spans.iter().flatten().count(),1);
        assert_eq!(plan.inputs.slots.len(),1,
            "independent source operations cannot become worker suffix entries");
        assert!(plan.inputs.storage_bytes()<n*64);
    }
}
