"""Lift only sparse storage's compact canonical forward-dependency list into the ordinary graph."""
from pathlib import Path

def install(crate):
    s=crate/'src/graph.rs';text=s.read_text()
    tree='    #[cfg(not(feature = "sparse-cells"))]\n    dependencies: HashMap<Dependency, BTreeSet<u64>>,\n'
    compact='    #[cfg(feature = "sparse-cells")]\n    dependencies: HashMap<Dependency, smallvec::SmallVec<[u64; 3]>>,'
    if text.count(tree)!=1 or text.count(compact)!=1:raise ValueError('two expected forward representations')
    text=text.replace(tree,'').replace(compact,'    dependencies: HashMap<Dependency, smallvec::SmallVec<[u64; 3]>>,')
    old='    #[cfg(not(feature = "sparse-cells"))]\n    fn subscribe_edges('
    new='    #[cfg(feature = "sparse-cells")]\n    fn subscribe_edges('
    start=text.index(old);end=text.index(new,start)
    text=text[:start]+text[end:].replace(new,'    fn subscribe_edges(',1)
    s.write_text(text)

def metadata(crate):
    # Optional inspection only. The ordinary graph retains its exact ordered reverse-use set.
    driver=crate/'examples/joint_witness_session.rs';text=driver.read_text()
    key='        report["canon_work"]=';assert text.count(key)==1
    driver.write_text(text.replace(key,'        if req["inspect_subscriptions"]==true {report["subscriptions"]=runtime.graph.forward_subscription_census();}\n'+key))
    src=crate/'src/graph.rs'
    with src.open('a') as f:f.write("""
impl Graph {
    pub fn forward_subscription_census(&self)->J{
        let mut histogram=[0u64;7];let mut edges=0;
        for refs in self.dependencies.values(){histogram[refs.len().min(6)]+=1;edges+=refs.len();}
        json!({"native":self.maintenance_report(),"forward_histogram":histogram,"forward_edges":edges,
               "forward_hash_capacity":self.dependencies.capacity(),"reverse_hash_capacity":self.uses.capacity()})
    }
}
""")
