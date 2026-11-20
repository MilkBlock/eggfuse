"""Specialize an isolated native Rust checkout; public logical Set serialization remains identical."""
from pathlib import Path
import argparse,shutil
HERE=Path(__file__).resolve().parent

def once(s,x,y):
    if s.count(x)!=1:raise ValueError(x)
    return s.replace(x,y)

def prepare(tree):
    d=tree/'engine/cell-runtime/src';shutil.copy2(HERE/'set_storage.rs',d/'set_storage.rs')
    shutil.copy2(HERE/'heap.rs',tree/'engine/cell-runtime/examples/set_repr_heap.rs')
    p=d/'lib.rs';p.write_text(p.read_text()+'\npub mod set_storage;\n')
    p=d/'value.rs';s=p.read_text().replace('Set(std::sync::Arc<Vec<Value>>)','Set(std::sync::Arc<crate::set_storage::SetData>)')
    a=s.index('        Value::Set(xs) => {',s.index('pub fn canon('));b=s.index('        _ =>',a)
    s=s[:a]+'        Value::Set(xs) => crate::set_storage::canonical(xs,p),\n'+s[b:]
    a=s.index('        "set-of" | "set-empty" => {');b=s.index('        _ => return Err(format!("unsupported primitive',a)
    s=s[:a]+'''        "set-of"|"set-empty"|"set-insert"|"set-remove"|"set-union"|"set-intersect"|"set-diff"|
        "set-contains"|"set-not-contains"|"set-length" =>return crate::set_storage::primitive(name,args),
'''+s[b:]
    s=s.replace('xs.iter().map(|v|exported(v','xs.values().iter().map(|v|exported(v');p.write_text(s)
    p=d/'graph.rs';s=p.read_text().replace('return Ok(Value::Set(xs.into()));','return crate::set_storage::make(&xs);')
    s=s.replace('for x in xs.iter()','for x in xs.values().iter()').replace('Value::Set(items) => items.iter()', 'Value::Set(items) => items.values().iter()')
    a=s.index('    #[cfg(not(feature = "sparse-cells"))]\n    fn subscribe_edges(')
    i=s.index('        let mut refs = BTreeSet::new();',a)
    s=s[:i]+s[i:].replace('''        let mut refs = BTreeSet::new();
        for v in values {
            Self::refs''','''        let mut refs = BTreeSet::new();
        let grouped=crate::set_storage::subscribe(d,values,&self.parents);
        for v in values {
            if grouped && matches!(v,Value::Set(_)){continue;}
            Self::refs''',1)
    s=once(s,'        self.parents.insert(hi, lo);','''        if crate::set_storage::auditing_rows(){
            for w in self.uses.get(&hi).into_iter().flatten(){
                if let Some(row)=self.row(*w)? && row.values.iter().any(|v|match v{
                    Value::Set(s)=>s.values().iter().any(|v|matches!(v,Value::Eq(id) if root(&self.parents,*id)==hi)),_=>false}){
                    crate::set_storage::count_set_row();
                }
            }
        }
        self.parents.insert(hi, lo);''')
    marker='        let displaced = affected.len();'
    s=once(s,marker,'''        let mut wake=crate::set_storage::wake(hi,lo);
        wake.extend(affected.iter().copied());
'''+marker)
    s=once(s,'self.match_equality_digest(hi, lo, &affected)?','self.match_equality_digest(hi, lo, &wake)?')
    s=once(s,'self.mark_affected(&affected, hi, lo);','self.mark_affected(&wake, hi, lo);')
    p.write_text(s)
    for name in ('local_context.rs','entry_schedule.rs'):
        p=d/name;s=p.read_text().replace('Value::Set(s) => s.iter()','Value::Set(s) => s.values().iter()').replace('Value::Set(xs) => xs.iter()','Value::Set(xs) => xs.values().iter()');p.write_text(s)
    p=d/'main.rs';s=p.read_text().replace('    let mut report = runtime.report();','''    if let Some(problem)=eggfuse_cell_runtime::set_storage::fault(){return Err(problem.into());}
    let mut report = runtime.report();
    report["set_storage"]=eggfuse_cell_runtime::set_storage::report();''');p.write_text(s)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('tree',type=Path);prepare(p.parse_args().tree)
