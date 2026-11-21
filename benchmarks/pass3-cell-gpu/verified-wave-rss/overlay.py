from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def change(s,old,new):
    if s.count(old)!=1: raise ValueError(old)
    return s.replace(old,new)

def driver(p,request,namespace):
    s=p.read_text()
    start='let start = Instant::now();'
    s=change(s,start,f'''let rss_window={request}["rss_file"].as_str().map(|x|{namespace}::Window::open(std::path::Path::new(x))).transpose()?;
        if let Some(w)=&rss_window{{w.begin();}}
        '''+start)
    stop='let ms = start.elapsed().as_secs_f64() * 1000.;'
    s=change(s,stop,stop+'\n        if let Some(w)=&rss_window{w.end();}')
    p.write_text(s)

def install(crate):
    src=crate/'src'
    copyfile(HERE/'window.rs',src/'rss_window.rs')
    p=src/'lib.rs';p.write_text(p.read_text()+'\npub mod rss_window;\n')
    p=src/'speculative_staging.rs';s=p.read_text()
    for key,tag in [('self.stats.granted += count;','granted'),('self.stats.used += 1;','redeemed'),('self.stats.unused += self.used_budget - self.seen;','expired')]:
        field=key.split()[0]
        s=change(s,key,key+f'\n        crate::rss_window::{tag}({field});')
    p.write_text(s)
    driver(crate/'examples/joint_witness_session.rs','req','eggfuse_cell_runtime::rss_window')
