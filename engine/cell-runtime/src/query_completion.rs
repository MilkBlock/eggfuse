//! Completion of one rule's actual query dependencies releases its winner
//! selection and RHS frame assembly. Unrelated rules keep using the Run reader.
use super::*;

#[cfg(feature="parallel-residuals")]
pub(super) type ChunkDone = (Vec<(usize, Binding)>, Option<((usize, bool, Dependency, usize), String)>, Counts,
    Option<usize>, expansion::ChunkWork, f64, Option<usize>);
#[cfg(not(feature="parallel-residuals"))]
pub(super) type ChunkDone = (Vec<(usize, Binding)>, Option<((usize, bool, Dependency, usize), String)>, Counts,
    Option<usize>, f64);

pub(super) enum Task<'a> {
    Point(&'a Chunk),
    #[cfg(feature="parallel-residuals")] Range(&'a entry_ranges::Chunk<'a>),
    #[cfg(feature="parallel-residuals")] Owned(&'a owned_ranges::Task<'a>),
    Ready(ready::Group<'a>),
    Finish(Finish<'a>),
}
pub(super) enum Event<'a> {
    Point(ChunkDone),
    #[cfg(feature="parallel-residuals")] Owned(owned_ranges::Done),
    Ready(ready::Group<'a>, ready::Work),
    Finish(Finish<'a>),
}

#[derive(Default)]
pub(crate) struct RuleDone {
    pub rule: usize,
    pub residual: Option<(usize, usize, usize)>, // candidates, prior rows, selected rows
    pub spine_previous: Option<usize>,
    pub dedup_rows: usize,
    pub dedup_duplicates: usize,
    pub final_len: usize,
    pub comparisons: u64,
    #[cfg(feature="parallel-residuals")]
    pub(super) merge: Option<expansion::MergeWork>,
}

pub(super) struct Finish<'a> {
    pub rule:usize,
    inputs:&'a [usize],
    rows:Vec<Binding>,
    selection:Option<crate::stage_spine::Selection>,
    #[cfg(feature="parallel-residuals")] merge:Option<expansion::PendingMerge>,
    done:RuleDone,
}
impl<'a> Finish<'a> {
    pub fn take(rule:usize,inputs:&'a [usize],rows:&mut Vec<Binding>,spine:&mut crate::stage_spine::Programs,
        #[cfg(feature="parallel-residuals")] output:Option<&mut expansion::Output>) -> Self {
        Self {rule,inputs,rows:std::mem::take(rows),selection:spine.take_worker_selection(rule),
            #[cfg(feature="parallel-residuals")] merge:output.and_then(expansion::Output::take_merge),
            done:RuleDone {rule,..Default::default()}}
    }
    pub fn size(&self)->usize {
        let n=self.rows.len()+self.selection.as_ref().map_or(0,|s|s.len());
        #[cfg(feature="parallel-residuals")] let n=n+self.merge.as_ref().map_or(0,|m|m.len());
        n
    }
    pub fn run(&mut self,pooled:bool) {
        if let Some(selection)=&mut self.selection {selection.select(self.inputs);self.done.comparisons=selection.comparisons;}
        #[cfg(feature="parallel-residuals")]
        if let Some(merge)=self.merge.take() {
            let (n,previous,selected,work)=merge.run(&mut self.rows,self.inputs,pooled);
            self.done.residual=Some((n,previous,selected));self.done.merge=Some(work);
        }
        #[cfg(not(feature="parallel-residuals"))] let _=pooled;
    }
    pub fn seal(mut self, rows:&mut Vec<Binding>,spine:&mut crate::stage_spine::Programs,
        #[cfg(feature="parallel-residuals")] output:Option<&mut expansion::Output>) -> Result<RuleDone> {
        #[cfg(feature="parallel-residuals")]
        if let Some((n,previous,_))=self.done.residual {output.unwrap().record_merge(n,previous);}
        if let Some(selection)=self.selection {
            let (complete,mut answers)=spine.seal_worker_selection(selection,self.inputs);
            self.done.spine_previous=Some(self.rows.len());answers.append(&mut self.rows);
            if !complete {
                if answers.iter().any(|a|self.inputs.iter().any(|s|!a.values.contains_key(s))) {return Err("incomplete binding".into());}
                self.done.dedup_rows=answers.len();
                answers.sort_by(|a,b|a.compare_inputs(b,self.inputs));
                answers.dedup_by(|a,b|a.compare_inputs(b,self.inputs).is_eq());
                self.done.dedup_duplicates=self.done.dedup_rows-answers.len();
            }
            self.rows=answers;
        }
        self.done.final_len=self.rows.len();*rows=self.rows;Ok(self.done)
    }
}
