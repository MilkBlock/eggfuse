from pathlib import Path
HERE=Path(__file__).resolve().parent
def install(crate):
    p=crate/'src/fresh_class_actor.rs'
    s=p.read_text()
    cut=s.index('struct ClassGate;')
    start=s.rindex('#[derive(Default)]',0,cut)
    assert 'fn observe' in s[cut:] and s[cut:].strip().endswith('}')
    p.write_text(s[:start]+(HERE/'gate.rs').read_text())
    p=crate/'src/adaptive_rows.rs';s=p.read_text()
    a='        self.rows.detailed = audit;'
    assert s.count(a)==1
    p.write_text(s.replace(a,a+'\n        self.class_gate.configure(&spec["fept_gate"])?;'))
    p=crate/'src/single_witness.rs';s=p.read_text()
    a='json!({"class_actor":self.class_counts,'
    assert s.count(a)==1
    p.write_text(s.replace(a,'json!({"fept_gate":self.class_gate.report(),"class_actor":self.class_counts,'))
