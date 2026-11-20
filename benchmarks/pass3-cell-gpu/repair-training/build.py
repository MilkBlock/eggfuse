"""Create a private pinned-source Rust runtime. No shared runtime files are edited."""
import argparse
from pathlib import Path
import shutil,subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
REV='42edc376a33818b7a13c9760ef454c7bfb1b0bb3'
def build(out):
    out.mkdir(parents=True,exist_ok=True);mirror=out/'source';mirror.mkdir(exist_ok=True)
    archive=subprocess.Popen(['git','archive',REV,'engine/cell-runtime','engine/structural-key','Cargo.lock'],cwd=REPO,stdout=subprocess.PIPE)
    subprocess.run(['tar','-xf','-','-C',str(mirror)],stdin=archive.stdout,check=True)
    archive.stdout.close();assert archive.wait()==0
    (mirror/'Cargo.toml').write_text('[workspace]\nresolver="2"\nmembers=["engine/cell-runtime","engine/structural-key"]\n')
    crate=mirror/'engine/cell-runtime';graph=crate/'src/graph.rs';s=graph.read_text()
    anchor='    fn mark_affected(&mut self, affected: &UseSet, from: u64, to: u64) {\n        for d in affected.iter() {'
    assert s.count(anchor)==1
    s=s.replace(anchor,'    fn mark_affected(&mut self, affected: &UseSet, from: u64, to: u64) {\n        trial::begin_union(self.stats.unions,from,to);\n        for d in affected.iter() {\n            if let Dependency::Fact(f)=d && self.trial_result(*f,from,to,affected){trial::delivered(*d,true);continue;}')
    last='                self.dirty.insert(*d);'
    assert s.count(last)==1
    s=s.replace(last,last+'\n                trial::delivered(*d,false);')
    original='''            if !retained && self.repair_ports.is_some()
                && let Dependency::Fact(f) = d
                && self.finish_result_port(*f, from, to)
            {
                continue;
            }
'''
    assert s.count(original)==1
    # The trial already invoked this exact predicate if its issuer selected it.
    # An uncovered fact must remain in the ordinary ordered dirty-row path.
    s=s.replace(original,'')
    graph.write_text(s.replace('#[path = "union_digest.rs"]','#[path="repair_training.rs"]\npub mod trial;\n#[path = "union_digest.rs"]',1))
    shutil.copyfile(HERE/'trial.rs',crate/'src/repair_training.rs');shutil.copyfile(HERE/'session.rs',crate/'examples/repair_training_session.rs')
    subprocess.run(['cargo','build','--offline','--release','--manifest-path',str(crate/'Cargo.toml'),'--features','precomputed-forest,slot-transfer-audit','--example','repair_training_session','--target-dir',str(out/'target')],check=True)
    shutil.copyfile(out/'target/release/examples/repair_training_session',out/'session');(out/'session').chmod(0o755)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);build(p.parse_args().out)
