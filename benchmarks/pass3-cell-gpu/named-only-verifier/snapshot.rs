// The checker borrows this view. Only its adapter can access Graph.
use crate::{
    cell::{bind_query, query_operand},
    graph::{Dependency, Graph, Row},
    program::{Arg, Result},
    value::Value,
};
use std::collections::BTreeMap;
pub(crate) struct Snapshot<'a>(&'a Graph);
impl<'a> Snapshot<'a> {
    pub(crate) fn new(graph: &'a Graph) -> Self {
        Self(graph)
    }
    pub(super) fn row(&self, address: Dependency) -> Result<Option<Row>> {
        self.0.row(address)
    }
    pub(super) fn bind(&self, a: &Arg, v: &Value, frame: &mut BTreeMap<usize, Value>) -> bool {
        bind_query(a, v, frame, self.0)
    }
    pub(super) fn operand(&self, a: &Arg, frame: &BTreeMap<usize, Value>) -> Option<Value> {
        query_operand(a, frame, self.0)
    }
    pub(super) fn primitive(&self, op: &str, values: &[Value], ty: &str) -> Result<Option<Value>> {
        self.0.primitive(op, values, ty)
    }
}
