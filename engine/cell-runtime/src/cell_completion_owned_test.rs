use super::*;
use crate::{
    cell::{Effects, RhsFrame},
    program::{Rule, Template},
    result_handoff::Input,
    slots::Slots,
};
use std::{rc::Rc, sync::Arc};

fn graph() -> Graph {
    let eq = json!({"kind":"eq","name":"E"});
    let build = Op::Let(1, Call::Table(0), vec![Arg::Slot(0)]);
    let source = Template {
        name: "source".into(),
        sorts: vec![eq.clone(); 2],
        defs: BTreeMap::from([(1, 0)]),
        ops: Arc::new(vec![build.clone()]),
        parent_columns: BTreeMap::new(),
    };
    let consumer = Template {
        name: "consumer".into(),
        sorts: vec![eq.clone(); 4],
        defs: BTreeMap::from([(1, 0), (3, 2)]),
        parent_columns: BTreeMap::from([(0, 0)]),
        ops: Arc::new(vec![
            build,
            Op::Union(Arg::Slot(1), Arg::Slot(2)),
            Op::Let(3, Call::Table(0), vec![Arg::Slot(2)]),
        ]),
    };
    let rule = Rule {
        template: 1,
        query: Rc::new(vec![]),
        inputs: vec![0, 2].into(),
        completion: Default::default(),
        seminaive: false,
        direct: None,
    };
    let mut p: Program = serde_json::from_value(json!({
        "multi_stage":crate::multistage::MultiStage::default(),
        "entry_schedule":crate::entry_schedule::Plan::default(),
        "tables":[{"name":"F","schema":[eq,eq],"constructor":true,"virtual_fact":true,
            "internal":false,"merge":null}],
        "templates":[source,consumer],"rules":[rule],"sets":{},"control":[],"initial":[],
        "table_templates":[0],"artifact":{}
    }))
    .unwrap();
    p.known_results.static_skip = vec![Rc::new(vec![false; 3])];
    Graph::new(p).unwrap()
}

#[test]
fn completion_keeps_the_query_allocation_actual_results_and_queued_union_at_a_late_miss() {
    for missing in [false, true] {
        for parent in [false, true] {
            let mut g = graph();
            let first = g
                .linked_frame(0, BTreeMap::from([(0, Value::Eq(7))]), None)
                .unwrap();
            g.construct(first, 0, 0, &[Arg::Slot(0)], 1).unwrap();
            let fact = FactRef { cell: first, op: 0 };
            let actual = g.slot(first, 1).unwrap();
            let last = if missing {
                None
            } else {
                let id = g
                    .linked_frame(0, BTreeMap::from([(0, Value::Eq(9))]), None)
                    .unwrap();
                g.construct(id, 0, 0, &[Arg::Slot(0)], 1).unwrap();
                Some(FactRef { cell: id, op: 0 })
            };
            let mut inputs = Slots::with_capacity(8);
            inputs.insert(0, Value::Eq(7));
            inputs.insert(2, Value::Eq(9));
            let allocation = std::ptr::from_ref(inputs.get(&0).unwrap());
            let transfers = [
                Input {
                    op: 0,
                    back: 1,
                    fact: Some(fact),
                    equal_output: false,
                    from_history: true,
                },
                Input {
                    op: 2,
                    back: 1,
                    fact: last,
                    equal_output: false,
                    from_history: true,
                },
            ];
            let mut receipts = Effects::default();
            let (start, unions) = g
                .start_completion(0, inputs, parent.then_some(fact), &transfers, &mut receipts)
                .unwrap();
            assert_eq!(unions, 1);
            assert_eq!(g.stats.union_requests, 1);
            assert_eq!(g.stats.unions, 0, "submission is not congruence completion");
            assert_eq!(g.stats.completion_frame_growths, 0);
            match start {
                cell_prefix::Start::Complete { cell, frame } => {
                    assert!(!missing);
                    assert_eq!(
                        std::ptr::from_ref(frame.values.get(&0).unwrap()),
                        allocation
                    );
                    assert_eq!(
                        g.argument_in(cell, &frame, &Arg::Slot(1)).unwrap(),
                        actual,
                        "the actual result belongs to the earlier producer"
                    );
                    assert_ne!(cell, first);
                    assert_eq!(g.stats.completion_promoted_result_slots, 0);
                }
                cell_prefix::Start::Resume { cell, next_op } => {
                    assert!(missing);
                    assert_eq!(
                        next_op, 2,
                        "neither the successful lookup nor union may replay"
                    );
                    let frame = g.rhs_frame(cell).unwrap();
                    if !parent {
                        assert_eq!(
                            std::ptr::from_ref(frame.values.get(&0).unwrap()),
                            allocation
                        );
                    }
                    assert_eq!(frame.parent, parent.then_some(fact));
                    assert_eq!(g.argument(cell, &Arg::Slot(0)).unwrap(), Value::Eq(7));
                    assert_eq!(g.slot(cell, 1).unwrap(), actual);
                    assert_eq!(g.stats.completion_promoted_result_slots, 1);
                    let instruction = g.program.templates[1].ops[next_op].clone();
                    assert!(
                        (RhsFrame {
                            cell,
                            receipts: &mut receipts
                        })
                        .execute(&mut g, next_op, &instruction, None)
                        .unwrap()
                    );
                    assert_eq!(g.stats.union_requests, 1);
                }
            }
            g.repair().unwrap();
            let Value::Eq(result) = actual else {
                unreachable!()
            };
            assert_eq!(root(&g.parents, result), root(&g.parents, 9));
        }
    }
}
