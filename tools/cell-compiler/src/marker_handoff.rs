//! Forward values proved by a marker's positive constructor view in the .egg
//! program itself. An Eq value is not a physical row address or a done bit.
use crate::surface::*;
use eggfuse_cell_runtime::cell::construction::{Construction, Known};
use serde_json::{Value as J, json};
use std::collections::{BTreeMap, BTreeSet};

pub const RESULT: &str = "cell_spine_result";

#[derive(Default)]
pub struct Stats {
    pub consumer_result_uses: usize,
    pub publication_result_uses: usize,
    pub captured_results: usize,
}

struct Forward<'a> {
    sig: &'a J,
    unavailable: &'a BTreeSet<&'a str>,
    construction: Construction<String, String, ()>,
    // Lexical source bindings are not SSA aliases: a later shadowing let must
    // not change the identity of an earlier query value. RHS binders are renamed.
    bindings: BTreeMap<String, J>,
    next: usize,
    stats: Stats,
}
impl Forward<'_> {
    fn permanent(&self, e: &J) -> bool {
        e["kind"] == "call"
            && self.sig[s(&e["head"])]["kind"] == "constructor"
            && !self.unavailable.contains(s(&e["head"]))
    }
    fn pure(&self, e: &J) -> bool {
        e["kind"] != "call" || (self.permanent(e) && a(&e["args"]).iter().all(|x| self.pure(x)))
    }
    fn fresh(next: &mut usize) -> String {
        let n = format!("{RESULT}{}", *next);
        *next += 1;
        n
    }
    fn expr(&mut self, e: &J, capture: bool, publication: bool, out: &mut Vec<J>) -> J {
        if e["kind"] == "var" {
            return self.bindings.get(s(&e["name"])).unwrap_or(e).clone();
        }
        if e["kind"] != "call" {
            return e.clone();
        }
        // Never hoist a constructor across an impure argument. Inside such an
        // expression only replace already bound values; retain evaluation order.
        let capture = capture && self.pure(e);
        let args = a(&e["args"])
            .iter()
            .map(|x| self.expr(x, capture, publication, out))
            .collect();
        let e = call(s(&e["head"]), args);
        if !self.permanent(&e) {
            return e;
        }
        let table = s(&e["head"]).to_owned();
        let inputs = a(&e["args"]).iter().map(term).collect::<Vec<_>>();
        let mut expression = Some(e);
        let next = &mut self.next;
        let stats = &mut self.stats;
        let result = self.construction.construct(table, inputs, || {
            if !capture { return None; }
            let n = Self::fresh(next);
            out.push(json!({"kind":"let","name":n,"expr":expression.take().unwrap()}));
            stats.captured_results += 1;
            Some(Known { value: n, source: () })
        });
        if let Some((known, reused)) = result {
            if reused {
                if publication { stats.publication_result_uses += 1; }
                else { stats.consumer_result_uses += 1; }
            }
            var(&known.value)
        } else {
            expression.unwrap()
        }
    }
}

/// `body` is the original flattened LHS, before replacing its positive facts
/// by markers. Those facts supply the proof for forwarding their result slots.
/// `publication_at` splits original actions from generated marker writes.
pub fn forward(
    body: &[J],
    head: &[J],
    publication_at: usize,
    sig: &J,
    unavailable: &BTreeSet<&str>,
) -> (Vec<J>, Stats) {
    let mut f = Forward {
        sig,
        unavailable,
        construction: Construction::default(),
        bindings: BTreeMap::new(),
        next: 0,
        stats: Stats::default(),
    };
    for fact in body {
        if fact["kind"] == "eq" && a(&fact["args"]).len() == 2 {
            let (v, e) = (&fact["args"][0], &fact["args"][1]);
            if v["kind"] == "var"
                && f.permanent(e)
                && a(&e["args"]).iter().all(|a| a["kind"] != "call")
            {
                f.construction.matched(s(&e["head"]).to_owned(),
                    a(&e["args"]).iter().map(term).collect(), s(&v["name"]).to_owned(), ());
            }
        }
    }
    let mut out = vec![];
    for (i, ac) in head.iter().enumerate() {
        let mut ac = ac.clone();
        let publication = i >= publication_at;
        let capture = ac
            .get("expr")
            .into_iter()
            .chain(a(&ac["args"]))
            .chain(ac.get("value"))
            .all(|e| f.pure(e));
        if let Some(expr) = ac.get_mut("expr") {
            *expr = f.expr(expr, capture, publication, &mut out);
        }
        if let Some(args) = ac["args"].as_array_mut() {
            for e in args {
                *e = f.expr(e, capture, publication, &mut out);
            }
        }
        if let Some(v) = ac.get_mut("value") {
            *v = f.expr(v, capture, publication, &mut out);
        }
        if ac["kind"] == "let" {
            let old = s(&ac["name"]).to_owned();
            if ac["expr"]["kind"] != "call" {
                f.bindings.insert(old, ac["expr"].clone());
                continue;
            }
            // Rename local binders so a shadowing let cannot change the meaning
            // of a query value already saved in the proof environment.
            let n = Forward::fresh(&mut f.next);
            ac["name"] = json!(n);
            f.bindings.insert(old, var(&n));
        } else if ac["kind"] == "expr" && ac["expr"]["kind"] != "call" {
            continue;
        }
        out.push(ac);
    }
    (out, f.stats)
}

#[cfg(test)]
mod tests {
    use super::*;
    use eggfuse_cell_runtime::{compiler, executor::Executor, graph::Graph, program::Program};

    const SOURCE: &str = include_str!("../tests/fixtures/marker-construction.egg");
    fn execute(source: &str, on: bool) -> (Executor, J, String) {
        execute_receipts(source,on,true)
    }
    fn execute_receipts(source:&str,on:bool,receipts:bool)->(Executor,J,String) {
        let (source, report, names) =
            crate::markers::rewrite_with_receipts("handoff.egg", source, &[], None, true, on,receipts).unwrap();
        let mut native = egglog::EGraph::default();
        native.parse_and_run_program(None, &source).unwrap();
        let core = eggfuse_bake::device_frontend::core("marked.egg", &source).unwrap();
        crate::marker_ir::build(&core, &report, &source, b"test").unwrap();
        let p = Program::parse(compiler::compile(core, &names).unwrap()).unwrap();
        let mut e = Executor::new(Graph::new(p).unwrap(), true);
        e.execute().unwrap();
        let mut state = e.graph.export().unwrap();
        state["anchors"] = json!([]);
        equivalent(
            &json!({"rows":native.device_snapshot().unwrap(),"anchors":[]}),
            &state,
        );
        (e, report, source)
    }
    #[test]
    fn optional_apply_receipts_preserve_marker_queries_and_source_runs() {
        let joined=SOURCE.replace("(run-schedule", "(ruleset join)\n(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset join)\n(run-schedule")
            +"\n(run join 1) (run-schedule (seq (run make) (run read) (run keep)))";
        for input in [SOURCE,joined.as_str()] {for handoff in [false,true] {
            let (old,report,_)=execute_receipts(input,handoff,true);
            let (new,omitted,source)=execute_receipts(input,handoff,false);
            let names=report["receipt_tables"].as_array().unwrap();
            assert!(!names.is_empty(),"exercise actual receipt elimination");
            assert!(omitted["receipt_tables"].as_array().unwrap().is_empty());
            assert_eq!(report["markers"],omitted["markers"]);
            assert!(!source.contains("CellSpineApplied"));
            let project=|mut state:J| {
                state["rows"].as_array_mut().unwrap().retain(|r|!names.contains(&r["table"]));
                state
            };
            let old_state=old.graph.export().unwrap();
            assert!(old_state["rows"].as_array().unwrap().iter().any(|r|names.contains(&r["table"])));
            equivalent(&project(old_state),&new.graph.export().unwrap());
            assert_eq!(old.snapshots.len(),new.snapshots.len());
            for (a,b) in old.snapshots.iter().zip(&new.snapshots) {equivalent(&project(a.clone()),b);}
            assert_eq!(old.steps.len(),new.steps.len());
            for (a,b) in old.steps.iter().zip(&new.steps) {
                for key in ["ordinal","ruleset","path","iterations","logical_matches","executed_bindings"] {
                    assert_eq!(a[key],b[key],"source schedule changed: {key}");
                }
            }
        }}
    }
    #[test]
    fn receipt_omission_does_not_accept_user_defined_reserved_tables() {
        let source="(relation CellSpineApplied0 (i64)) (CellSpineApplied0 1)";
        assert!(crate::markers::rewrite_with_receipts("reserved.egg",source,&[],None,true,false,false).is_err());
    }
    fn compare(source: &str) -> (Executor, Executor, J, String) {
        let mut native = egglog::EGraph::default();
        native.parse_and_run_program(None, source).unwrap();
        let (old, _, _) = execute(source, false);
        let (new, report, emitted) = execute(source, true);
        let original_tables = native.get_function_names();
        let mut projected = new.graph.export().unwrap();
        projected["rows"]
            .as_array_mut()
            .unwrap()
            .retain(|r| original_tables.iter().any(|t| r["table"] == *t));
        projected["anchors"] = json!([]);
        equivalent(
            &json!({"rows":native.device_snapshot().unwrap(),"anchors":[]}),
            &projected,
        );
        equivalent(&old.graph.export().unwrap(), &new.graph.export().unwrap());
        assert_eq!(old.snapshots.len(), new.snapshots.len());
        for (a, b) in old.snapshots.iter().zip(&new.snapshots) {
            equivalent(a, b);
        }
        assert_eq!(old.steps.len(), new.steps.len());
        for (a, b) in old.steps.iter().zip(&new.steps) {
            for k in [
                "ordinal",
                "ruleset",
                "path",
                "iterations",
                "epoch",
                "logical_matches",
                "executed_bindings",
                "changed",
            ] {
                assert_eq!(a[k], b[k], "{k}");
            }
        }
        (old, new, report, emitted)
    }
    fn equivalent(a: &J, b: &J) {
        use eggfuse_bake::saturated_rule_composition::{
            Comparison, Row, SaturatedRuleComposition, Vertex, compare,
        };
        let convert = |state: &J| {
            let mut values = vec![];
            let mut ids = BTreeMap::new();
            let mut value = |v: &J| {
                *ids.entry(v.to_string()).or_insert_with(|| {
                    let i = values.len();
                    values.push(Vertex {
                        sort: s(&v["sort"]).into(),
                        literal: v.get("value").map(J::to_string),
                    });
                    i
                })
            };
            let mut rows = vec![];
            let mut hidden = vec![];
            for (i, row) in super::a(&state["rows"]).iter().enumerate() {
                let (last, args) = super::a(&row["values"]).split_last().unwrap();
                rows.push(Row {
                    op: s(&row["table"]).into(),
                    args: args.iter().map(&mut value).collect(),
                    result: value(last),
                });
                if row["subsumed"] == true {
                    hidden.push(i);
                }
            }
            let ports = super::a(&state["anchors"])
                .iter()
                .map(|p| {
                    (
                        format!("{}:{}", p["sort"], p["old"]),
                        value(&json!({"sort":p["sort"],"eq":p["now"]})),
                    )
                })
                .collect();
            SaturatedRuleComposition {
                version: 2,
                local_ids: vec![],
                scope: J::Null,
                values,
                rows,
                subsumed_rows: hidden,
                ports,
            }
        };
        let result = compare(&convert(a), &convert(b)).unwrap();
        assert!(
            matches!(result, Comparison::Equivalent { .. }),
            "{result:?}"
        );
    }
    #[test]
    fn marker_values_replace_rhs_requeries_and_publication_reconstruction() {
        let (old, new, report, emitted) = compare(SOURCE);
        assert!(report["selected"].as_u64().unwrap() > 0);
        assert_eq!(report["result_handoff"]["new_marker_fields"], 0);
        assert!(
            a(&report["result_handoff"]["rules"])
                .iter()
                .any(|r| r["consumer_result_uses"].as_u64().unwrap() >= 2)
        );
        assert!(
            a(&report["result_handoff"]["rules"])
                .iter()
                .any(|r| r["publication_result_uses"].as_u64().unwrap() > 0)
        );
        assert!(
            new.graph.key_lookup_calls.get() < old.graph.key_lookup_calls.get(),
            "{} -> {}\n{emitted}",
            old.graph.key_lookup_calls.get(),
            new.graph.key_lookup_calls.get()
        );
        let rules = &new.graph.program.artifact["recipe"]["rules"];
        let consumer = a(rules)
            .iter()
            .find(|r| r["metadata"]["name"] == "consumer")
            .unwrap();
        assert!(
            a(&consumer["effects"])
                .iter()
                .all(|e| e["call"]["table"] != "F" && e["call"]["table"] != "G")
        );
    }
    #[test]
    fn union_and_later_residual_activation_use_current_marker_values() {
        let source = SOURCE.replace("(ruleset make)", "(ruleset merge) (ruleset later)\n(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset merge)\n(rule ((= a (N 0))) ((Edge a 99)) :ruleset later)\n(ruleset make)")
            .replace("(run read) (run keep)", "(run merge) (run read) (run later) (run read) (run keep)");
        compare(&source);
    }
    #[test]
    fn deletable_and_subsumable_constructors_are_not_proofs() {
        for change in ["delete", "subsume"] {
            let source = SOURCE.replace("(ruleset make)", &format!("(ruleset retire) (rule ((= f (F x))) (({change} (F x))) :ruleset retire)\n(ruleset make)"));
            let (_, new, _, _) = compare(&source);
            let rules = a(&new.graph.program.artifact["recipe"]["rules"]);
            let consumer = rules
                .iter()
                .find(|r| r["metadata"]["name"] == "consumer")
                .unwrap();
            assert!(
                a(&consumer["effects"])
                    .iter()
                    .any(|e| e["call"]["table"] == "F")
            );
        }
    }
    #[test]
    fn mutable_reads_and_numeric_guards_remain_live() {
        let source = SOURCE.replace("(ruleset make)", "(function number (E) i64 :merge new) (ruleset update)\n(rule ((= x (N n))) ((set (number x) 7)) :ruleset update)\n(ruleset make)")
            .replace("(Edge x n))", "(Edge x n) (= k (number x)) (> k 0))")
            .replace("(run read) (run keep)", "(run read) (run update) (run read) (run keep)");
        compare(&source);
    }
    #[test]
    fn rhs_aliases_keep_actual_results_and_live_function_inputs() {
        let source = SOURCE.replace("(ruleset make)", "(function number (E) i64 :merge new) (function saved (E) i64 :merge new)\n(ruleset make)")
            .replace("(Edge x n))", "(Edge x n) (= before (number x)))")
            .replace("((Out (G (F x)) n))", "((set (number x) (+ before 1)) (let f2 (F x)) (let g2 (G f2)) (Out g2 n) (set (saved x) before))")
            .replace("(run-schedule", "(set (number (N 0)) 0) (set (number (N 1)) 0)\n(run-schedule");
        compare(&source);
    }
    #[test]
    fn computed_arguments_keep_the_original_effect_order() {
        let source = SOURCE.replace("((Out (G (F x)) n))",
            "((Out (G (F x)) n) (Keep (Out (G (F x)) (+ n 1))))");
        compare(&source);
    }
    #[test]
    fn literal_and_repeated_marker_fields_reject_other_local_rows() {
        compare(include_str!("../tests/fixtures/marker-bindings.egg"));
    }
}
