use eggfuse_cell_runtime::{
    compiler,
    executor::{CellBindingObserver, Executor},
    graph::Graph,
    program::Program,
    proof_audit::{Audit, Claim, Frame, Proposal},
};
use std::{cell::RefCell, collections::BTreeSet, rc::Rc};
#[test]
fn native_audit_preserves_runs_and_rejects_false_missing_and_stale_claims() {
    let source = r#"
(datatype E (N i64) (F E))
(ruleset grow)
(ruleset merge)
(rule ((= a (N 0)) (= b (N 1)) (= c (N 2))) ((union a b)) :ruleset merge)
(rule ((= x (N i))) ((F x)) :ruleset grow)
(N 0) (N 1) (N 2)
(run-schedule (seq (run grow) (run merge) (run grow)))
"#;
    let artifact = compiler::compile(
        eggfuse_bake::device_frontend::core("proof-audit", source).unwrap(),
        &BTreeSet::new(),
    )
    .unwrap();
    let make = || {
        Executor::new(
            Graph::new(Program::parse(artifact.clone()).unwrap()).unwrap(),
            true,
        )
    };
    let mut reference = make();
    reference.execute().unwrap();
    let audit = Rc::new(RefCell::new(Audit::new(
        &Program::parse(artifact.clone()).unwrap(),
        42,
    )));
    let hook = audit.clone();
    let mut checked = make();
    checked.binding_observer = Some(CellBindingObserver {
        rules: vec![true; 2],
        observe: Box::new(move |_, index, rule, slots, graph| {
            hook.borrow_mut().capture(index, rule, slots, graph)
        }),
    });
    let mut frames = vec![];
    while !checked.tasks.is_empty() {
        let n = checked.steps.len();
        checked.execute_until(Some(n + 1)).unwrap();
        if checked.steps.len() > n {
            frames.push(audit.borrow_mut().finish(n + 1, &checked.graph));
        }
    }
    assert_eq!(reference.snapshots, checked.snapshots);
    assert_eq!(reference.binding_audit, checked.binding_audit);
    assert_eq!(
        reference.graph.export().unwrap(),
        checked.graph.export().unwrap()
    );
    fn send<T: Send>() {}
    send::<Frame>();
    let program = Program::parse(artifact.clone()).unwrap();
    let mut incomplete = Audit::new(&program, 42);
    incomplete.capture(0, 0, &Default::default(), &checked.graph);
    assert!(!incomplete.finish(999, &checked.graph).complete);
    assert!(incomplete.stats.missing_ports > 0);
    let frame = frames
        .into_iter()
        .find(|f| f.outcomes.iter().any(|o| o.equal))
        .unwrap();
    let mut p = Proposal {
        execution: 42,
        program: frame.program.clone(),
        run: frame.run,
        epoch: frame.epoch,
        equalities: frame
            .outcomes
            .iter()
            .filter(|o| o.equal)
            .map(|o| o.claim.clone())
            .collect(),
    };
    assert!(frame.check(&p).pass);
    let truth = p.equalities.pop().unwrap();
    assert_eq!(frame.check(&p).false_negatives, 1);
    p.equalities.push(truth.clone());
    p.equalities.push(
        frame
            .outcomes
            .iter()
            .find(|o| !o.equal)
            .unwrap()
            .claim
            .clone(),
    );
    assert_eq!(frame.check(&p).false_positives, 1);
    p.equalities.pop();
    p.equalities.push(truth);
    assert_eq!(frame.check(&p).invalid_claims, 1);
    p.equalities.pop();
    p.equalities.push(Claim::new(usize::MAX, 0, 0, 1));
    assert_eq!(frame.check(&p).invalid_claims, 1);
    p.equalities.pop();
    p.execution += 1;
    assert!(!frame.check(&p).protocol_ok);
    p.execution -= 1;
    p.run += 1;
    assert!(!frame.check(&p).pass);
    p.run -= 1;
    p.epoch += 1;
    assert!(!frame.check(&p).pass);
    p.epoch -= 1;
    p.program.push('x');
    assert!(!frame.check(&p).pass);
    p.program.pop();
    std::thread::spawn(move || {
        assert!(frame.check(&p).pass);
        let mut f = frame;
        f.complete = false;
        assert!(!f.check(&p).pass);
    })
    .join()
    .unwrap();
}
