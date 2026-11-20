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
    comp='''    if args.first().is_some_and(|v|v=="--compile-bundle"){
        let seed=match args.len(){
            3=>1703,4=>args[3].to_str().ok_or("invalid seed")?.parse::<u16>()?,
            _=>return Err("use --compile-bundle PROGRAM.json NEW_DIR [1703|1709]".into()),
        };
        return compile_frozen_bundle(Path::new(&args[1]),Path::new(&args[2]),seed);
    }'''
    s=s.replace(marker,marker+'\n'+comp)
    p.write_text(s+'\ninclude!("native_bundle.rs");\n')
    source=Path(__file__).resolve().parent
    shutil.copyfile(source/'native_bundle.rs',p.with_name('native_bundle.rs'))
    dst=p.parent/'frozen-weights';dst.mkdir()
    for seed in (1703,1709):
        for tag,rel in [('single',f'single-witness/certified-{seed}.json'),('multi',f'ordinary-witness/weights-{seed}.json'),('merge',f'joint-witness/weights/nested-{seed}.json')]:
            shutil.copyfile(source.parent/rel,dst/f'{tag}-{seed}.json')
    mod=Path(crate)/'src/ordinary_witness.rs'
    with mod.open('a') as f:f.write('\ninclude!("sealed_static_plan.rs");\n')
    shutil.copyfile(source/'sealed_plan.rs',mod.with_name('sealed_static_plan.rs'))
