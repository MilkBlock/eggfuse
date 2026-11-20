// Fields in this program are relative to the independently issued, ordered parent roles.
#[derive(Clone)]
enum BlockField {
    Parent(usize, usize),
    Previous(usize),
    Literal(Value),
}
impl BlockField {
    fn read(&self, g: &Graph, parents: &[Row], results: &[Value]) -> Value {
        match self {
            Self::Parent(j, col) => parents[*j].values[*col].clone(),
            Self::Previous(i) => results[*i].clone(),
            Self::Literal(v) => canon(v, &g.parents),
        }
    }
}
struct BlockStep {
    atom: usize,
    call: Call,
    keys: Vec<BlockField>,
    expected: Option<BlockField>,
    // One parent and the static literals determine the entire function key.
    parent_key: Option<usize>,
}
struct BlockTail {
    steps: Vec<BlockStep>,
    outputs: Vec<(usize, BlockField)>,
}
impl BlockTail {
    fn compile(
        rule: &Rule,
        plan: &Plan,
        parents: &BTreeMap<usize, (usize, usize)>,
        count: usize,
    ) -> Option<Self> {
        let mut slots: BTreeMap<_, _> = parents
            .iter()
            .map(|(slot, (j, col))| (*slot, BlockField::Parent(*j, *col)))
            .collect();
        let mut steps = vec![];
        for &(atom, pick, _) in &plan.ins[count..] {
            if pick != 0 {
                return None;
            }
            let a = &rule.query[atom];
            let (out, args) = a.args.split_last()?;
            let keys = args
                .iter()
                .map(|arg| match arg {
                    Arg::Slot(s) => slots.get(s).cloned(),
                    Arg::Literal(v) => Some(BlockField::Literal(v.clone())),
                })
                .collect::<Option<Vec<_>>>()?;
            let mut owner = None;
            let valid = keys.iter().all(|k| match k {
                BlockField::Literal(_) => true,
                BlockField::Parent(j, _) => {
                    let prev = *owner.get_or_insert(*j);
                    prev == *j
                }
                BlockField::Previous(_) => false,
            });
            let expected = match out {
                Arg::Slot(s) => {
                    let old = slots.get(s).cloned();
                    if old.is_none() {
                        slots.insert(*s, BlockField::Previous(steps.len()));
                    }
                    old
                }
                Arg::Literal(v) => Some(BlockField::Literal(v.clone())),
            };
            steps.push(BlockStep {
                atom,
                call: a.call.clone(),
                keys,
                expected,
                parent_key: if valid { owner } else { None },
            });
        }
        Some(Self {
            steps,
            outputs: slots.into_iter().collect(),
        })
    }
}
type PortMemo = SourceMap<(usize, Dependency, u64), Option<Row>>;
#[derive(Default, Serialize)]
struct BlockCounts {
    started: u64,
    completed: u64,
    stale: u64,
    key_misses: u64,
    guard_failures: u64,
    value_slots: u64,
    parent_port_hits: u64,
    parent_port_misses: u64,
    avoided_key_fields: u64,
    peak_ports: usize,
    negative_ports: u64,
}
impl Store {
    fn run_block(
        &mut self,
        c: &Context,
        plan: &PageProgram,
        rows: &[Row],
        mut epoch: u64,
        mut exact: Prefix,
        ports: &mut PortMemo,
        out: &mut Vec<Instance>,
    ) -> Result<()> {
        self.blocks.started += 1;
        let tail = &plan.tail;
        let mut results = smallvec::SmallVec::<[Value; 8]>::new();
        let mut witnesses = smallvec::SmallVec::<[(usize, Dependency); 8]>::new();
        let mut keys = PointKey::new();
        for (i, step) in tail.steps.iter().enumerate() {
            if c.rule.seminaive && epoch.max(c.remaining[c.pick_count + i]) < c.watermark {
                self.blocks.stale += 1;
                return Ok(());
            }
            let output = match &step.call {
                Call::Table(table) => {
                    let port = step
                        .parent_key
                        .filter(|_| self.premises.mode == 9)
                        .map(|j| (i, rows[j].witness, rows[j].epoch));
                    let row = if let Some(v) = port.as_ref().and_then(|key| ports.get(key)) {
                        self.blocks.parent_port_hits += 1;
                        self.blocks.avoided_key_fields += step.keys.len() as u64;
                        self.blocks.negative_ports += u64::from(v.is_none());
                        v.clone()
                    } else {
                        keys.clear();
                        keys.extend(step.keys.iter().map(|f| f.read(c.graph, rows, &results)));
                        let row = self.suffix_point(c.graph, *table, &keys)?.filter(|r| {
                            !r.hidden
                                && r.table == *table
                                && r.values.len() == keys.len() + 1
                                && r.values[..keys.len()] == keys[..]
                        });
                        if let Some(key) = port {
                            self.blocks.parent_port_misses += 1;
                            if ports.len() < 4096 {
                                ports.insert(key, row.clone());
                                self.blocks.peak_ports = self.blocks.peak_ports.max(ports.len());
                            }
                        }
                        row
                    };
                    let Some(row) = row else {
                        self.blocks.key_misses += 1;
                        return Ok(());
                    };
                    witnesses.push((step.atom, row.witness));
                    epoch = epoch.max(row.epoch);
                    row.values.last().ok_or("empty checked point")?.clone()
                }
                Call::Primitive(name, ty) => {
                    keys.clear();
                    keys.extend(step.keys.iter().map(|f| f.read(c.graph, rows, &results)));
                    self.counts.primitive_evals += 1;
                    let Some(v) = c.graph.primitive(name, &keys, ty)? else {
                        self.blocks.guard_failures += 1;
                        return Ok(());
                    };
                    v
                }
            };
            if let Some(want) = &step.expected
                && want.read(c.graph, rows, &results) != output
            {
                self.blocks.guard_failures += 1;
                return Ok(());
            }
            results.push(output);
        }
        if c.rule.seminaive && epoch < c.watermark {
            self.blocks.stale += 1;
            return Ok(());
        }
        // Only a complete checked tuple materializes a source binding.
        exact.witness.resize(c.rule.query.len(), None);
        for (r, parent) in plan.roles.iter().zip(rows) {
            exact.witness[r.atom] = Some(parent.witness);
        }
        for (atom, w) in witnesses {
            exact.witness[atom] = Some(w);
        }
        for (slot, f) in &tail.outputs {
            exact.slots.insert(*slot, f.read(c.graph, rows, &results));
        }
        exact.epoch = epoch;
        self.blocks.completed += 1;
        self.blocks.value_slots += tail.outputs.len() as u64;
        self.complete_source_binding(c, exact, out)
    }
}
