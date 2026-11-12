//! A single functional write has no constructor positions. Its committed
//! function row owns the immutable producer slots until it is superseded.
use super::*;
use crate::slots::FrameSlots as Slots;
#[derive(Clone, Debug)]
pub(super) struct Writer {
    pub template: usize,
    pub parent: Option<FactRef>,
    pub values: Slots,
    epoch: u64,
    pub completed: bool,
    pub depth: u32,
    prefix: usize,
}
#[derive(Default)]
pub(super) struct Directory {
    pages: Vec<Option<Box<Page>>>,
    pub live: usize,
    pub peak: usize,
    pub installations: u64,
    pub promoted: u64,
    pub general: u64,
}
struct Page {
    row: [u32; 512],
    count: usize,
}
impl Directory {
    pub(super) fn register(&mut self, index: usize, origin: FactRef) {
        self.insert(origin.cell, index as u32);
    }
    pub fn get(&self, id: u32) -> Option<usize> {
        let page = self.pages.get(id as usize / 512)?.as_ref()?;
        page.row[id as usize % 512]
            .checked_sub(1)
            .map(|x| x as usize)
    }
    fn insert(&mut self, id: u32, index: u32) {
        let i = id as usize / 512;
        if self.pages.len() <= i {
            self.pages.resize_with(i + 1, || None);
        }
        let page = self.pages[i].get_or_insert_with(|| {
            Box::new(Page {
                row: [0; 512],
                count: 0,
            })
        });
        debug_assert_eq!(page.row[id as usize % 512], 0);
        page.row[id as usize % 512] = index + 1;
        page.count += 1;
        self.live += 1;
        self.peak = self.peak.max(self.live);
        self.installations += 1;
    }
    fn remove(&mut self, id: u32) {
        let p = &mut self.pages[id as usize / 512];
        let page = p.as_mut().unwrap();
        debug_assert_ne!(page.row[id as usize % 512], 0);
        page.row[id as usize % 512] = 0;
        page.count -= 1;
        if page.count == 0 {
            *p = None;
        }
        self.live -= 1;
    }
}
impl Graph {
    pub(super) fn retire_unretained_writer(&mut self, origin: FactRef, parent: Option<FactRef>) {
        // Worker admission excludes inline writers as new parents, so an
        // unretained old writer cannot acquire readers during the batch.
        debug_assert_eq!(self.parent_users.get(&origin.cell).copied().unwrap_or(0), 0);
        self.writer_dir.remove(origin.cell);
        if let Some(parent) = parent { self.release_reference(parent); }
    }
    pub(super) fn writer(&self, id: u32) -> Option<&Writer> {
        self.functions
            .get(self.writer_dir.get(id)?)?
            .writer
            .as_deref()
    }
    pub(super) fn detach_origin(&mut self, index: usize) -> Option<Box<Writer>> {
        let previous = self.functions[index].origin.take()?;
        let writer = self.functions[index].writer.take();
        self.retire_writer(previous, writer)
    }
    pub(super) fn retire_writer(&mut self, previous: FactRef, writer: Option<Box<Writer>>) -> Option<Box<Writer>> {
        let Some(mut writer) = writer else {
            self.release_reference(previous);
            return None;
        };
        self.writer_dir.remove(previous.cell);
        if self.parent_users.get(&previous.cell).copied().unwrap_or(0) > 0 {
            // A client explicitly retained this producer as a parent. Its
            // original parent is already retained; transfer that hold.
            let c = Cell {
                template: writer.template,
                parent: writer.parent.take(),
                values: std::mem::take(&mut writer.values),
                facts: Default::default(),
                completed: writer.completed,
                completed_prefix: writer.prefix,
                recipe_depth: writer.depth,
                started_epoch: writer.epoch,
            };
            self.cells.insert(previous.cell, c);
            self.stats.cells_created += 1;
            self.writer_dir.promoted += 1;
        } else if let Some(p) = writer.parent {
            self.release_reference(p);
        }
        Some(writer)
    }
    pub(super) fn inline_writer(&mut self, index: usize, cell: u32, op: usize, frame: Cell) {
        let prior = self.detach_origin(index);
        self.install_writer(
            index,
            FactRef {
                cell,
                op: op as u32,
            },
            frame,
            prior,
        );
    }
    pub(super) fn install_writer(
        &mut self,
        index: usize,
        origin: FactRef,
        frame: Cell,
        prior: Option<Box<Writer>>,
    ) {
        if let Some(p) = frame.parent {
            self.retain_reference(p);
        }
        let state = Writer {
            template: frame.template,
            parent: frame.parent,
            values: frame.values,
            epoch: frame.started_epoch,
            depth: frame.recipe_depth,
            completed: frame.completed,
            prefix: frame.completed_prefix,
        };
        let writer = if let Some(mut b) = prior {
            *b = state;
            b
        } else {
            Box::new(state)
        };
        self.writer_dir.insert(origin.cell, index as u32);
        let f = &mut self.functions[index];
        f.writer = Some(writer);
        f.origin = Some(origin);
    }
}
impl Writer {
    pub(super) fn completed(template: usize, values: crate::slots::Slots, parent: Option<FactRef>, epoch: u64, prefix: usize) -> Self {
        Self { template, parent, values: values.into(), epoch, completed: true, depth: 0, prefix }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn replacing_a_retained_writer_preserves_the_old_immutable_slots() {
        let table = serde_json::json!({"name":"attr","schema":["i64","i64"],"constructor":false,"virtual_fact":false,"internal":false,"merge":{"var":"new"}});
        let p=serde_json::from_value(serde_json::json!({"multi_stage":crate::multistage::MultiStage::default(),"entry_schedule":crate::entry_schedule::Plan::default(),"tables":[table],"templates":[],"rules":[],"sets":{},"control":[],"initial":[],"table_templates":[],"artifact":{}})).unwrap();
        let mut g = Graph::new(p).unwrap();
        let key = [Value::Int(3)];
        let i = g.set_function_canonical(0, &key, Value::Int(1)).unwrap();
        let frame = |n| Cell {
            values: [(0, Value::Int(n))].into_iter().collect(),
            parent: None,
            template: 0,
            facts: Default::default(),
            completed: true,
            completed_prefix: 3,
            recipe_depth: 2,
            started_epoch: 4,
        };
        let a = FactRef { cell: 10, op: 2 };
        g.inline_writer(i, 10, 2, frame(7));
        g.retain_reference(a);
        assert_eq!(
            g.continuation_context(Dependency::Function(i))
                .unwrap()
                .depth,
            2
        );
        g.inline_writer(i, 11, 2, frame(8));
        assert_eq!(g.slot(10, 0).unwrap(), Value::Int(7));
        assert_eq!(g.slot(11, 0).unwrap(), Value::Int(8));
        g.release_reference(a);
        g.collect_garbage();
        assert!(g.slot(10, 0).is_err());
        assert_eq!(g.writer_dir.live, 1);
    }
}

#[cfg(feature="storage-metrics")]
impl Directory {
    pub(super) fn storage_bytes(&self)->usize {
        self.pages.capacity()*std::mem::size_of::<Option<Box<Page>>>()
        +self.pages.iter().flatten().count()*std::mem::size_of::<Page>()
    }
}
