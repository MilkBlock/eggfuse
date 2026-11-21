"""Run the actual native header codec with both tag bits set on a synthetic valid-layout word."""
import argparse,os,subprocess,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE='''
mod program {pub type Result<T>=std::result::Result<T,String>;}
#[path="wire.rs"] mod codec;
fn main(){
    for spine in [1u64,508,0x7fff_ffff]{
        let source=0x89ab_cdef;
        let original=source|(spine<<32);
        for m in [false,true]{
            codec::configure(false,0).unwrap();
            let bytes=codec::pack(original as usize,m);
            assert_eq!(bytes,u64::to_le_bytes(original|((m as u64)<<63)));
            assert_eq!(codec::source(bytes),source as usize);
            assert_eq!(codec::spine(bytes),spine as usize);
            assert_eq!(codec::merge(bytes),m);
        }
    }
}
'''
def run(build):
    deps=build/'target/release/deps'
    lib=next(deps.glob('libserde_json-*.rlib'))
    with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
        tmp=Path(tmp);(tmp/'main.rs').write_text(SOURCE);(tmp/'wire.rs').write_bytes((HERE/'wire.rs').read_bytes())
        subprocess.run(['rustc','--edition=2024','-Awarnings','-L',f'dependency={deps}','--extern',f'serde_json={lib}',tmp/'main.rs','-o',tmp/'probe'],check=True)
        subprocess.run([tmp/'probe'],check=True)
    print('Native header codec retained source template and Spine code with the merge bit set and clear, including the maximum 31-bit Spine code.')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('build',type=Path);run(p.parse_args().build)
