from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent


def edit(path,before,after):
    s=path.read_text()
    if s.count(before)!=1:raise ValueError((path,before))
    path.write_text(s.replace(before,after))


def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs'
    edit(p,'struct Store {','struct Store {fresh_mode:bool,static_entrances:Vec<Option<StaticEntrance>>,plan_counts:PlanCounts,')
    edit(p,'let s=Store{','let s=Store{fresh_mode:false,static_entrances:vec![],plan_counts:Default::default(),')
    old='let plan=s.plans[rid].as_ref().unwrap();let ins=plan.ins.clone();let width=plan.width;'
    edit(p,old,'let width=s.plans[rid].as_ref().unwrap().width;')
    edit(p,'        let mut remaining=vec![0;ins.len()+1];','''        let Some(ins)=s.select_entrance(g,rule,rid,mark)? else{return Ok(vec![])};
        let mut remaining=vec![0;ins.len()+1];''')
    edit(p,'json!({"shortlist":s.memo_counts,','json!({"fresh_entrance":s.plan_counts,"shortlist":s.memo_counts,')
    with p.open('a') as f:f.write('\ninclude!("fresh_entrances.rs");\n')
    shutil.copy2(HERE/'plans.rs',src/'fresh_entrances.rs')
    edit(crate/'examples/joint_witness_session.rs','        let initial_cells = runtime.graph.stats.cells_created;', '''        if let Some(mode)=req["entrance"].as_str(){ordinary_witness::configure_fresh_entrances(&program,mode)?;}
        let initial_cells = runtime.graph.stats.cells_created;''')
