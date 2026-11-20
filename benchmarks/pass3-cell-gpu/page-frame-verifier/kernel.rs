#[derive(Default, serde::Serialize)]
struct ReadWork {
    audit_anchor_lists_omitted: u64,
    audit_anchor_refs_omitted: u64,
    issue_frame_refs: u64,
    issue_source_refs: u64,
    issue_offset_mismatches: u64,
    dead_port_calls: u64,
    dead_port_args: u64,
    seals: [u64; 4],
    pages: u64,
    parents: u64,
    source_rows: u64,
    frame_rows: u64,
    union_source_rows: u64,
    prefix_hits: u64,
    fresh_rejects: u64,
    pointer_rejects: u64,
    offset_bytes: u64,
}
#[derive(Default)]
struct PageKernel {
    on: bool,
    tail_active: bool,
    seal_active: bool,
    mode: u8,
    fault: u8,
    positions: Vec<u32>,
    work: ReadWork,
}
pub fn configure_page_kernel(mode: u8, fault: u8) -> Result<()> {
    STORE.with_borrow_mut(|store| {
        let s = store.as_mut().ok_or("missing multi-parent issuer")?;
        if mode > 11 || fault > 3 || !s.page || s.accel != 4 || !s.seal {
            return Err("unsupported page reader".into());
        }
        s.page_kernel.on = true;
        s.page_kernel.mode = mode;
        s.page_kernel.fault = fault;
        Ok(())
    })
}
impl Store {
    fn check_parent_page(
        &mut self,
        g: &Graph,
        c: &Context,
        base: &Prefix,
        page: &crate::joint_root::MultiPage,
        frames: &[Rc<Frame>],
        out: &mut Vec<Instance>,
        unused: &mut Vec<Vec<Dependency>>,
    ) -> Result<()> {
        let k = &mut self.page_kernel;
        let mode = k.mode;
        let fault = k.fault;
        let mut positions = std::mem::take(&mut k.positions);
        if matches!(mode, 1 | 3 | 7)
            && (positions.len() != page.count() * c.pick_count || frames.len() != c.pick_count)
        {
            return Err("incomplete emitted page positions".into());
        }
        k.work.pages += 1;
        k.work.parents += (page.count() * c.pick_count) as u64;
        k.work.offset_bytes += (positions.len() * std::mem::size_of::<u32>()) as u64;
        let use_frame = matches!(mode, 1 | 3 | 7);
        let share_prefix = mode == 2 || mode == 3;
        // A single immutable Graph borrow spans issue, checking and suffix verification.
        if use_frame && (fault==2 || frames.iter().enumerate().any(|(j,f)|{
            !matches!(c.rule.query[c.inst[j].0].call,Call::Table(t) if f.table==t && f.generation==g.query_versions[t])
        })){
            k.work.fresh_rejects+=page.count() as u64;self.counts.raw_parent_rejects+=page.count() as u64;
            positions.clear();k.positions=positions;return Ok(());
        }
        let mut last: Option<(Dependency, u64, u32, Option<Prefix>)> = None;
        for i in 0..page.count() {
            let parents = page.parents(i);
            let mut exact = base.clone();
            let mut ok = true;
            for (j, parent) in parents.iter().enumerate() {
                let atom = c.inst[j].0;
                let pos = if !use_frame {
                    0
                } else {
                    positions[i * c.pick_count + j]
                };
                let k = &mut self.page_kernel;
                let stale = fault == 3 && j == 0;
                if j == 0
                    && share_prefix
                    && let Some((address, version, offset, prior)) = &last
                    && *address == parent.row
                    && *version == parent.version
                    && *offset == pos
                    && !stale
                {
                    k.work.prefix_hits += 1;
                    if let Some(p) = prior {
                        exact = p.clone();
                        continue;
                    } else {
                        ok = false;
                        break;
                    }
                }
                let stored;
                let row = if use_frame {
                    let f = &frames[j];
                    let chosen = if fault == 1 && j == 0 {
                        pos.wrapping_add(1)
                    } else {
                        pos
                    };
                    let candidate = f.rows.get(chosen as usize);
                    if candidate.is_none_or(|r| r.witness != parent.row) {
                        k.work.pointer_rejects += 1;
                        ok = false;
                        break;
                    }
                    let r = candidate.unwrap();
                    if stale || r.epoch != parent.version || r.hidden || r.table != f.table {
                        k.work.fresh_rejects += 1;
                        ok = false;
                        break;
                    }
                    if f.born_at_union == g.stats.unions {
                        k.work.frame_rows += 1;
                        r
                    } else {
                        k.work.union_source_rows += 1;
                        k.work.source_rows += 1;
                        stored = g.row(parent.row)?;
                        let Some(v) = stored.as_ref().filter(|v| v.epoch == parent.version) else {
                            k.work.fresh_rejects += 1;
                            ok = false;
                            break;
                        };
                        v
                    }
                } else {
                    k.work.source_rows += 1;
                    stored = g.row(parent.row)?;
                    let Some(v) = stored.as_ref() else {
                        ok = false;
                        break;
                    };
                    v
                };
                if matches!(mode, 5 | 6 | 7 | 8 | 9 | 10 | 11)
                    && (parent.atom != atom
                        || row.epoch != parent.version
                        || row.witness != parent.row)
                {
                    k.work.fresh_rejects += 1;
                    ok = false;
                    break;
                }
                let pass = extend(g, c.rule, atom, row, &mut exact);
                if j == 0 && share_prefix {
                    last = Some((parent.row, parent.version, pos, pass.then(|| exact.clone())));
                }
                if !pass {
                    ok = false;
                    break;
                }
            }
            if !ok {
                self.counts.raw_parent_rejects += 1;
                continue;
            }
            self.counts.verified_parent_tuples += 1;
            exact.picks = parents.len();
            if matches!(mode, 10 | 11) && !self.detailed {
                self.page_kernel.work.audit_anchor_lists_omitted += 1;
                self.page_kernel.work.audit_anchor_refs_omitted += parents.len() as u64;
            } else {
                exact.anchors = parents.iter().map(|r| r.row).collect();
            }
            exact.root_recipe = page.recipe(i);
            self.page_kernel.tail_active = matches!(mode, 4 | 6 | 7 | 8 | 9 | 10 | 11);
            self.page_kernel.seal_active = matches!(mode, 5 | 6 | 7 | 8 | 9 | 10 | 11);
            let answer = self.descend(c, c.pick_count, exact, out, unused);
            self.page_kernel.tail_active = false;
            self.page_kernel.seal_active = false;
            answer?;
        }
        positions.clear();
        self.page_kernel.positions = positions;
        Ok(())
    }
}
