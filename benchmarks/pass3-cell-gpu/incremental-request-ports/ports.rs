type SMap<K, V> = rustc_hash::FxHashMap<K, V>;
type Set<T> = rustc_hash::FxHashSet<T>;

#[derive(Default)]
struct LivePostings {
    codes: SMap<Dependency, (u32, Option<u64>)>,
    by_code: SMap<u32, Vec<Dependency>>,
    by_class: SMap<u64, Vec<Dependency>>,
}
fn remove_dep<K: Eq + std::hash::Hash>(map: &mut SMap<K, Vec<Dependency>>, k: &K, d: Dependency) {
    if let Some(v) = map.get_mut(k) {
        let i = v
            .iter()
            .position(|addr| *addr == d)
            .expect("reverse request membership");
        v.swap_remove(i);
        if v.is_empty() {
            map.remove(k);
        }
    }
}
impl LivePostings {
    fn remove(&mut self, d: Dependency) {
        if let Some((code, class)) = self.codes.remove(&d) {
            remove_dep(&mut self.by_code, &code, d);
            if let Some(id) = class {
                remove_dep(&mut self.by_class, &id, d);
            }
        }
    }
    fn insert(&mut self, d: Dependency, word: u32, class: Option<u64>) {
        self.codes.insert(d, (word, class));
        self.by_code.entry(word).or_default().push(d);
        if let Some(id) = class {
            self.by_class.entry(id).or_default().push(d);
        }
    }
}
struct VersionedPort {
    rows: Rc<LivePostings>,
    through: u64,
    generation: u64,
    unions: u64,
    complete: bool,
    changed: Set<Dependency>,
}
#[derive(Default, Serialize)]
struct PatchWork {
    directory_ns: u64,
    activation_ns: u64,
    builds: u64,
    built_rows: u64,
    repairs: u64,
    repaired_addresses: u64,
    union_repairs: u64,
    class_probes: u64,
    affected_classes: u64,
    stale_logs: u64,
    transitions: u64,
    journal_writes: u64,
    reused: u64,
    peak_rows: usize,
    audit_rows: u64,
}
#[derive(Default)]
struct PatchPorts {
    mode: u8,
    versions: SMap<(usize, usize), VersionedPort>,
    size: usize,
    work: PatchWork,
}
impl PatchPorts {
    fn transition(&mut self, table: usize, old: u64, new: u64, delta: &[Dependency]) {
        for ((t, _), v) in self.versions.iter_mut().filter(|((t, _), _)| *t == table) {
            debug_assert_eq!(*t, table);
            self.work.transitions += 1;
            if v.through != old || v.changed.len() + delta.len() > 32768 {
                v.complete = false;
                v.changed.clear();
            }
            if v.complete {
                v.changed.extend(delta);
                self.work.journal_writes += delta.len() as u64;
            }
            v.through = new;
        }
    }
}
enum WakeImage {
    Offsets(Rc<Subscribers>),
    Stable(Rc<LivePostings>, Rc<Frame>),
}
impl WakeImage {
    fn get(&self, key: &u32) -> Option<std::borrow::Cow<'_, [usize]>> {
        match self {
            Self::Offsets(data) => Some(std::borrow::Cow::Borrowed(data.get(key)?)),
            Self::Stable(data, frame) => Some(std::borrow::Cow::Owned(
                data.by_code
                    .get(key)?
                    .iter()
                    .map(|d| {
                        frame
                            .rows
                            .binary_search_by_key(d, |r| r.witness)
                            .expect("live subscription address")
                    })
                    .collect(),
            )),
        }
    }
}
pub fn configure_patch_ports(mode: u64) -> Result<()> {
    if !(1..=4).contains(&mode) {
        return Err("invalid incremental subscription policy".into());
    }
    STORE.with_borrow_mut(|s| {
        s.as_mut().ok_or("missing source issuer")?.patch_ports.mode = mode.min(3) as u8;
        Ok(())
    })
}
impl Store {
    fn port_row(&mut self, c: &Context, row: &Row, col: usize) -> Option<(u32, Option<u64>)> {
        let v = canon(&row.values[col], &c.graph.parents);
        let class = match v {
            Value::Eq(i) => Some(i),
            Value::Int(_) => None,
            _ => return None,
        };
        let w = self.code(&v);
        Some((signature(w, false, self.views), class))
    }
    fn current_ports(&mut self, c: &Context, step: &StackStep, col: usize) -> Option<WakeImage> {
        let clock = self.profiling.then(std::time::Instant::now);
        let data = self.current_ports_impl(c, step, col);
        if let Some(t) = clock {
            self.patch_ports.work.directory_ns += t.elapsed().as_nanos() as u64;
        }
        data
    }

    fn current_ports_impl(
        &mut self,
        c: &Context,
        step: &StackStep,
        col: usize,
    ) -> Option<WakeImage> {
        if self.patch_ports.mode == 0 {
            return self.wake_index(c, step, col).map(WakeImage::Offsets);
        }
        let n = step.frame.rows.len();
        if n > 32768 {
            return None;
        }
        let key = (step.table, col);
        let generation = step.frame.generation;
        let unions = c.graph.stats.unions;
        let mode = self.patch_ports.mode;
        if let Some(v) = self.patch_ports.versions.get(&key)
            && v.generation == generation
            && v.unions == unions
        {
            self.patch_ports.work.reused += 1;
            return Some(WakeImage::Stable(v.rows.clone(), step.frame.clone()));
        }
        let mut old = self.patch_ports.versions.remove(&key);
        if let Some(v) = &old {
            self.patch_ports.size -= v.rows.codes.len()
        }
        if n + self.patch_ports.size > 65536 {
            self.patch_ports.versions.clear();
            self.patch_ports.size = 0;
        }
        let can_patch = old.as_ref().is_some_and(|v| {
            mode >= 2
                && v.complete
                && v.through == generation
                && (v.unions == unions
                    || mode == 3
                        && unions.checked_sub(v.unions).is_some_and(|k| {
                            k <= c.graph.request_unions.as_ref().map_or(0, |r| r.len()) as u64
                        }))
        });
        let data = if can_patch {
            let v = old.take()?;
            let mut data = Rc::try_unwrap(v.rows).ok()?;
            let mut pending = v.changed;
            if v.unions != unions {
                self.patch_ports.work.union_repairs += 1;
                for hi in c
                    .graph
                    .request_unions
                    .as_ref()?
                    .iter()
                    .rev()
                    .take((unions - v.unions) as usize)
                {
                    self.patch_ports.work.class_probes += 1;
                    if let Some(deps) = data.by_class.get(hi) {
                        self.patch_ports.work.affected_classes += 1;
                        pending.extend(deps);
                    }
                }
            }
            self.patch_ports.work.repairs += 1;
            self.patch_ports.work.repaired_addresses += pending.len() as u64;
            for d in pending {
                data.remove(d);
                if let Ok(i) = step.frame.rows.binary_search_by_key(&d, |r| r.witness) {
                    let (word, class) = self.port_row(c, &step.frame.rows[i], col)?;
                    data.insert(d, word, class);
                }
            }
            Rc::new(data)
        } else {
            self.patch_ports.work.stale_logs += u64::from(mode > 1 && old.is_some());
            self.patch_ports.work.builds += 1;
            let mut data = LivePostings::default();
            for row in step.frame.rows.iter() {
                let (word, class) = self.port_row(c, row, col)?;
                data.insert(row.witness, word, class);
            }
            self.patch_ports.work.built_rows += n as u64;
            Rc::new(data)
        };
        if self.detailed {
            assert_eq!(data.codes.len(), n);
            for row in step.frame.rows.iter() {
                let expected = self.port_row(c, row, col)?;
                assert_eq!(data.codes.get(&row.witness), Some(&expected));
                assert!(data.by_code[&expected.0].contains(&row.witness));
            }
            self.patch_ports.work.audit_rows += n as u64;
        }
        self.patch_ports.size += n;
        self.patch_ports.work.peak_rows =
            self.patch_ports.work.peak_rows.max(self.patch_ports.size);
        self.patch_ports.versions.insert(
            key,
            VersionedPort {
                rows: data.clone(),
                through: generation,
                generation,
                unions,
                complete: true,
                changed: Set::default(),
            },
        );
        Some(WakeImage::Stable(data, step.frame.clone()))
    }
}
