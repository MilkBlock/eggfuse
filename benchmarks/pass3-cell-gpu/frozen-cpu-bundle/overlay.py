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
    old_settings='    let encoded = FROZEN_BUNDLE_SETTINGS.ok_or("unsupported compiled CPU bundle profile")?;\n    let options: Value = serde_json::from_str(encoded)?;'
    if s.count(old_settings)!=1:raise ValueError(old_settings)
    s=s.replace(old_settings,'''    let name=request["cpu_profile"].as_str().ok_or("invalid CPU bundle profile")?;
    let options=profile_options(name)?;
    // These fields only became executable when this binary linked the composed modules.
    if name=="frozen-ports/v1" && ["header_mode","derived_ports","lazy_equations"].iter().any(|k|request.get(k).is_some()) {
        return Err("composed settings are not part of the frozen profile".into());
    }''')
    anchor='        if one_shot && req["full_audit_report"] != true {'
    if s.count(anchor)!=1:raise ValueError(anchor)
    s=s.replace('let profile_work = req.get("cpu_profile")','let mut profile_work = req.get("cpu_profile")')
    s=s.replace(anchor,'''        if req["cpu_profile"]=="composed-ports/v1" && let Some(work)=&mut profile_work {
            work["published_header_updates"]=report["header_view"]["delta_updates"].clone();
            work["lazy_arithmetic_evaluations"]=report["multi"]["lazy_eq"]["computed"].clone();
            work["signature_cache_hits"]=report["multi"]["lazy_eq"]["table_hits"].clone();
        }
'''+anchor)
    comp='''    if args.first().is_some_and(|v|v=="--compile-bundle"){
        let usage="use --compile-bundle PROGRAM.json NEW_DIR [1703|1709] [--profile NAME]";
        if args.len()<3 {return Err(usage.into());}
        let mut extra=&args[3..];
        let mut seed=1703;
        if let Some(first)=extra.first() && first!="--profile" {
            seed=first.to_str().ok_or("invalid seed")?.parse::<u16>()?;
            extra=&extra[1..];
        }
        let profile=match extra {
            []=>"frozen-ports/v1",
            [flag,name] if flag=="--profile"=>name.to_str().ok_or("invalid profile name")?,
            _=>return Err(usage.into()),
        };
        return compile_frozen_bundle(Path::new(&args[1]),Path::new(&args[2]),seed,profile);
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
