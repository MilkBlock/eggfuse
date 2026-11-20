from pathlib import Path
from shutil import copyfile

HERE = Path(__file__).resolve().parent


def change(text, old, new):
    if text.count(old) != 1:
        raise ValueError(old)
    return text.replace(old, new)


def install(crate):
    path = crate / "src/ordinary_witness.rs"
    text = change(path.read_text(), "struct Store {", "struct Store {bridges:Bridges,")
    text = change(text, "let s=Store{", "let s=Store{bridges:Bridges::default(),")
    text = change(text, '"equations":s.equations.stats,', '"bridges":s.bridges.work,"equations":s.equations.stats,')
    start = '            if s.forward.config.is_some() && steps.len()>=3{'
    text = change(text, start, """            let used_bridge = s.emit_bridge(&c,&steps,&mut raw)?;
            if used_bridge {
                s.issued_generations.clear();
                s.issued_generations.extend(steps.iter().map(|d|d.frame.generation));
            } else {
""" + start)
    end = '        }else{s.descend(&c,0,p.clone(),&mut out,&mut raw)?;}'
    text = change(text, end, '            }\n'+end)
    path.write_text(text+'\ninclude!("connected_requests.rs");\n')
    copyfile(HERE / 'bridge.rs',path.with_name('connected_requests.rs'))
    path = crate / 'examples/joint_witness_session.rs'
    anchor = '        let initial_cells = runtime.graph.stats.cells_created;'
    path.write_text(change(path.read_text(),anchor,'''        if let Some(plans)=req.get("connected_requests") {
            ordinary_witness::configure_bridges(plans.clone(),req.get("bridge_memo").and_then(Value::as_bool).unwrap_or(false),
                req.get("bridge_directory").and_then(Value::as_bool).unwrap_or(false))?;
        }
'''+anchor))
