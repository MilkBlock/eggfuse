//! Compare saved reports with the same work ledger used by Bake admission.
#[path = "../src/work_credit.rs"]
mod work_credit;
use std::fs;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let [before, after, output] = args.as_slice() else {
        return Err("expected BEFORE_REPORT AFTER_REPORT OUTPUT.json".into());
    };
    let read = |path| -> Result<work_credit::Work, Box<dyn std::error::Error>> {
        Ok(work_credit::Work::read(&serde_json::from_slice(&fs::read(path)?)?)?)
    };
    let (_, evidence) = read(before)?.savings(&read(after)?);
    fs::write(output, serde_json::to_vec_pretty(&evidence)?)?;
    Ok(())
}
