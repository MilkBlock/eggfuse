use serde::{Deserialize, Serialize};
use serde_json::{Value as J, json};

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub enum Value {
    Eq(u64),
    Int(i64),
    Text(std::sync::Arc<String>),
    Float(FloatBits),
    Set(std::sync::Arc<Vec<Value>>),
    Key(eggfuse_structural_key::Key),
}
/// Preserve the artifact's bit encoding while using egglog's OrderedFloat
/// equality, ordering and hashing (all NaNs equal; signed zeros equal).
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(transparent)]
pub struct FloatBits(pub i64);
impl FloatBits {
    pub fn get(self) -> ordered_float::OrderedFloat<f64> {
        ordered_float::OrderedFloat(f64::from_bits(self.0 as u64))
    }
    pub fn key_bits(self) -> u64 {
        let x = self.get().0;
        if x.is_nan() {
            f64::NAN.to_bits()
        } else if x == 0.0 {
            0
        } else {
            x.to_bits()
        }
    }
}
impl PartialEq for FloatBits {
    fn eq(&self, other: &Self) -> bool {
        self.get() == other.get()
    }
}
impl Eq for FloatBits {}
impl PartialOrd for FloatBits {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}
impl Ord for FloatBits {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.get().cmp(&other.get())
    }
}
impl std::hash::Hash for FloatBits {
    fn hash<H: std::hash::Hasher>(&self, state: &mut H) {
        std::hash::Hash::hash(&self.get(), state);
    }
}
fn float(x: f64) -> Value {
    Value::Float(FloatBits(x.to_bits() as i64))
}

/// A scalar interning choice, not graph identity or query state. Only zero's
/// sign is observable after OrderedFloat equality (via to-string). Share it
/// across query/RHS/merge and worker reads, as native base-value interning does.
#[derive(Debug)]
pub struct ScalarContext(std::sync::atomic::AtomicU8);
impl ScalarContext {
    pub fn new(zero: Option<i64>) -> Self {
        Self(std::sync::atomic::AtomicU8::new(
            zero.map_or(0, |x| if x < 0 { 2 } else { 1 }),
        ))
    }
    fn intern(&self, x: FloatBits) -> FloatBits {
        if x.get().0 != 0.0 {
            return x;
        }
        use std::sync::atomic::Ordering::Relaxed;
        let proposed = if x.0 < 0 { 2 } else { 1 };
        let chosen = self
            .0
            .compare_exchange(0, proposed, Relaxed, Relaxed)
            .unwrap_or_else(|x| x);
        let chosen = if chosen == 0 { proposed } else { chosen };
        FloatBits(if chosen == 2 { i64::MIN } else { 0 })
    }
    pub fn primitive(
        &self,
        name: &str,
        args: &[Value],
        output: &str,
        nodes: &J,
    ) -> Result<Option<Value>, String> {
        // The representation is only observable through float operations or
        // conversion. Integer/string/boolean hot paths need no atomic access.
        let mut normalized = smallvec::SmallVec::<[Value; 4]>::new();
        let args = if output == "f64"
            || (name == "to-string" && matches!(args.first(), Some(Value::Float(_))))
        {
            normalized.extend(args.iter().map(|v| match v {
                Value::Float(x) => Value::Float(self.intern(*x)),
                _ => v.clone(),
            }));
            normalized.as_slice()
        } else {
            args
        };
        let v = primitive(name, args, output, nodes)?;
        Ok(v.map(|v| match v {
            Value::Float(x) => Value::Float(self.intern(x)),
            _ => v,
        }))
    }
}

/// Typed capability check shared by artifact admission and the scalar executor.
/// Containers and structural keys retain their own capability checks.
pub fn scalar_signature(name: &str, inputs: &[&str], output: &str) -> bool {
    match name {
        "=" | "!=" | "value-eq" => inputs.len() == 2 && inputs[0] == inputs[1] && output == "Unit",
        "bool-!=" => inputs.len() == 2 && inputs[0] == inputs[1] && output == "bool",
        "bool-=" | "bool-<" | "bool->" | "bool-<=" | "bool->=" => {
            inputs == ["i64", "i64"] && output == "bool"
        }
        "+" if output == "String" => inputs.iter().all(|s| *s == "String"),
        "+" | "-" | "*" | "/" | "%" | "^" | "min" | "max" => {
            inputs == [output, output] && matches!(output, "i64" | "f64")
        }
        "&" | "|" | "<<" | ">>" => inputs == ["i64", "i64"] && output == "i64",
        "not-i64" | "log2" => inputs == ["i64"] && output == "i64",
        "abs" => inputs == [output] && matches!(output, "i64" | "f64"),
        "neg" => inputs == ["f64"] && output == "f64",
        "<" | ">" | "<=" | ">=" => {
            output == "Unit" && (inputs == ["i64", "i64"] || inputs == ["f64", "f64"])
        }
        "to-string" => output == "String" && (inputs == ["i64"] || inputs == ["f64"]),
        "to-f64" => inputs == ["i64"] && output == "f64",
        "to-i64" => inputs == ["f64"] && output == "i64",
        "count-matches" => inputs == ["String", "String"] && output == "i64",
        "replace" => inputs == ["String", "String", "String"] && output == "String",
        "not" => inputs == ["bool"] && output == "bool",
        "or" => inputs.iter().all(|s| *s == "bool") && output == "bool",
        "and" | "xor" | "=>" | "implies" => inputs == ["bool", "bool"] && output == "bool",
        "guard" => inputs == ["bool"] && output == "Unit",
        _ => false,
    }
}
#[path = "parent_epoch.rs"]
pub(crate) mod parent_epoch;
#[cfg(feature = "sparse-cells")]
#[path = "root_directory.rs"]
mod root_directory;
pub use parent_epoch::Parents;
pub fn root(parents: &Parents, mut x: u64) -> u64 {
    while let Some(&y) = parents.get(&x) {
        if x == y {
            break;
        }
        x = y;
    }
    x
}
pub fn canon(v: &Value, p: &Parents) -> Value {
    match v {
        Value::Eq(x) => Value::Eq(root(p, *x)),
        Value::Set(xs) => {
            let mut xs = xs.iter().map(|x| canon(x, p)).collect::<Vec<_>>();
            xs.sort();
            xs.dedup();
            Value::Set(xs.into())
        }
        _ => v.clone(),
    }
}
pub fn integer(v: &Value) -> Result<i64, String> {
    if let Value::Int(x) = v {
        Ok(*x)
    } else {
        Err("expected integer".into())
    }
}
/// Shared checked integer semantics for execution and read-only Cell proofs.
#[inline]
pub(crate) fn checked_integer_binary(name: &str, a: i64, b: i64) -> Option<i64> {
    match name {
        "+" => a.checked_add(b),
        "-" => a.checked_sub(b),
        "*" => a.checked_mul(b),
        "/" => a.checked_div(b),
        "%" => a.checked_rem(b),
        "min" => Some(a.min(b)),
        "max" => Some(a.max(b)),
        _ => None,
    }
}
pub fn primitive(
    name: &str,
    args: &[Value],
    output: &str,
    nodes: &J,
) -> Result<Option<Value>, String> {
    if name.starts_with("cell-key-") {
        use eggfuse_structural_key::Key;
        let key = |i: usize| -> Result<&Key, String> {
            match args.get(i) {
                Some(Value::Key(k)) => Ok(k),
                _ => Err("expected structural key".into()),
            }
        };
        let v = match name {
            "cell-key-decode" => {
                let Value::Text(x) = &args[0] else {
                    return Err("key decode input".into());
                };
                return Ok(Key::decode_legacy(x).map(Value::Key));
            }
            "cell-key-min" => Value::Key(key(0)?.min(key(1)?).clone()),
            "cell-key-anchor" => Value::Key(key(0)?.clone().anchor()),
            "cell-key-cmp" => Value::Int(match key(0)?.cmp(key(1)?) {
                std::cmp::Ordering::Less => -1,
                std::cmp::Ordering::Equal => 0,
                std::cmp::Ordering::Greater => 1,
            }),
            "cell-key-prefer-left" => Value::Int(i64::from(
                integer(&args[0])? > integer(&args[1])?
                    || (integer(&args[0])? == integer(&args[1])? && key(2)? <= key(3)?),
            )),
            "cell-key-select" => {
                if integer(&args[2])? != 0 {
                    args[0].clone()
                } else {
                    args[1].clone()
                }
            }
            "cell-key-base-i64" => Value::Key(Key::base_i64(integer(&args[0])?)),
            "cell-key-base-f64" => {
                let Value::Float(x) = args[0] else {
                    return Err("float key input".into());
                };
                Value::Key(Key::base_f64(x.0 as u64))
            }
            "cell-key-base-String" => {
                let Value::Text(x) = &args[0] else {
                    return Err("string key input".into());
                };
                Value::Key(Key::base_string(x))
            }
            "cell-key-base-bool" => Value::Key(Key::new(
                format!("bool:{}", integer(&args[0])? != 0),
                vec![],
            )),
            "cell-key-base-Unit" => Value::Key(Key::new("Unit:()".into(), vec![])),
            _ => {
                let n = nodes
                    .as_array()
                    .and_then(|ns| ns.iter().find(|n| n["primitive"] == name))
                    .ok_or("undeclared key node primitive")?;
                if n["arity"].as_u64() != Some(args.len() as u64) {
                    return Err("key node arity".into());
                }
                Value::Key(Key::new(
                    n["label"].as_str().ok_or("key node label")?.into(),
                    (0..args.len())
                        .map(key)
                        .map(|x| x.cloned())
                        .collect::<Result<Vec<_>, _>>()?,
                ))
            }
        };
        return Ok(Some(v));
    }
    // Overloaded scalar operations dispatch on values whose types were checked
    // at admission. Keep the integer fast path and fallible query contract.
    if let Some(Value::Float(a)) = args.first() {
        let a = a.get();
        let b = match args.get(1) {
            Some(Value::Float(b)) => Some(b.get()),
            _ => None,
        };
        let v = match (name, b) {
            ("+", Some(b)) => Some(float((a + b).0)),
            ("-", Some(b)) => Some(float((a - b).0)),
            ("*", Some(b)) => Some(float((a * b).0)),
            ("/", Some(b)) => {
                return Ok((b.0 != 0.0).then(|| float((a / b).0)));
            }
            ("%", Some(b)) => {
                return Ok((b.0 != 0.0).then(|| float((a % b).0)));
            }
            ("^", Some(b)) => Some(float(a.0.powf(b.0))),
            ("min", Some(b)) => Some(float(a.min(b).0)),
            ("max", Some(b)) => Some(float(a.max(b).0)),
            ("<" | ">" | "<=" | ">=", Some(b)) => {
                let yes = match name {
                    "<" => a < b,
                    ">" => a > b,
                    "<=" => a <= b,
                    _ => a >= b,
                };
                return Ok(yes.then_some(Value::Int(0)));
            }
            ("neg", _) => Some(float(-a.0)),
            ("abs", _) => Some(float(a.0.abs())),
            ("to-i64", _) => Some(Value::Int(a.0 as i64)),
            ("to-string", _) => Some(Value::Text(format!("{:?}", a.0).into())),
            _ => None,
        };
        if let Some(v) = v {
            return Ok(Some(v));
        }
    }
    if name == "+" && output == "String" {
        let mut text = String::new();
        for arg in args {
            let Value::Text(s) = arg else {
                return Err("expected string".into());
            };
            text.push_str(s);
        }
        return Ok(Some(Value::Text(text.into())));
    }
    if name == "replace" || name == "count-matches" {
        let (Value::Text(a), Value::Text(b)) = (&args[0], &args[1]) else {
            return Err("expected strings".into());
        };
        return Ok(Some(if name == "count-matches" {
            Value::Int(a.matches(b.as_str()).count() as i64)
        } else {
            let Value::Text(c) = &args[2] else {
                return Err("expected string".into());
            };
            Value::Text(a.replace(b.as_str(), c.as_str()).into())
        }));
    }
    let name = name.strip_prefix("bool-").unwrap_or(name);
    let value = match name {
        "=" | "!=" | "value-eq" => {
            let yes = (args[0] == args[1]) == (name != "!=");
            if output == "Unit" {
                return Ok(yes.then_some(Value::Int(0)));
            }
            Value::Int(i64::from(yes))
        }
        "<" | "<=" | ">" | ">=" => {
            let a = integer(&args[0])?;
            let b = integer(&args[1])?;
            let yes = match name {
                "<" => a < b,
                "<=" => a <= b,
                ">" => a > b,
                _ => a >= b,
            };
            if output == "Unit" {
                return Ok(yes.then_some(Value::Int(0)));
            }
            Value::Int(i64::from(yes))
        }
        "+" | "-" | "*" | "/" | "%" | "min" | "max" => {
            let a = integer(&args[0])?;
            let b = integer(&args[1])?;
            let n = checked_integer_binary(name, a, b);
            let Some(n) = n else { return Ok(None) };
            Value::Int(n)
        }
        "&" | "|" | "^" | "<<" | ">>" => {
            let a = integer(&args[0])?;
            let b = integer(&args[1])?;
            let n = match name {
                "&" => Some(a & b),
                "|" => Some(a | b),
                "^" => Some(a ^ b),
                "<<" => u32::try_from(b).ok().and_then(|b| a.checked_shl(b)),
                _ => u32::try_from(b).ok().and_then(|b| a.checked_shr(b)),
            };
            return Ok(n.map(Value::Int));
        }
        "not-i64" => Value::Int(!integer(&args[0])?),
        "abs" => return Ok(integer(&args[0])?.checked_abs().map(Value::Int)),
        "log2" => {
            // Native egglog panics for nonpositive inputs: preserve an execution
            // error instead of silently turning it into a failed match.
            Value::Int(
                integer(&args[0])?
                    .checked_ilog2()
                    .ok_or("log2 requires a positive integer")? as i64,
            )
        }
        "to-f64" => float(integer(&args[0])? as f64),
        "to-string" => Value::Text(integer(&args[0])?.to_string().into()),
        "guard" => return Ok((integer(&args[0])? != 0).then_some(Value::Int(0))),
        "or" => {
            let mut yes = false;
            for arg in args {
                yes |= integer(arg)? != 0;
            }
            Value::Int(i64::from(yes))
        }
        "not" => Value::Int(i64::from(integer(&args[0])? == 0)),
        "and" | "xor" | "=>" | "implies" => {
            let a = integer(&args[0])? != 0;
            let b = integer(&args[1])? != 0;
            Value::Int(i64::from(match name {
                "and" => a && b,
                "xor" => a != b,
                _ => !a || b,
            }))
        }
        "set-of" | "set-empty" => {
            let mut xs = args.to_vec();
            xs.sort();
            xs.dedup();
            Value::Set(xs.into())
        }
        "set-insert" | "set-remove" => {
            let Value::Set(xs) = &args[0] else {
                return Err("set expected".into());
            };
            let mut xs = xs.as_ref().clone();
            if name == "set-insert" {
                xs.push(args[1].clone());
                xs.sort();
                xs.dedup()
            } else {
                xs.retain(|x| x != &args[1])
            }
            Value::Set(xs.into())
        }
        "set-union" | "set-intersect" | "set-diff" => {
            let (Value::Set(a), Value::Set(b)) = (&args[0], &args[1]) else {
                return Err("set expected".into());
            };
            let mut xs = if name == "set-union" {
                [a.as_slice(), b.as_slice()].concat()
            } else {
                a.iter()
                    .filter(|x| b.contains(x) == (name == "set-intersect"))
                    .cloned()
                    .collect()
            };
            xs.sort();
            xs.dedup();
            Value::Set(xs.into())
        }
        "set-contains" | "set-not-contains" => {
            let Value::Set(xs) = &args[0] else {
                return Err("set expected".into());
            };
            return Ok((xs.contains(&args[1]) == (name == "set-contains")).then_some(Value::Int(0)));
        }
        "set-length" => {
            let Value::Set(xs) = &args[0] else {
                return Err("set expected".into());
            };
            Value::Int(xs.len() as i64)
        }
        _ => return Err(format!("unsupported primitive {name}")),
    };
    Ok(Some(value))
}
pub fn literal(j: &J) -> Result<Value, String> {
    let kind = j["sort"]["kind"].as_str().ok_or("literal sort")?;
    let n = &j["literal"];
    Ok(match kind {
        "String" => Value::Text(n.as_str().ok_or("string literal")?.to_owned().into()),
        "f64" => Value::Float(FloatBits(n.as_i64().ok_or("float bits")?)),
        "i64" | "bool" | "Unit" => Value::Int(n.as_i64().ok_or("integer literal")?),
        _ => return Err(format!("unsupported literal {kind}")),
    })
}
pub fn exported(v: &Value, sort: &J) -> J {
    match v {
        Value::Eq(x) => json!({"sort":sort["name"],"eq":format!("Cell({x})")}),
        Value::Int(x) => json!({"sort":sort["name"],"value":x}),
        Value::Float(x) => json!({"sort":sort["name"],"value":x.key_bits() as i64}),
        Value::Text(x) => json!({"sort":sort["name"],"value":x}),
        Value::Set(xs) => {
            json!({"sort":sort["name"],"elements":xs.iter().map(|v|exported(v,&sort["element"])).collect::<Vec<_>>()})
        }
        Value::Key(k) => json!({"sort":sort["name"],"key":k.to_wire()}),
    }
}
