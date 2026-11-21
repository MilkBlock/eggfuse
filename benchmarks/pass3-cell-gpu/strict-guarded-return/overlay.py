from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def replace(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)

def install(crate):
    src=crate/"src";p=src/"strict_named.rs"
    s=p.read_text()
    s=replace(s,"struct State {","struct State {\n    guards:bool, guarded:BTreeSet<usize>, guard_counts:[u64;3],")
    s=replace(s,"let mut s = State {",'''let mut s = State {guards:spec["value_guards"]==true,''')
    a=s.index("            if !r.seminaive || r.query.len() != 1")
    b=s.index("            s.targets.entry(t)",a)
    s=s[:a]+'''            if !guarded_plan(r) {continue;}
            let a=&r.query[0];let Call::Table(t)=a.call else{unreachable!()};
            if !g.program.tables[t].constructor {continue;}
            let mut slots=BTreeSet::new();
            let simple=r.query.len()==1 && a.args.iter().all(|v|matches!(v,Arg::Slot(i) if slots.insert(*i)));
            if !simple {
                if !s.guards {continue;}
                s.guarded.insert(rid);
            }
'''+s[b:]
    a=s.index("            let mut input = Slots::default();")
    b=s.index("            ready.push",a)
    original=s[a:b]
    s=s[:a]+'''            let input=if s.guarded.contains(&rid) {
                s.guard_counts[0]+=1;
                let Some(value)=direct_inputs(g,rule,&row)? else{
                    guard_failed=true;
                    s.guard_counts[1]+=1;
                    continue;
                };
                s.guard_counts[2]+=1;value
            }else{
'''+original+'''                input
            };
'''+s[b:]
    s=replace(s,"        let mut live = 0;","        let mut guard_failed=false;\n        let mut live = 0;")
    s=replace(s,"if (!s.partial && live!=n) || ready.is_empty()", "if (!s.partial && (live!=n || guard_failed)) || ready.is_empty()")
    s=replace(s,"if live==n{s.stats.complete_banks", "if live==n && !guard_failed{s.stats.complete_banks")
    s=replace(s,'json!({"signed_commits":','json!({"guard_rules":s.guarded,"guard_counts":s.guard_counts,"signed_commits":')
    p.write_text(s+'\ninclude!("strict_return_guards.rs");\n')
    copyfile(HERE/'guard.rs',src/'strict_return_guards.rs')
    p=src/'stage_spine.rs';p.write_text(replace(p.read_text(),'if rule.query.len()!=1{return Err("strict Spine needs a sole pivot".into())}',
        'if !crate::strict_named::strict_pivot_only(rule){return Err("strict Spine requires its sole table to be its named pivot".into())}'))
    p=src/'strict_partial.rs';p.write_text(replace(p.read_text(),'|| p.order.len() != 0',
        '|| !crate::strict_named::strict_pivot_only(&g.program.rules[rid])'))
