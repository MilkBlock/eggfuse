"""Record real externally issued multi-parent lanes by source rule after receiver dispatch."""
def replace(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)


def install(crate):
    p=crate/'src/pair_bucket_actor.rs';s=p.read_text()
    s=replace(s,'struct PairActor{','struct PairActor{\n    residual_by_rule:BTreeMap<usize,[u64;3]>,')
    p.write_text(s)
    p=crate/'src/ordinary_witness.rs';s=p.read_text()
    a='                    s.pair_actor.work.external_residual+=bank.count() as u64;'
    s=replace(s,a,a+'''
                    if s.detailed{
                        let r=s.pair_actor.residual_by_rule.entry(rid).or_default();
                        r[0]+=bank.count() as u64;r[1]+=1;r[2]+=(bank.count()*c.pick_count) as u64;
                    }
''')
    s=replace(s,'json!({"family_work":s.family.metrics,','json!({"pair_rule_issues":s.pair_actor.residual_by_rule,"family_work":s.family.metrics,')
    p.write_text(s)
