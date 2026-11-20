"""Apply experiment-local hooks to a copy of the current native runtime and build its normal Cargo CLI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def change(path,old,new):
    s=path.read_text()
    if s.count(old)!=1:raise ValueError(f'{path.name}: expected one occurrence of {old}')
    path.write_text(s.replace(old,new))


def build(out):
    out.mkdir(parents=True,exist_ok=False)
    copy=out/'workspace';copy.mkdir()
    shutil.copytree(ROOT/'engine',copy/'engine',ignore=shutil.ignore_patterns('target','__pycache__'))
    shutil.copyfile(ROOT/'Cargo.lock',copy/'Cargo.lock')
    (copy/'Cargo.toml').write_text('[workspace]\nresolver="2"\nmembers=["engine/cell-runtime","engine/structural-key"]\n')
    src=copy/'engine/cell-runtime/src'
    files=['forest_policy.rs','precomputed_forest.rs','runtime.rs','stage_spine.rs','lib.rs']
    before={f:hashlib.sha256((src/f).read_bytes()).hexdigest() for f in files}
    shutil.copyfile(HERE/'variable_ports.rs',src/'variable_ports.rs')
    with (src/'lib.rs').open('a') as f:f.write('\n#[cfg(feature="precomputed-forest")]\nmod variable_ports;\n')
    p=src/'forest_policy.rs'
    change(p,'pub struct ForestPolicy {','pub struct ForestPolicy {\n    #[serde(default)] variable: Option<crate::variable_ports::Head>,')
    change(p,'pub struct ForestInputs {','pub struct ForestInputs {\n    #[serde(default)] variable: Option<crate::variable_ports::Plan>,')
    change(p,'        let packet = Packet {','''        let port_start=Instant::now();
        let variable=match (&model.variable,&inputs.variable){
            (Some(h),Some(p))=>Some(crate::variable_ports::State::emit(h,p,&parents,&mut children)?),
            (None,None)=>None,_=>return Err("variable-port policy and plan must be paired".into()),
        };
        let ports_ms=port_start.elapsed().as_secs_f64()*1000.;
        let packet = Packet {''')
    change(p,'self.install_forest_packet(packet, digest, residual)?;',
           'self.install_forest_packet(packet, digest, residual)?;\n        self.install_variable_ports(variable);')
    change(p,'"forward_ms":forward_ms','"forward_ms":forward_ms,"ports_ms":ports_ms')
    p=src/'runtime.rs';change(p,'    pub fn precomputed_report(&self)', '''    pub(crate) fn install_variable_ports(&mut self,s:Option<crate::variable_ports::State>){self.stage_spine.forest.as_mut().unwrap().variable=s;}
    #[cfg(feature="precomputed-forest")]
    pub fn precomputed_report(&self)''')
    p=src/'precomputed_forest.rs'
    change(p,'pub(crate) struct Forest {','pub(crate) struct Forest {\n    pub(crate) variable:Option<crate::variable_ports::State>,')
    change(p,'            published: BTreeMap::new(),','            variable:None,published: BTreeMap::new(),')
    change(p,'"rhs":self.ordinal,','"ports":self.variable.as_ref().map(|v|v.report()),"rhs":self.ordinal,')
    p=src/'stage_spine.rs'
    change(p,'                    cursor.forest_claim=forest_claim;','''                    cursor.forest_claim=forest_claim;
                    if let Some(id)=forest_claim{
                        let f=self.forest.as_mut().unwrap();
                        if let Some(v)=f.variable.as_mut() && !v.check(id,g,&rule,&known)?{
                            cursor.forest_claim=None;if !f.residual{continue 'answer;}
                        }
                    }
''')
    session=HERE/'port_session.rs'
    if session.exists():shutil.copyfile(session,src.parent/'examples/variable_certificate_session.rs')
    # The CLI is the native runtime used by the standard benchmark. Keep this executable separate from other experiments.
    target=out/'target';env=dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_INCREMENTAL='0')
    command=['cargo','build','--offline','--release','-p','eggfuse-cell-runtime','--features','precomputed-forest,slot-transfer-audit','--bin','eggfuse-cell-runtime']
    if session.exists():command+=['--example','variable_certificate_session']
    subprocess.run(command,cwd=copy,env=env,check=True)
    shutil.copyfile(target/'release/eggfuse-cell-runtime',out/'runtime');(out/'runtime').chmod(0o755)
    if session.exists():
        shutil.copyfile(target/'release/examples/variable_certificate_session',out/'session');(out/'session').chmod(0o755)
    sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    report=dict(features=['precomputed-forest','slot-transfer-audit'],base_git=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),upstream_sha256=before,
                patched_sha256={f:sha(src/f) for f in [*files,'variable_ports.rs']},binary_sha256=sha(out/'runtime'))
    (out/'build.json').write_text(json.dumps(report,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);build(p.parse_args().out)
