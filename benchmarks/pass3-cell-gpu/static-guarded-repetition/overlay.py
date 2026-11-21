from pathlib import Path

def replace(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)


def install(crate):
    p=crate/"src/strict_named.rs"
    s=p.read_text()
    s=replace(s,"struct State {","""struct State {
    // (producer rule, operation) pairs whose deterministic guard can be applied
    // again to that instruction's returned fact. Chosen before root issuance.
    repeat_ops:BTreeSet<(usize,usize)>,
    deeper:BTreeMap<usize,u64>,
""")
    s=replace(s,"if depth > 2 {",'if depth > 8 || (depth>2 && (spec["repeat"]!=true || spec.get("library").is_some())) {')
    a="                        s.next_at.entry((rid, op, *t)).or_default().push(c);"
    s=replace(s,a,a+'''
                        if rid==c && r.query.len()>1 && s.guarded.contains(&rid) {
                            s.repeat_ops.insert((rid,op));
                        }
''')
    a="            if path.len() > s.depth"
    s=replace(s,a,'''            if path.len()>2 && !s.repeat_ops.contains(&(a.rule,f.op as usize)){
                continue;
            }
'''+a)
    s=replace(s, "            s.stats.source_commits += 1;","            s.stats.source_commits += 1;*s.deeper.entry(internal.path.len()).or_default()+=1;")
    s=replace(s, 'json!({"guard_rules":','json!({"compiled_repeat_ops":s.repeat_ops,"commits_by_depth":s.deeper,"guard_rules":')
    p.write_text(s)
