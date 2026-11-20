from pathlib import Path
import shutil

def install(crate):
    p=Path(crate)/'examples/joint_witness_session.rs';s=p.read_text()
    old='const FROZEN_BUNDLE_SETTINGS: Option<&str> = None;'
    if s.count(old)!=1:raise ValueError(old)
    shutil.copy2(Path(__file__).with_name('frozen-options.json'),p.with_name('frozen-options.json'))
    s=s.replace(old,'const FROZEN_BUNDLE_SETTINGS: Option<&str> = Some(include_str!("frozen-options.json"));')
    marker='    let args: Vec<_> = std::env::args_os().skip(1).collect();'
    if s.count(marker)!=1:raise ValueError(marker)
    s=s.replace(marker,marker+'''
    if let [flag,input,output]=args.as_slice() && flag=="--bake-port-codes"{
        let table=ordinary_witness::bake_port_codes(&std::fs::read(input)?)?;
        let mut file=std::fs::OpenOptions::new().create_new(true).write(true).open(output)?;
        file.write_all(&table)?;
        return Ok(());
    }''')
    p.write_text(s)
