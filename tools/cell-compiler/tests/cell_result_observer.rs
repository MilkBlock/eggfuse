use eggfuse_cell_runtime::{
    compiler,
    executor::{CellResultObserver, Executor},
    graph::Graph,
    program::{Arg, Call, Op, Program},
    value,
};
use std::{cell::RefCell, collections::BTreeSet, rc::Rc};

#[test]
fn actual_reused_results_and_run_boundaries() {
    let source = r#"
(datatype Expr (N i64) (F Expr) (G Expr))
(ruleset grow)
(ruleset merge)
(rule ((= x (N i))) ((let y (F x)) (G y)) :ruleset grow)
(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset merge)
(F (N 0))
(N 1)
(run-schedule (seq (run grow) (run merge) (run grow)))
"#;
    let core = eggfuse_bake::device_frontend::core("rhs-observer", source).unwrap();
    let artifact = compiler::compile(core, &BTreeSet::new()).unwrap();
    let make = || {
        Executor::new(
            Graph::new(Program::parse(artifact.clone()).unwrap()).unwrap(),
            true,
        )
    };
    let mut baseline = make();
    let nt = baseline
        .graph
        .program
        .tables
        .iter()
        .position(|t| t.name == "N")
        .unwrap();
    let ft = baseline
        .graph
        .program
        .tables
        .iter()
        .position(|t| t.name == "F")
        .unwrap();
    let n = baseline
        .graph
        .lookup(nt, &[value::Value::Int(0)])
        .unwrap()
        .unwrap();
    let existing = baseline
        .graph
        .lookup(ft, &[n.values.last().unwrap().clone()])
        .unwrap()
        .unwrap()
        .values
        .last()
        .unwrap()
        .clone();
    baseline.execute().unwrap();
    let mut observed = make();
    let checked = Rc::new(RefCell::new((0usize, false)));
    let counts = checked.clone();
    let slots = observed
        .graph
        .program
        .rules
        .iter()
        .map(|r| (0..observed.graph.program.templates[r.template].sorts.len()).collect())
        .collect();
    observed.result_observer = Some(CellResultObserver {
        slots,
        observe: Box::new(move |_, rid, complete, values, g| {
            assert!(complete);
            counts.borrow_mut().0 += 1;
            let get = |a: &Arg| match a {
                Arg::Literal(v) => Some(v.clone()),
                Arg::Slot(s) => values
                    .iter()
                    .find(|(i, _)| i == s)
                    .and_then(|(_, v)| v.as_ref().ok())
                    .cloned(),
            };
            for op in g.program.templates[g.program.rules[rid].template]
                .ops
                .iter()
            {
                if let Op::Let(dst, Call::Table(t), args) = op {
                    if !g.program.tables[*t].constructor {
                        continue;
                    }
                    let args: Vec<_> = args
                        .iter()
                        .map(|a| get(a).expect("available constructor input"))
                        .collect();
                    let actual = get(&Arg::Slot(*dst)).expect("available constructor output");
                    let expected = g.lookup(*t, &args).unwrap().unwrap();
                    assert_eq!(
                        value::canon(&actual, &g.parents),
                        value::canon(expected.values.last().unwrap(), &g.parents)
                    );
                    if *t == ft && actual == existing {
                        counts.borrow_mut().1 = true;
                    }
                }
            }
        }),
    });
    observed.execute().unwrap();
    assert_eq!(baseline.snapshots, observed.snapshots);
    assert_eq!(baseline.binding_audit, observed.binding_audit);
    assert_eq!(
        baseline.graph.export().unwrap(),
        observed.graph.export().unwrap()
    );
    assert!(checked.borrow().0 > 0);
    assert!(
        checked.borrow().1,
        "existing constructor result was captured"
    );
}
