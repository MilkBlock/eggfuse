// A transaction is scoped to one rule occurrence and one immutable Graph borrow.
// Prefixes in the buffer already carry their own sealed recipe and actual parent proofs.
#[derive(Default, Serialize)]
struct RequestStats {
    eligible_rules: usize,
    raw_batches: u64,
    collect_ns: u64,
    max_collect_ns: u64,
    execute_ns: u64,
    parent_reads: u64,
    reused_parents: u64,
    flushes: u64,
    lanes: u64,
    peak_lanes: usize,
    reads: u64,
    evaluations: u64,
    reused_rows: u64,
    reused_scalars: u64,
    survivors: u64,
    deferred_lane_pairs: u64,
}
#[derive(Default)]
struct Transactions {
    width: usize,
    share: bool,
    tables_only: bool,
    streaming: bool,
    parent_reads: bool,
    profile: bool,
    opened: Option<std::time::Instant>,
    audit: bool,
    audit_streams: BTreeMap<(usize, usize), Sha256>,
    eligible: Vec<bool>,
    stats: RequestStats,
}
impl Transactions {
    fn width_for(&self, rule: usize) -> usize {
        if self.eligible.get(rule) == Some(&true) {
            self.width
        } else {
            0
        }
    }
}

// Restrict arithmetic to operations with integer output or comparison guards.
// Other scalar programs can intern float representations in encounter order.
fn read_only_request(call: &Call) -> bool {
    match call {
        Call::Table(_) => true,
        Call::Primitive(name, output) => match output.as_str() {
            "i64" => matches!(name.as_str(), "+" | "-" | "*" | "min" | "max"),
            "Unit" => matches!(
                name.as_str(),
                "<" | ">" | "<=" | ">=" | "=" | "!=" | "value-eq"
            ),
            _ => false,
        },
    }
}

pub fn configure_transactions(
    program: &Program,
    width: u64,
    share: bool,
    share_parents: bool,
    tables_only: bool,
    streaming: bool,
    profile: bool,
) -> Result<()> {
    if width > 128 {
        return Err("request batch exceeds 128".into());
    }
    STORE.with_borrow_mut(|cell| {
        let s = cell
            .as_mut()
            .ok_or("request transactions require a sealed proposer")?;
        if s.accel != 4 || !s.seal {
            return Err("request transactions require sealed stack parents".into());
        }
        let eligible: Vec<_> = s
            .plans
            .iter()
            .zip(&program.rules)
            .map(|(p, r)| {
                let Some(p) = p else {
                    return false;
                };
                let suffix = &p.ins[p.ins.iter().take_while(|t| t.1 == 1).count()..];
                !suffix.is_empty()
                    && suffix.iter().all(|(atom, pick, _)| {
                        *pick == 0 && read_only_request(&r.query[*atom].call)
                    })
            })
            .collect();
        s.transactions.stats.eligible_rules = eligible.iter().filter(|&&ready| ready).count();
        s.transactions.width = width as usize;
        s.transactions.eligible = eligible;
        s.transactions.share = share;
        s.transactions.audit = s.detailed;
        s.transactions.tables_only = tables_only;
        s.transactions.streaming = streaming;
        s.transactions.parent_reads = share_parents;
        s.transactions.profile = profile;
        Ok(())
    })
}

#[derive(Serialize)]
enum AnswerReceipt<'a> {
    Read(Option<(usize, Dependency, u64, bool, &'a [Value])>),
    Scalar(Option<&'a Value>),
}
impl<'a> AnswerReceipt<'a> {
    fn read(row: Option<&'a Row>) -> Self {
        Self::Read(row.map(|r| (r.table, r.witness, r.epoch, r.hidden, &r.values[..])))
    }
}
impl Transactions {
    fn record(&mut self, rule: usize, atom: usize, input: Vec<u8>, result: AnswerReceipt<'_>) {
        let hash = self.audit_streams.entry((rule, atom)).or_default();
        for item in [
            input,
            serde_json::to_vec(&result).expect("serializable answer"),
        ] {
            hash.update((item.len() as u64).to_le_bytes());
            hash.update(item);
        }
    }
    fn digest(&self) -> Option<String> {
        if !self.audit {
            return None;
        }
        let mut all = Sha256::new();
        for ((rule, atom), stream) in &self.audit_streams {
            all.update((*rule as u64).to_le_bytes());
            all.update((*atom as u64).to_le_bytes());
            all.update(stream.clone().finalize());
        }
        Some(format!("{:x}", all.finalize()))
    }
}
fn request_input(run: usize, c: &Context<'_>, p: &Prefix, args: &[Value]) -> Vec<u8> {
    serde_json::to_vec(&(run, c.graph.epoch, c.watermark, &p.anchors, args))
        .expect("serializable typed request")
}

enum Answer {
    Read(Option<Row>),
    Scalar(Option<Value>),
}

type AnswerMap = rustc_hash::FxHashMap<smallvec::SmallVec<[Value; 2]>, Answer>;
impl Store {
    fn flush_requests(
        &mut self,
        c: &Context<'_>,
        pending: &mut Vec<Prefix>,
        cache: &mut Vec<AnswerMap>,
        out: &mut Vec<Instance>,
    ) -> Result<()> {
        let n = pending.len();
        let start = self.transactions.opened.take().map(|opened| {
            let start = std::time::Instant::now();
            let elapsed = start.duration_since(opened).as_nanos() as u64;
            self.transactions.stats.collect_ns += elapsed;
            self.transactions.stats.max_collect_ns =
                self.transactions.stats.max_collect_ns.max(elapsed);
            start
        });
        let stats = &mut self.transactions.stats;
        stats.flushes += 1;
        stats.lanes += n as u64;
        stats.peak_lanes = stats.peak_lanes.max(n);
        stats.deferred_lane_pairs += (n * (n - 1) / 2) as u64;
        let mut lanes = std::mem::take(pending);
        let mut keep = Vec::with_capacity(n);
        if cache.is_empty() {
            cache.resize_with(c.inst.len() - c.pick_count, AnswerMap::default);
        }
        for step in c.pick_count..c.inst.len() {
            let id = c.inst[step].0;
            let atom = &c.rule.query[id];
            let answers = &mut cache[step - c.pick_count];
            let share_step = self.transactions.share
                && self.transactions.width > 1
                && (!self.transactions.tables_only || matches!(atom.call, Call::Table(_)));
            for mut lane in lanes.drain(..) {
                if c.rule.seminaive && lane.epoch.max(c.remaining[step]) < c.watermark {
                    self.counts.stale_candidates += 1;
                    continue;
                }
                let args = atom.args[..atom.args.len() - 1]
                    .iter()
                    .map(|a| value(a, c.graph, &lane))
                    .collect::<Option<smallvec::SmallVec<[Value; 2]>>>()
                    .ok_or("unbound transaction operand")?;
                // Avoid the equality conventions of float keys and containers when sharing payloads.
                let shared = share_step
                    && args
                        .iter()
                        .all(|v| matches!(v, Value::Int(_) | Value::Eq(_)));
                let input = self
                    .transactions
                    .audit
                    .then(|| request_input(self.run, c, &lane, &args));
                let evaluate = |args: &[Value], store: &mut Self| -> Result<Answer> {
                    match &atom.call {
                        Call::Table(table) => {
                            store.transactions.stats.reads += 1;
                            store.counts.point_reads += 1;
                            Ok(Answer::Read(c.graph.lookup(*table, args)?))
                        }
                        Call::Primitive(name, ty) => {
                            store.transactions.stats.evaluations += 1;
                            store.counts.primitive_evals += 1;
                            Ok(Answer::Scalar(c.graph.primitive(name, args, ty)?))
                        }
                    }
                };
                let one;
                let answer = if shared {
                    use std::collections::hash_map::Entry;
                    match answers.entry(args) {
                        Entry::Occupied(e) => {
                            match atom.call {
                                Call::Table(_) => self.transactions.stats.reused_rows += 1,
                                Call::Primitive(..) => self.transactions.stats.reused_scalars += 1,
                            }
                            e.into_mut() as &Answer
                        }
                        Entry::Vacant(e) => {
                            let ans = evaluate(e.key(), self)?;
                            e.insert(ans)
                        }
                    }
                } else {
                    one = evaluate(&args, self)?;
                    &one
                };
                if let Some(input) = input {
                    let receipt = match answer {
                        Answer::Read(r) => AnswerReceipt::read(r.as_ref()),
                        Answer::Scalar(v) => AnswerReceipt::Scalar(v.as_ref()),
                    };
                    self.transactions.record(self.rule, id, input, receipt);
                }
                let valid = match answer {
                    Answer::Read(Some(row)) => extend(c.graph, c.rule, id, row, &mut lane),
                    Answer::Scalar(Some(v)) => {
                        bind(atom.args.last().unwrap(), v, c.graph, &mut lane)
                    }
                    _ => false,
                };
                if valid {
                    keep.push(lane);
                }
            }
            std::mem::swap(&mut lanes, &mut keep);
            if lanes.is_empty() {
                break;
            }
        }
        self.transactions.stats.survivors += lanes.len() as u64;
        let mut unused = vec![];
        // No writes or unions have occurred. Materialize the original ordered child bindings.
        for lane in lanes.drain(..) {
            self.descend(c, c.inst.len(), lane, out, &mut unused)?;
        }
        if let Some(start) = start {
            self.transactions.stats.execute_ns += start.elapsed().as_nanos() as u64;
        }
        *pending = lanes;
        Ok(())
    }
}
