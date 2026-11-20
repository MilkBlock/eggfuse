use crate::cell::Field as SourceField;
use std::fmt::Write as _;

type NativeVerifier = fn(
    &mut VerifiedRows,
    &Graph,
    &Rule,
    &ProjectedRule,
    &Row,
    u64,
    &mut [u64; 8],
) -> Result<Option<Instance>>;

#[derive(Debug, Copy, Clone, Ord, PartialOrd, Eq, PartialEq)]
enum Input {
    Anchor(usize),
    Prior(usize),
    Literal,
}
impl Input {
    fn from_field(f: &SourceField) -> Option<Self> {
        match f {
            SourceField::Anchor(i) => Some(Self::Anchor(*i)),
            SourceField::StepResult(i) => Some(Self::Prior(*i)),
            SourceField::Literal(_) => Some(Self::Literal),
            SourceField::Column { .. } => None,
        }
    }
    fn value(self, field: String) -> String {
        match self {
            Self::Anchor(col) => format!("row.values[{col}].clone()"),
            Self::Prior(i) => format!("v{i}.clone()"),
            Self::Literal => format!("native_literal(g,&{field})?"),
        }
    }
}
#[derive(Debug, Ord, PartialOrd, Eq, PartialEq)]
struct Operation {
    table: bool,
    keys: Vec<Input>,
    check: Option<Input>,
}
#[derive(Debug, Ord, PartialOrd, Eq, PartialEq)]
struct VerifierShape {
    ops: Vec<Operation>,
    outputs: Vec<Input>,
}
impl VerifierShape {
    fn lower(q: &crate::cell::Query) -> Option<Self> {
        let mut ops = Vec::new();
        for step in &q.steps {
            if step.expansion.is_some() {
                return None;
            }
            let keys = step
                .key
                .iter()
                .map(Input::from_field)
                .collect::<Option<_>>()?;
            let check = match &step.check_result {
                Some(f) => Some(Input::from_field(f)?),
                None => None,
            };
            ops.push(Operation {
                table: matches!(step.call, Call::Table(_)),
                keys,
                check,
            });
        }
        Some(Self {
            ops,
            outputs: q
                .inputs
                .iter()
                .map(Input::from_field)
                .collect::<Option<_>>()?,
        })
    }

    fn emit(&self, name: usize) -> String {
        let mut s = format!(
            "#[allow(unused_variables,unused_mut)]\nfn kernel_{name}(state:&mut VerifiedRows,g:&Graph,r:&Rule,p:&ProjectedRule,row:&Row,wm:u64,work:&mut [u64;8])->Result<Option<Instance>>{{\n"
        );
        s.push_str("let mut epoch=row.epoch;\n");
        for (i, op) in self.ops.iter().enumerate() {
            let step = format!("p.query.steps[{i}]");
            let args = op
                .keys
                .iter()
                .enumerate()
                .map(|(j, f)| f.value(format!("{step}.key[{j}]")))
                .collect::<Vec<_>>()
                .join(",");
            writeln!(s, "let args=[{args}];").unwrap();
            if op.table {
                writeln!(s,"let Call::Table(table)={step}.call else{{return Err(\"wrong generated table operation\".into())}};").unwrap();
                s.push_str("work[3]+=1; state.projected.stats.point_reads+=1;\n");
                writeln!(s,"let Some(found)=g.lookup(table,&args)?.filter(|v|!v.hidden) else{{return Ok(None)}};\nlet dep{i}=found.witness; epoch=epoch.max(found.epoch);\nlet v{i}=found.values.last().ok_or(\"empty function row\")?.clone();").unwrap();
            } else {
                writeln!(s,"let Call::Primitive(op,ty)=&{step}.call else{{return Err(\"wrong generated primitive operation\".into())}};").unwrap();
                writeln!(s,"work[4]+=1;state.projected.stats.scalar_ops+=1;\nlet Some(v{i})=g.primitive(op,&args,ty)? else{{return Ok(None)}};").unwrap();
            }
            if let Some(f) = op.check {
                let x = f.value(format!(
                    "*{step}.check_result.as_ref().ok_or(\"missing result test\")?"
                ));
                writeln!(s, "if v{i}!={x} {{return Ok(None)}}").unwrap();
            }
        }
        s.push_str("if r.seminaive && epoch<wm{return Ok(None)}\nlet mut slots=crate::slots::Slots::default();\n");
        for (i, f) in self.outputs.iter().enumerate() {
            let value = f.value(format!("p.query.inputs[{i}]"));
            writeln!(s, "slots.insert(r.inputs[{i}],{value});").unwrap();
        }
        s.push_str("let mut refs=vec![None;r.query.len()];refs[p.pivot]=Some(row.witness);\n");
        for (i, op) in self.ops.iter().enumerate().filter(|(_, op)| op.table) {
            let _ = op;
            writeln!(s, "refs[p.query.steps[{i}].atom]=Some(dep{i});").unwrap();
        }
        s.push_str("state.projected.stats.successes+=1;\nOk(Some(Instance::matched(slots,QueryFacts::Ports(refs),epoch)))\n}\n");
        s
    }
}

fn native_literal(g: &Graph, f: &SourceField) -> Result<Value> {
    let SourceField::Literal(v) = f else {
        return Err("wrong generated literal operand".into());
    };
    Ok(crate::value::canon(v, &g.parents))
}

pub fn emit_verifier_library(program: &Program) -> (String, serde_json::Value) {
    let mut counts = BTreeMap::<VerifierShape, usize>::new();
    for rule in &program.rules {
        let Some(p) = plan(rule) else { continue };
        let Some(pivot) = p.pivot else { continue };
        if let Some(query) = crate::cell::Query::compile(rule, pivot, &p.order)
            && let Some(shape) = VerifierShape::lower(&query)
        {
            *counts.entry(shape).or_default() += 1;
        }
    }
    let mut source = String::new();
    let mut registry = String::from(
        "fn native_entry(shape:&str)->Option<(NativeVerifier,usize)>{\nmatch shape{\n",
    );
    let mut layouts = vec![];
    for (i, (shape, n)) in counts.iter().enumerate() {
        let key = format!("{shape:?}");
        source.push_str(&shape.emit(i));
        writeln!(registry, "{key:?}=>Some((kernel_{i},{n})),").unwrap();
        layouts.push(serde_json::json!({"shape":key,"rules":n,"steps":shape.ops.len()}));
    }
    registry.push_str("_=>None,\n}\n}\n");
    source.push_str(&registry);
    (source, serde_json::json!(layouts))
}
