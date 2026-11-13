//! Oracle for the input-ready scalar fragment in the existing SubTuple rule.
use eggfuse_cell_runtime::value::{Value, primitive};
use serde_json::{Value as J, json};
use std::{collections::BTreeMap, env, fs, io};
fn err(s: impl ToString) -> io::Error {
    io::Error::other(s.to_string())
}
fn operand(arg: &J, slots: &BTreeMap<usize, Value>) -> Result<Value, io::Error> {
    if let Some(slot) = arg["slot"].as_u64() {
        slots
            .get(&(slot as usize))
            .cloned()
            .ok_or_else(|| err("missing scalar dependency"))
    } else {
        Ok(Value::Int(
            arg["literal"]
                .as_i64()
                .ok_or_else(|| err("i64 literal required"))?,
        ))
    }
}
fn recipe_reference(request: &J, row: &J) -> Result<J, Box<dyn std::error::Error>> {
    let mut slots = BTreeMap::new();
    let inputs = request["inputs"].as_array().ok_or_else(|| err("inputs"))?;
    let values = row.as_array().ok_or_else(|| err("row"))?;
    if inputs.len() != values.len() {
        return Err(err("input arity").into());
    }
    for (slot, value) in inputs.iter().zip(values) {
        slots.insert(
            slot.as_u64().ok_or_else(|| err("slot"))? as usize,
            Value::Int(value.as_i64().ok_or_else(|| err("integer"))?),
        );
    }
    let mut outputs = serde_json::Map::new();
    for op in request["rule"]["effects"]
        .as_array()
        .ok_or_else(|| err("effects"))?
    {
        if op["op"] == "copy" && op["sort"]["kind"] == "i64" {
            let value = operand(&op["arg"], &slots)?;
            slots.insert(
                op["dst"].as_u64().ok_or_else(|| err("dst"))? as usize,
                value,
            );
        } else if op["kind"] == "compute" {
            if op["sort"]["kind"] != "i64" {
                return Err(err("noninteger compute").into());
            }
            let args = op["args"]
                .as_array()
                .ok_or_else(|| err("args"))?
                .iter()
                .map(|arg| operand(arg, &slots))
                .collect::<Result<Vec<_>, _>>()?;
            let name = op["call"]["primitive"]
                .as_str()
                .ok_or_else(|| err("primitive"))?;
            let dst = op["dst"].as_u64().ok_or_else(|| err("dst"))? as usize;
            match primitive(name, &args, "i64", &J::Null).map_err(err)? {
                Some(Value::Int(value)) => {
                    slots.insert(dst, Value::Int(value));
                    outputs.insert(dst.to_string(), json!(value));
                }
                _ => return Ok(J::Null),
            }
        }
    }
    Ok(J::Object(outputs))
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
 let args=env::args().skip(1).collect::<Vec<_>>();
 let [input,output]=args.as_slice() else{return Err(err("INPUT OUTPUT").into())};
 let request:J=serde_json::from_slice(&fs::read(input)?)?;
 let start=std::time::Instant::now();let mut rows=vec![];
 for row in request["cases"].as_array().ok_or_else(||err("cases"))? {rows.push(recipe_reference(&request,row)?);}
 let seconds=start.elapsed().as_secs_f64();
 fs::write(output,serde_json::to_vec(&json!({"rows":rows,"cpu_reference_seconds":seconds}))?)?;Ok(())
}
