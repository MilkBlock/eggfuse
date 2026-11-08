//! Reproducible constructor/Unit workloads; intentionally bypasses marker Bake.
//! Usage: cargo run --release -p eggfuse-cell-compiler --example
//! union_digest_fixture -- OUTPUT SHAPE GROUPS DEPTH
use eggfuse_cell_runtime::{compiler, program::Program};
use std::{collections::BTreeSet, fs, path::PathBuf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 4 {
        return Err("expected OUTPUT [unit-|warm-]chain|fanout|stable GROUPS DEPTH".into());
    }
    let out = PathBuf::from(&args[0]);
    let unit = args[1].starts_with("unit-");
    let warm = args[1].starts_with("warm-");
    let shape = args[1]
        .strip_prefix("warm-")
        .or_else(|| args[1].strip_prefix("unit-"))
        .unwrap_or(&args[1]);
    if !["chain", "fanout", "stable", "staged"].contains(&shape) || (warm && shape == "stable") {
        return Err("unknown shape".into());
    }
    let groups: usize = args[2].parse()?;
    let depth: usize = args[3].parse()?;
    if groups == 0 || depth == 0 {
        return Err("positive GROUPS and DEPTH required".into());
    }
    if shape == "staged" {
        return write_fixture(out, staged(groups, depth), BTreeSet::new());
    }
    let mut source = String::from("(datatype E (N i64) (Seed E E) (F i64 E) (Seen E))\n");
    if unit {
        source.push_str("(function Mark (i64 E E) Unit :merge old)\n(ruleset consume)\n");
    }
    source.push_str("(ruleset make) (ruleset alias) (ruleset read)\n(rule ((Seed a b)) (\n");
    for level in 0..depth {
        let left = if level == 0 || shape == "fanout" {
            "a".into()
        } else {
            format!("left{}", level - 1)
        };
        let right = if level == 0 || shape == "fanout" {
            "b".into()
        } else {
            format!("right{}", level - 1)
        };
        source.push_str(&format!(
            "(let left{level} (F {level} {left})) (let right{level} (F {level} {right}))\n"
        ));
    }
    source.push_str(") :ruleset make)\n");
    let other = if shape == "stable" { "a" } else { "b" };
    source.push_str(&format!(
        "(rule ((Seed a b)) ((union a {other})) :ruleset alias)\n"
    ));
    if unit {
        source.push_str("(rule ((= x (F i y))) ((set (Mark i y x) ())) :ruleset read)\n(rule ((Mark i y x)) ((Seen x)) :ruleset consume)\n");
    } else {
        source.push_str("(rule ((= x (F i y))) ((Seen x)) :ruleset read)\n");
    }
    for group in 0..groups {
        source.push_str(&format!("(Seed (N {}) (N {}))\n", 2 * group, 2 * group + 1));
    }
    if unit {
        source.push_str("(run-schedule (seq (run make) (run read) (run consume) (run alias) (run consume) (run read) (run consume)))\n");
    } else if warm {
        source.push_str("(run-schedule (seq (run make) (run read) (run alias) (run read)))\n");
    } else {
        source.push_str("(run-schedule (seq (run make) (run alias) (run read)))\n");
    }
    let markers = if unit {
        BTreeSet::from(["Mark".to_owned()])
    } else {
        BTreeSet::new()
    };
    write_fixture(out, source, markers)
}

fn write_fixture(
    out: PathBuf,
    source: String,
    markers: BTreeSet<String>,
) -> Result<(), Box<dyn std::error::Error>> {
    let core = eggfuse_bake::device_frontend::core("union-digest-fixture", &source)?;
    let artifact = compiler::compile(core, &markers)?;
    Program::parse(artifact.clone())?;
    fs::create_dir(&out)?;
    fs::write(out.join("source.egg"), source)?;
    fs::write(out.join("program.json"), serde_json::to_vec(&artifact)?)?;
    Ok(())
}

fn staged(groups: usize, depth: usize) -> String {
    let mut s = String::from(
        "(datatype E (N i64) (Seed E E E E) (Pair i64 E E) (Other i64 E E) (F E) (Seen E))\n(ruleset make) (ruleset left) (ruleset right) (ruleset read)\n(rule ((Seed a b c d)) (\n",
    );
    for i in 0..depth {
        s.push_str(&format!(
            "(F (Pair {i} a c)) (F (Pair {i} b d)) (F (Other {i} a c)) (F (Other {i} b d))\n"
        ));
    }
    s.push_str(") :ruleset make)\n(rule ((Seed a b c d)) ((union a b)) :ruleset left)\n(rule ((Seed a b c d)) ((union c d)) :ruleset right)\n(rule ((= x (F y))) ((Seen x)) :ruleset read)\n");
    for g in 0..groups {
        s.push_str(&format!(
            "(Seed (N {}) (N {}) (N {}) (N {}))\n",
            4 * g,
            4 * g + 1,
            4 * g + 2,
            4 * g + 3
        ));
    }
    s.push_str(
        "(run-schedule (seq (run make) (run read) (run left) (run read) (run right) (run read)))\n",
    );
    s
}
