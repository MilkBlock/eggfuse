"""Compile an isolated diagnostic, evict the payload cache and validate both direct layouts."""
import argparse,json,shutil,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('build','program','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    tree=a.out/'tree'
    subprocess.run(['cp','-cR',a.build/'tree',tree],check=True)
    crate=tree/'engine/cell-runtime'
    shutil.copyfile(HERE/'probe.rs',crate/'src/certificate_probe.rs')
    with (crate/'src/graph.rs').open('a') as f:f.write('\ninclude!("certificate_probe.rs");\n')
    (crate/'examples/certificate_probe.rs').write_text('''
use eggfuse_cell_runtime::{graph::{Graph,probe_certificate_layout},program::Program};
fn main()->Result<(),Box<dyn std::error::Error>>{
    let p=Program::parse(serde_json::from_slice(&std::fs::read(std::env::args_os().nth(1).ok_or("pass program.json")?)?)?)?;
    println!("{}",probe_certificate_layout(Graph::new(p)?)?);Ok(())
}
''')
    result=subprocess.run(['cargo','run','--locked','--offline','--release','-p','eggfuse-cell-runtime','--features','precomputed-forest,slot-transfer-audit','--example','certificate_probe','--target-dir',a.out/'target','--',a.program],
                          cwd=tree,check=True,stdout=subprocess.PIPE)
    out=json.loads(result.stdout);assert sorted(x[0] for x in out['observed'])==[3,4]
    (a.out/'probe.json').write_text(json.dumps(out,indent=1)+'\n')
