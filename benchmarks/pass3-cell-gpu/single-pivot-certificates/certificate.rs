// A seminaive rule needs one fresh table row. When the complete key of every
// suffix table is a single scalar pivot column, all such epochs are determinate.
#[derive(Clone)]
struct ScalarPlan {
    pivot_table: usize,
    points: Vec<(usize, usize)>,
}
impl ScalarPlan {
    fn compile(g: &Graph, rule: &Rule, p: &Plan) -> Option<Self> {
        let pivot = p.pivot?;
        let Call::Table(pivot_table) = rule.query[pivot].call else {
            return None;
        };
        if !rule.seminaive {
            return None;
        }
        let mut points = Vec::new();
        for &i in &p.order {
            let atom = &rule.query[i];
            let table = match &atom.call {
                Call::Table(t) => *t,
                Call::Primitive(op, ty)
                    if ty == "i64"
                        && matches!(op.as_str(), "+" | "-" | "*" | "/" | "%" | "min" | "max") =>
                {
                    continue;
                }
                _ => return None,
            };
            let schema = &g.program.tables[table];
            if schema.virtual_fact
                || schema.schema.len() != 2
                || schema.schema[0]["kind"] != "eq"
                || atom.args.len() != 2
            {
                return None;
            }
            let Arg::Slot(key) = atom.args[0] else {
                return None;
            };
            let col = rule.query[pivot]
                .args
                .iter()
                .position(|a| matches!(a,Arg::Slot(s) if *s==key))?;
            if !points.contains(&(table, col)) {
                points.push((table, col));
            }
        }
        if points.is_empty() {
            return None;
        }
        Some(Self {
            pivot_table,
            points,
        })
    }
}
#[derive(Default, serde::Serialize)]
struct Count {
    examined: u64,
    reads: u64,
    missing: u64,
    stale: u64,
    passthrough: u64,
    audited: u64,
}
#[derive(Default)]
struct ScalarProofs {
    enabled: bool,
    audit: bool,
    counts: Vec<Count>,
    plans: Vec<Option<ScalarPlan>>,
    // Audit-only candidates to be independently matched on the same immutable
    // snapshot via the original register-independent source checker.
    skipped: std::collections::BTreeMap<usize, Vec<Token>>,
}
impl ScalarProofs {
    fn rejects(&mut self, g: &Graph, rid: usize, h: &SourceHeader, wm: u64) -> Result<bool> {
        let Some(plan) = &self.plans[rid] else {
            return Ok(false);
        };
        let counts = &mut self.counts[rid];
        counts.examined += 1;
        let Some(w) = h.source else { return Ok(false) };
        let Some(row) = g.row(w)? else {
            return Ok(false);
        };
        if row.hidden || row.table != plan.pivot_table || row.epoch != h.version {
            return Ok(false);
        }
        let mut greatest = row.epoch;
        for &(t, col) in &plan.points {
            let Some(key @ Value::Eq(_)) = row.values.get(col) else {
                counts.passthrough += 1;
                return Ok(false);
            };
            counts.reads += 1;
            let Some(epoch) = g.single_scalar_epoch(t, key)? else {
                counts.missing += 1;
                return Ok(true);
            };
            greatest = greatest.max(epoch);
        }
        if greatest < wm {
            counts.stale += 1;
            return Ok(true);
        }
        Ok(false)
    }
}
