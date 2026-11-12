//! Oracle for the input-ready scalar fragment in the existing SubTuple rule.
use eggfuse_cell_runtime::value::{Value, primitive};
use serde_json::{Value as J, json};
use std::{env, fs, io};
fn err(s: impl ToString) -> io::Error {
    io::Error::other(s.to_string())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let [input, output] = args.as_slice() else {
        return Err(err("INPUT OUTPUT").into());
    };
    let request: J = serde_json::from_slice(&fs::read(input)?)?;
    let mut rows = vec![];
    for r in request["cases"].as_array().ok_or_else(|| err("cases"))? {
        let a = r[0].as_i64().ok_or_else(|| err("a"))?;
        let b = r[1].as_i64().ok_or_else(|| err("b"))?;
        let matched = primitive(">", &[Value::Int(b), Value::Int(1)], "Unit", &J::Null)
            .map_err(err)?
            .is_some();
        let result = if matched {
            let mut values = vec![];
            let mut ok = true;
            for (name, v) in [("+", a), ("-", b)] {
                match primitive(name, &[Value::Int(v), Value::Int(1)], "i64", &J::Null)
                    .map_err(err)?
                {
                    Some(Value::Int(x)) => values.push(x),
                    _ => {
                        ok = false;
                        break;
                    }
                }
            }
            if ok { json!(values) } else { J::Null }
        } else {
            J::Null
        };
        rows.push(json!({"matched":matched,"result":result}));
    }
    fs::write(output, serde_json::to_vec(&rows)?)?;
    Ok(())
}
