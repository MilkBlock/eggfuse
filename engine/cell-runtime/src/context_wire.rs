//! Compatibility views of the old context artifact. Runtime execution stores
//! only the common Cell Query; these borrowed fields exist during serialization.
use super::*;
use crate::cell::Field;

#[derive(Serialize)]
enum WireField<'a> {
    Prefix(usize),
    Tail(usize),
    Literal(&'a Value),
}
fn field(f: &Field) -> WireField<'_> {
    match f {
        Field::Anchor(slot) => WireField::Prefix(*slot),
        Field::Column { step: 0, column } => WireField::Tail(*column),
        Field::Literal(v) => WireField::Literal(v),
        _ => unreachable!("scalar suffix results have no legacy projection"),
    }
}
struct Outputs<'a>(&'a [Field]);
impl Serialize for Outputs<'_> {
    fn serialize<S: serde::Serializer>(&self, s: S) -> std::result::Result<S::Ok, S::Error> {
        s.collect_seq(self.0.iter().map(field))
    }
}
struct Checks<'a>(&'a [(usize, Field)]);
impl Serialize for Checks<'_> {
    fn serialize<S: serde::Serializer>(&self, s: S) -> std::result::Result<S::Ok, S::Error> {
        s.collect_seq(self.0.iter().map(|(col, f)| (*col, field(f))))
    }
}
impl Serialize for Plan {
    fn serialize<S: serde::Serializer>(&self, s: S) -> std::result::Result<S::Ok, S::Error> {
        #[derive(Serialize)]
        struct Wire<'a> {
            root: usize,
            ports: &'a [usize],
            tail: usize,
            columns: &'a [usize],
            versions: &'a [usize],
            identity_literal: bool,
            output: Outputs<'a>,
            checks: Checks<'a>,
            #[serde(skip_serializing_if = "Vec::is_empty")]
            post: &'a Vec<usize>,
        }
        let ports = self.ports.iter().map(|s| s.step.atom).collect::<Vec<_>>();
        let post = self.query.steps.iter().skip(1).map(|s| s.atom).collect::<Vec<_>>();
        let expansion = self.query.steps[0].expansion.as_ref().expect("terminal expansion");
        Wire { root: self.root, ports: &ports, tail: self.tail, columns: &self.columns,
            versions: &self.versions, identity_literal: self.identity_literal,
            output: Outputs(if post.is_empty() { &self.query.inputs } else { &[] }),
            checks: Checks(&expansion.checks), post: &post }.serialize(s)
    }
}
