//! Finite, positive constructor completion. These graphs exist only while Bake
//! or the artifact checker runs. Runtime instances retain their ordinary slots.
use crate::{cell::{Definition, Site, Symbols}, iterative::Entry,
    program::{Arg, Call, Op, Program}, value::Value};
use serde::{Deserialize, Serialize};
use serde_json::{Value as Json, json};
use std::collections::{BTreeMap, BTreeSet};


#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize, Deserialize)]
struct Fact { table: usize, columns: Vec<usize> }

/// The key contains no local slot, instance, rule or derivation identifier.
/// Assumptions remain part of the contract; completed facts alone are not a
/// proof that two implementations have the same admissible entry.
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize, Deserialize)]
pub struct Structure {
    colors: Vec<String>,
    assumptions: Vec<Fact>,
    completed: Vec<Fact>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    terminal_unions: Vec<Fact>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Normalized {
    pub structure: Structure,
    pub ports: Vec<(usize, Site, Vec<usize>)>,
    #[serde(skip)]
    symbols: BTreeMap<usize, usize>,
}

#[derive(Default)]
struct Builder {
    eq: Symbols,
    colors: Vec<String>,
    literals: BTreeMap<Value, usize>,
    facts: Vec<Fact>,
    terminal_unions: Vec<Fact>,
    assumptions: Vec<Fact>,
    ports: Vec<(usize, Site, Vec<usize>)>,
}
impl Builder {
    fn fresh(&mut self, color: String) -> usize {
        let id = self.eq.fresh();
        debug_assert_eq!(id, self.colors.len());
        self.colors.push(color);
        id
    }
    fn arg(&mut self, arg: &Arg, slots: &[usize]) -> usize {
        match arg {
            Arg::Slot(s) => slots[*s],
            Arg::Literal(v) => {
                if let Some(&id) = self.literals.get(v) { return id; }
                let id = self.fresh(format!("literal:{}", serde_json::to_string(v).unwrap()));
                self.literals.insert(v.clone(), id);
                id
            }
        }
    }
    fn close(&mut self) {
        self.eq.close_constructors(self.facts.iter().map(|f|
            (f.table, &f.columns[..f.columns.len()-1], *f.columns.last().unwrap())));
    }
    fn relation(&mut self, table: usize, columns: Vec<usize>, assumption: bool) {
        let key = &columns[..columns.len()-1];
        let previous = self.facts.iter().find(|f| f.table == table
            && f.columns.len() == columns.len()
            && f.columns[..key.len()].iter().zip(key)
                .all(|(&a,&b)| self.eq.root(a) == self.eq.root(b)));
        if let Some(f) = previous {
            self.eq.equal(*f.columns.last().unwrap(), *columns.last().unwrap());
            // Ports retain every stage's addressing. The constructor relation
            // is already established: keep its existing representative rather
            // than replaying duplicate facts through each later closure.
            return;
        } else if assumption {
            self.assumptions.push(Fact { table, columns: columns.clone() });
        }
        self.facts.push(Fact { table, columns });
    }
    fn finish(self) -> Option<Normalized> {
        let used = self.facts.iter().chain(&self.terminal_unions).flat_map(|f| &f.columns)
            .map(|&s| self.eq.root(s)).collect::<BTreeSet<_>>();
        let roots = used.iter().copied().collect::<Vec<_>>();
        let ids = roots.iter().enumerate().map(|(i,&s)|(s,i)).collect::<BTreeMap<_,_>>();
        let project = |facts: &[Fact]| facts.iter().map(|f| Fact {
            table:f.table, columns:f.columns.iter().map(|&s|ids[&self.eq.root(s)]).collect()
        }).collect::<BTreeSet<_>>().into_iter().collect::<Vec<_>>();
        // Equality can identify an input with a literal. Its complete color is
        // the set of type/literal constraints, not whichever root ID survived.
        let mut colors = vec![BTreeSet::new(); roots.len()];
        for (s,color) in self.colors.iter().enumerate() {
            if let Some(&id)=ids.get(&self.eq.root(s)) { colors[id].insert(color.clone()); }
        }
        let colors = colors.into_iter().map(|c|serde_json::to_string(&c).unwrap()).collect();
        let raw = Structure { colors, assumptions:project(&self.assumptions), completed:project(&self.facts), terminal_unions:project(&self.terminal_unions) };
        let (structure, mapping) = canonical(raw)?;
        let map = |s|mapping[ids[&self.eq.root(s)]];
        Some(Normalized { structure,
            ports:self.ports.iter().map(|(stage,site,cols)|(*stage,*site,cols.iter().map(|&s|map(s)).collect())).collect(),
            symbols:(0..self.colors.len()).filter(|&s|used.contains(&self.eq.root(s)))
                .map(|s|(s,map(s))).collect() })
    }
}

/// Exact canonical labeling after color refinement. Symmetric cells are
/// enumerated only within a fixed compilation budget. Exceeding it declines
/// structural sharing rather than treating a digest or a partial coloring as
/// an isomorphism proof.
fn canonical(raw: Structure) -> Option<(Structure,Vec<usize>)> {
    fn colors(keys: Vec<String>) -> Vec<usize> {
        let sorted=keys.iter().cloned().collect::<BTreeSet<_>>();
        let ids=sorted.into_iter().enumerate().map(|(i,k)|(k,i)).collect::<BTreeMap<_,_>>();
        keys.iter().map(|k|ids[k]).collect()
    }
    let n=raw.colors.len();
    let mut labels=colors(raw.colors.clone());
    loop {
        let mut incidence=vec![vec![];n];
        for (role,facts) in [(0,&raw.assumptions),(1,&raw.completed),(2,&raw.terminal_unions)] {
            for f in facts {
                let adjacent=f.columns.iter().map(|&s|labels[s]).collect::<Vec<_>>();
                for (column,&s) in f.columns.iter().enumerate() {
                    incidence[s].push((role,f.table,column,adjacent.clone()));
                }
            }
        }
        let keys=incidence.into_iter().enumerate().map(|(i,mut edges)| {
            edges.sort(); serde_json::to_string(&(labels[i],edges)).unwrap()
        }).collect();
        let next=colors(keys);
        // Including the old color makes this a refinement, never a merge.
        let stable=(0..n).all(|i|(0..n).all(|j|(labels[i]==labels[j])==(next[i]==next[j])));
        labels=next;
        if stable { break; }
    }
    let mut groups=BTreeMap::<usize,Vec<usize>>::new();
    for (s,&label) in labels.iter().enumerate() { groups.entry(label).or_default().push(s); }
    let mut budget=1usize;
    for group in groups.values() {
        for i in 2..=group.len() { budget=budget.checked_mul(i)?; if budget>4096 { return None; } }
    }
    let groups=groups.into_values().collect::<Vec<_>>();
    let mut best:Option<(Structure,Vec<usize>)>=None;
    fn visit(raw:&Structure, groups:&[Vec<usize>], group:usize, order:&mut Vec<usize>, best:&mut Option<(Structure,Vec<usize>)>) {
        if group==groups.len() {
            let mut map=vec![0;order.len()];
            for (i,&s) in order.iter().enumerate() { map[s]=i; }
            let project=|facts:&[Fact]| facts.iter().map(|f|Fact{table:f.table,columns:f.columns.iter().map(|&s|map[s]).collect()})
                .collect::<BTreeSet<_>>().into_iter().collect();
            let candidate=Structure { colors:order.iter().map(|&s|raw.colors[s].clone()).collect(),
                assumptions:project(&raw.assumptions),completed:project(&raw.completed), terminal_unions:project(&raw.terminal_unions) };
            if best.as_ref().is_none_or(|(b,_)|candidate<*b) { *best=Some((candidate,map)); }
            return;
        }
        fn permute(raw:&Structure,groups:&[Vec<usize>],g:usize,values:&mut [usize],i:usize,
            order:&mut Vec<usize>,best:&mut Option<(Structure,Vec<usize>)>) {
            if i==values.len() {
                let start=order.len(); order.extend_from_slice(values);
                visit(raw,groups,g+1,order,best); order.truncate(start); return;
            }
            for j in i..values.len() { values.swap(i,j); permute(raw,groups,g,values,i+1,order,best); values.swap(i,j); }
        }
        permute(raw,groups,group,&mut groups[group].clone(),0,order,best);
    }
    visit(&raw,&groups,0,&mut vec![],&mut best);
    best
}

/// Supported paths have immutable constructor facts and optional ordered
/// terminal Union obligations, which do not feed constructor closure. The source
/// scheduler still owns rule/Run order. A finite constructor fixed point is not
/// a claim that every rule in the source program has saturated.
pub(crate) fn normalize(p:&Program,path:&[(Option<usize>,Entry)]) -> Option<Normalized> {
    let mut b=Builder::default();
    let mut published=Vec::new();
    for (stage,&(_, (rid,pivot))) in path.iter().enumerate() {
        let cell=Definition::new(p,rid).ok()?;
        if cell.rule.query.iter().any(|a|!matches!(a.call,Call::Table(t) if p.tables[t].constructor && p.tables[t].virtual_fact))
            || cell.template.ops.iter().any(|op|!matches!(op,Op::Copy(..)|Op::Let(_,Call::Table(_),_)|Op::Union(..))) { return None; }
        // Type identity must not depend on serde_json's object iteration
        // order. The native compiler enables preserve_order transitively,
        // whereas the standalone runtime can deserialize the same schema
        // into sorted maps. Use the shared artifact encoding on both sides.
        let mut slots=cell.template.sorts.iter().map(|sort|
            b.fresh(format!("sort:{}",crate::checksum::canonical(sort,false)))
        ).collect::<Vec<_>>();
        if stage!=0 {
            let relation=cell.relation(Site::Query(pivot?))?;
            let columns=relation.columns().collect::<Vec<_>>();
            if columns.len()!=published.len() { return None; }
            for (arg,col) in columns.into_iter().zip(published.drain(..)) {
                let into=b.arg(arg,&slots); b.eq.equal(into,col);
            }
        }
        for atom in 0..cell.rule.query.len() {
            let relation=cell.relation(Site::Query(atom))?;
            let columns=relation.columns().map(|a|b.arg(a,&slots)).collect::<Vec<_>>();
            b.ports.push((stage,Site::Query(atom),columns.clone()));
            b.relation(relation.table,columns,true);
        }
        b.close();
        for (op,ins) in cell.template.ops.iter().enumerate() {
            if let Op::Copy(dst,arg)=ins { slots[*dst]=b.arg(arg,&slots); continue; }
            if let Op::Union(a,c)=ins {
                // RHS unions are queued until the source boundary, so later
                // constructors still use pre-Union congruence. Keep these
                // final-stage equalities as ordered obligations,
                // never as entry assumptions or constructor congruence.
                let a=b.arg(a,&slots); let c=b.arg(c,&slots);
                b.close();
                if b.eq.root(a)!=b.eq.root(c) {
                    if stage+1!=path.len() { return None; }
                    b.terminal_unions.push(Fact {table:b.terminal_unions.len(),columns:vec![a,c]});
                }
                continue;
            }
            let relation=cell.relation(Site::Effect(op))?;
            if !p.tables[relation.table].constructor || !p.tables[relation.table].virtual_fact { return None; }
            let columns=relation.columns().map(|a|b.arg(a,&slots)).collect::<Vec<_>>();
            if path.get(stage+1).is_some_and(|s|s.0==Some(op)) { published=columns.clone(); }
            b.ports.push((stage,Site::Effect(op),columns.clone()));
            b.relation(relation.table,columns,false);
        }
        b.close();
    }
    b.finish()
}

/// Structural sharing across pending Union boundaries. Each stage keeps its
/// own pre-commit symbols; links identify actual publication/query ports.
/// This is not a cross-boundary Eq proof or an executable completion plan.
pub(crate) fn staged_contract(p: &Program, path: &[(Option<usize>, Entry)]) -> Option<Json> {
    if path.len() < 2 { return None; }
    let stages = path.iter().map(|&(_,entry)| normalize(p,&[(None,entry)]))
        .collect::<Option<Vec<_>>>()?;
    let mut links = vec![];
    for stage in 1..path.len() {
        let source = Site::Effect(path[stage].0?);
        let target = Site::Query(path[stage].1.1?);
        let left = Definition::new(p,path[stage-1].1.0).ok()?.relation(source)?;
        let right = Definition::new(p,path[stage].1.0).ok()?.relation(target)?;
        if left.table != right.table { return None; }
        let ports = |n: &Normalized, site| n.ports.iter()
            .find(|(_,s,_)|*s==site).map(|(_,_,cols)|cols.clone());
        let from = ports(&stages[stage-1],source)?;
        let to = ports(&stages[stage],target)?;
        if from.len()!=to.len() { return None; }
        links.push(json!({"table":left.table,"from":from,"to":to}));
    }
    Some(json!({"normalization":"staged-lazy-union/v1",
        "stages":stages.iter().map(|n| &n.structure).collect::<Vec<_>>(),
        "links":links,"effects":"ordered-at-original-source-boundary"}))
}

/// A checked inclusion map comes from the very same symbolic prefix, never
/// from runtime numbering or probabilistic membership. New assumptions are
/// explicit and must still be matched by the consumer.
pub(crate) fn extension(before:&Normalized,after:&Normalized) -> Option<Json> {
    if !before.structure.terminal_unions.is_empty() { return None; }
    let mut mapping=BTreeMap::new();
    for (&symbol,&source) in &before.symbols {
        let target=*after.symbols.get(&symbol)?;
        if mapping.insert(source,target).is_some_and(|old|old!=target) { return None; }
    }
    let map=(0..before.structure.colors.len()).map(|s|mapping.get(&s).copied()).collect::<Option<Vec<_>>>()?;
    let project=|f:&Fact|Fact{table:f.table,columns:f.columns.iter().map(|&s|map[s]).collect()};
    if !before.structure.completed.iter().all(|f|after.structure.completed.binary_search(&project(f)).is_ok()) { return None; }
    Some(json!({"ports":map,"completed_inclusion":true,"entry_assumptions":"consumer-match-required"}))
}

#[cfg(test)]
mod tests {
    #[test]
    fn repeated_completed_relations_share_one_fact_but_keep_stage_ports() {
        let mut compact = Builder::default();
        let mut expanded = Builder::default();
        for b in [&mut compact, &mut expanded] { b.fresh("E".into()); }
        for stage in 0..64 {
            for b in [&mut compact, &mut expanded] {
                let output = b.fresh("E".into());
                b.relation(0,vec![0,output],stage==0);
                b.ports.push((stage,Site::Effect(0),vec![0,output]));
                b.close();
            }
            // Reproduce the old retained duplicate, after its equality proof.
            if stage != 0 {
                expanded.facts.push(Fact {table:0,columns:vec![0,stage+1]});
            }
        }
        assert_eq!(compact.facts.len(),1);
        assert_eq!(expanded.facts.len(),64);
        assert_eq!(compact.assumptions.len(),1);
        let a=compact.finish().unwrap(); let b=expanded.finish().unwrap();
        assert_eq!(a.structure,b.structure);
        assert_eq!(a.ports,b.ports);
        assert_eq!(a.symbols,b.symbols);
        assert_eq!(a.ports.len(),64);
    }

    use super::*;
    fn shape(reverse:bool, crossed:bool, assumed:bool) -> Normalized {
        let mut b=Builder::default();
        let mut v=(0..5).map(|_|b.fresh("E".into())).collect::<Vec<_>>();
        if reverse { v.reverse(); }
        b.relation(0,vec![v[0],v[1]],true);
        let mut rows=vec![(1,vec![v[1],v[2]]),(2,vec![v[1],v[3]]),
            (3,vec![if crossed {v[3]} else {v[2]},v[3],v[4]])];
        if reverse { rows.reverse(); }
        for (table,columns) in rows { b.relation(table,columns,assumed); }
        b.close(); b.finish().unwrap()
    }
    #[test]
    fn names_and_independent_apply_order_do_not_identify_a_cell() {
        assert_eq!(shape(false,false,false).structure,shape(true,false,false).structure);
        assert_ne!(shape(false,false,false).structure,shape(true,true,false).structure);
        assert_ne!(shape(false,false,false).structure,shape(true,false,true).structure);
    }
    #[test]
    fn terminal_union_order_is_not_entry_equality() {
        let build = |reverse: bool| {
            let mut b=Builder::default();
            let x=b.fresh("x".into()); let y=b.fresh("y".into()); let z=b.fresh("z".into());
            b.relation(0,vec![x,y],true);
            let pairs=if reverse {vec![vec![y,z],vec![x,y]]} else {vec![vec![x,y],vec![y,z]]};
            b.terminal_unions=pairs.into_iter().enumerate().map(|(table,columns)|Fact {table,columns}).collect();
            b.finish().unwrap()
        };
        let a=build(false); let b=build(true);
        assert_ne!(a.structure,b.structure);
        assert_eq!(a.structure.colors.len(),3,"terminal equalities must not collapse entry ports");
        assert!(extension(&a,&a).is_none(),"post-Union prefix inheritance is not supported");
    }

    #[test]
    fn symmetric_ports_are_exact_and_bounded() {
        let raw=Structure{colors:vec!["E".into();9],assumptions:vec![],completed:vec![],terminal_unions:vec![]};
        assert!(canonical(raw).is_none(),"decline rather than silently identify a symmetric cell");
        let mut a=Builder::default();
        let x=a.fresh("E".into()); let y=a.fresh("E".into());
        a.relation(0,vec![x,y],true); a.ports.push((0,Site::Query(0),vec![x,y]));
        let before=a.finish().unwrap();
        let mut b=Builder::default();
        let x=b.fresh("E".into()); let y=b.fresh("E".into()); let z=b.fresh("E".into());
        b.relation(0,vec![x,y],true); b.relation(1,vec![y,z],false);
        b.close(); let after=b.finish().unwrap();
        assert_eq!(extension(&before,&after).unwrap()["completed_inclusion"],true);
        assert!(extension(&after,&before).is_none());
    }
}
