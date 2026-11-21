"""Export committed internal-to-external links for attribution only."""
def install(crate):
    p=crate/"src/strict_named.rs"
    s=p.read_text()
    def sub(old,new):
        nonlocal s
        if s.count(old)!=1:raise ValueError(old)
        s=s.replace(old,new)
    sub('struct State {','struct State {\n    record_links:bool, links:Vec<[u64;3]>,')
    sub('let mut s = State {','let mut s = State {record_links:spec["record_links"]==true,')
    sub('        if let Some(internal) = s.issued.remove(&serial) {','''        if let Some(internal) = s.issued.remove(&serial) {
            if s.record_links { s.links.push([serial,internal.root,internal.path.len() as u64]); }
''')
    sub('json!({"availability":s.availability,"counts":s.stats,','json!({"links":s.links,"availability":s.availability,"counts":s.stats,')
    p.write_text(s)
