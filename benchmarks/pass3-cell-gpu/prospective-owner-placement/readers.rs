// Build once for an immutable, settled boundary. It records only distinct consumer
// Cell identities; None represents a function row which is always external to the
// set of source Cell IDs. Once a real offer is found the ordinary full reader
// audit still captures physical references, columns, values and the repaired graph.
impl Graph {
    fn owner_trial_reader_index(&self) -> Result<TrialMap<u64, TrialSet<Option<u32>>>> {
        let mut users=TrialMap::<u64,TrialSet<Option<u32>>>::new();
        for t in 0..self.program.tables.len() {
            for d in self.witnesses(t) {
                let Some(row)=self.row(d)? else {continue};
                if row.hidden {continue;}
                let caller=match d {Dependency::Fact(f)=>Some(f.cell),Dependency::Function(_)=>None};
                for v in row.values.iter().take(row.values.len().saturating_sub(1)) {
                    if let Value::Eq(n)=v {users.entry(root(&self.parents,*n)).or_default().insert(caller);}
                }
            }
        }
        Ok(users)
    }

    fn trial_has_reader(&self, ids:&[u32],users:&TrialMap<u64,TrialSet<Option<u32>>>)->Result<bool> {
        for &id in ids {
            for op in self.cells.owner_ops(id) {
                let Some(row)=self.row(Dependency::Fact(FactRef{cell:id,op}))? else {continue};
                if !row.hidden && let Some(Value::Eq(n))=row.values.last()
                    && let Some(set)=users.get(&root(&self.parents,*n))
                    && set.iter().any(|caller|caller.is_none_or(|c|!ids.contains(&c))) {return Ok(true);}
            }
        }
        Ok(false)
    }
}
