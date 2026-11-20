"""Build a scoped native runtime with a persistent Metal replica of published proof ports."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]

def replace(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:raise ValueError(f'{path}: source hook changed near {old}')
    path.write_text(text.replace(old,new))
def build(out):
    out.mkdir(parents=True,exist_ok=False);repo=out/'workspace';repo.mkdir()
    shutil.copytree(ROOT/'engine',repo/'engine',ignore=shutil.ignore_patterns('target','__pycache__'))
    shutil.copyfile(ROOT/'Cargo.lock',repo/'Cargo.lock')
    (repo/'Cargo.toml').write_text('[workspace]\nresolver="2"\nmembers=["engine/cell-runtime","engine/structural-key"]\n')
    crate=repo/'engine/cell-runtime';src=crate/'src'
    for f in ('sidecar.rs','sidecar.metal','bridge.m'):shutil.copyfile(HERE/f,src/f)
    original=(crate/'build.rs').read_text().replace('fn main()', 'fn ordinary()')
    (crate/'build.rs').write_text(original+'''
fn main(){
 ordinary();
 let out=std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
 let obj=out.join("ports.o");let lib=out.join("libdelta_ports.a");
 assert!(std::process::Command::new("xcrun").args(["--sdk","macosx","clang","-O3","-fobjc-arc","-c","src/bridge.m","-o"]).arg(&obj).status().unwrap().success());
 assert!(std::process::Command::new("ar").arg("rcs").arg(lib).arg(obj).status().unwrap().success());
 println!("cargo:rustc-link-search=native={}",out.display());
 println!("cargo:rustc-link-lib=static=delta_ports");println!("cargo:rustc-link-lib=framework=Metal");
 println!("cargo:rustc-link-lib=framework=Foundation");println!("cargo:rustc-link-lib=dylib=objc");
}
''')
    with (src/'lib.rs').open('a') as f:f.write('\nmod sidecar;\n')
    p=src/'precomputed_forest.rs'
    replace(p,'pub(crate) struct Forest {','pub(crate) struct Forest {\n    pub(crate) sidecar:Option<crate::sidecar::Sidecar>,')
    replace(p,'            published: BTreeMap::new(),','''            sidecar:std::env::var("EGGFUSE_PROOF_SIDECAR").ok().map(|mode|crate::sidecar::Sidecar::open(p,&packet,mode)).transpose()?,
            published: BTreeMap::new(),''')
    replace(p,'    pub(crate) fn propose_root(','''    pub(crate) fn sync_delta<F>(&mut self,g:&crate::graph::Graph,rules:&[usize],watermarks:&[u64],current:F)->Result<()>
        where F:Fn(crate::graph::Dependency)->Option<(usize,usize)>{
        if let Some(s)=&mut self.sidecar{s.epoch(g,rules,watermarks,&self.published,&self.used,current)?;}
        Ok(())
    }
    pub(crate) fn propose_root(''')
    replace(p,'"rhs":self.ordinal,','"sidecar":self.sidecar.as_ref().map(|s|s.report()),"rhs":self.ordinal,')
    p=src/'stage_spine.rs'
    replace(p,'    pub(crate) fn begin_step(','''    pub(crate) fn sync_proof_sidecar(&mut self,g:&Graph,rules:&[usize],wm:&[u64])->Result<()>{
        if let Some(f)=self.forest.as_mut(){
            let entries=&self.entries;
            f.sync_delta(g,rules,wm,|w|entries.get(&w).map(|cursor|{
                let (parent,effect,_)=cursor.cell_results();(parent,effect)
            }))?;
        }Ok(())
    }
    pub(crate) fn begin_step(''')
    start='            let forest_claim=self.forest.as_ref().and_then(|forest|{'
    insert='''            let mut forest_claim=self.forest.as_ref().and_then(|forest|{
                if forest.sidecar.is_some(){return forest.claim(cursor.producer,cursor.state.output,rid,pivot);}
'''
    replace(p,start,insert)
    needle='            if self.forest.as_ref().is_some_and(|f|!f.residual) && forest_claim.is_none(){continue;}'
    replace(p,needle,'''            if let Some(id)=forest_claim && let Some(checker)=self.forest.as_mut().and_then(|f|f.sidecar.as_mut()){
                if let Some(values)=checker.take(id,row.witness,rid,g)?{
                    let mut cursor=cursor;cursor.forest_claim=Some(id);
                    record_answer(&mut results,values,facts.with_rows([(pivot,row.witness)]),row.epoch,cursor);
                    continue 'answer;
                }
                forest_claim=None;
            }
            #[cfg(feature="precomputed-forest")]
'''+needle)
    p=src/'runtime.rs';replace(p,'        let (set_id, rules) = if let Some(sets) = &self.ready_sets {','''        if self.stage_spine.forest.as_ref().is_some_and(|f|f.sidecar.is_some()){
            let scheduled=self.graph.program.sets.get(set).ok_or("unknown ruleset")?;
            self.stage_spine.sync_proof_sidecar(&self.graph,scheduled,&self.watermarks)?;
        }
        let (set_id, rules) = if let Some(sets) = &self.ready_sets {''')
    replace(src/'forest_policy.rs','i64::from(active && c.direct),','if active && !c.direct {-2}else{i64::from(active && c.direct)},')
    shutil.copyfile(HERE/'cpu_session.rs',crate/'examples/sidecar_cpu_session.rs')
    replace(crate/'examples/native_forest_session.rs','"rhs":result["rhs"]','"sidecar":result["sidecar"],"rhs":result["rhs"]')
    env=dict(os.environ,CARGO_TARGET_DIR=str(out/'target'),CARGO_INCREMENTAL='0')
    subprocess.run(['cargo','build','--offline','--release','-p','eggfuse-cell-runtime','--features','precomputed-forest,slot-transfer-audit',
                    '--bin','eggfuse-cell-runtime','--example','native_forest_session','--example','sidecar_cpu_session'],cwd=repo,env=env,check=True)
    for a,b in [('eggfuse-cell-runtime','runtime'),('examples/native_forest_session','session'),('examples/sidecar_cpu_session','cpu_session')]:
        shutil.copy2(out/'target/release'/a,out/b)
    (out/'build.json').write_text(json.dumps(dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        binary=hashlib.sha256((out/'runtime').read_bytes()).hexdigest(),session=hashlib.sha256((out/'session').read_bytes()).hexdigest()),indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);build(p.parse_args().out)
