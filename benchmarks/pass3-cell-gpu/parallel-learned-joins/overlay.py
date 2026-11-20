from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent

def change(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise RuntimeError((p.name,a,s.count(a)))
    p.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs'
    change(p,'struct Store {','struct Store {workers:Workers,')
    change(p,'let s=Store{','let s=Store{workers:Workers::default(),')
    change(p,'"tier":s.tier.stats','"worker_join":s.workers.stats,"tier":s.tier.stats')
    change(p,'            if s.pair_mode>0 && steps.len()==2','            if s.parallel_issue(&c,&steps,slots,&mut raw)?{}else if s.pair_mode>0 && steps.len()==2')
    change(p,'        let issued=clock.map(|_|std::time::Instant::now());','        if s.workers.min_cost>0 && c.pick_count>=3{let cost=s.counts.approximate_visits-initial.2;let old=s.workers.cost.entry(rid).or_default();*old=cost.max(*old/2); }\n        let issued=clock.map(|_|std::time::Instant::now());')
    shutil.copy2(HERE/'join.rs',src/'worker_join.rs')
    shutil.copy2(HERE/'cache.rs',src/'worker_columns.rs')
    with p.open('a') as f:f.write('\ninclude!("worker_join.rs");\ninclude!("worker_columns.rs");\n')
    p=crate/'examples/joint_witness_session.rs'
    change(p,'        let initial_cells =','''        if let Some(x)=req.get("join_workers"){ordinary_witness::set_join_workers(x["workers"].as_u64().ok_or("missing workers")? as usize,x["min_roots"].as_u64().ok_or("missing threshold")? as usize,u8::try_from(x["fault"].as_u64().unwrap_or(0))?,x["cache_bytes"].as_u64().unwrap_or(0) as usize,x["grain"].as_u64().unwrap_or(1) as usize,x["local"].as_bool().unwrap_or(false),x["min_cost"].as_u64().unwrap_or(0))?;}
        let initial_cells =''')
