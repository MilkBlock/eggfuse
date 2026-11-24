//! Count-framed little-endian tensors for exclusive proof and computation batches.
use super::*;
use crate::program::Arg;
use std::io::Read;

const MAGIC: u32 = 0x31585443;
const STATUS: &[&str] = &[
    "accepted",
    "duplicate",
    "untriggered_rule",
    "arity",
    "unknown_output",
    "retired",
    "hidden",
    "type",
    "version",
    "binding",
    "watermark",
    "unbound_primitive",
    "guard",
    "unbound_input",
    "computed",
    "bad_dependency",
    "invalid_computation",
];

#[derive(Default, Serialize)]
pub struct Metrics {
    batches: usize,
    proof_ops: usize,
    compute_ops: usize,
    computed: usize,
    local_reads: usize,
    decode_ns: u64,
    execute_ns: u64,
    encode_ns: u64,
    response_write_ns: u64,
    publication_encode_ns: u64,
    publication_write_ns: u64,
    request_bytes: u64,
    response_bytes: u64,
    port_bytes: u64,
}
fn elapsed(t: Instant) -> u64 {
    t.elapsed().as_nanos() as u64
}
fn pack<const N: usize>(buf: &mut Vec<u8>, row: [i64; N]) {
    for x in row {
        buf.extend_from_slice(&x.to_le_bytes());
    }
}
pub(super) fn publish(
    writer: &mut dyn Write,
    accepted: &[Request],
    rows: &[(&Address, &PortObservation)],
    retired: &[&Address],
    m: &mut Metrics,
) -> Result<()> {
    let t = Instant::now();
    let mut buf = Vec::new();
    let mut end = 0;
    for (a, v) in rows {
        end += v.hashes.len() as i64;
        pack(
            &mut buf,
            [
                a.token,
                a.op as i64,
                v.table as i64,
                v.version as i64,
                i64::from(v.forwarded),
                end,
            ],
        );
    }
    for (_, v) in rows {
        for h in &v.hashes {
            buf.extend_from_slice(&h.to_le_bytes());
        }
    }
    for a in retired {
        pack(&mut buf, [a.token, a.op as i64]);
    }
    for p in accepted {
        pack(&mut buf, [p.token, p.rule as i64]);
    }
    m.port_bytes += buf.len() as u64;
    m.publication_encode_ns += elapsed(t);
    let t = Instant::now();
    writer.write_all(&buf).map_err(|e| e.to_string())?;
    m.publication_write_ns += elapsed(t);
    Ok(())
}

struct Batch {
    bytes: Vec<u8>,
    ops: usize,
}
fn row<const N: usize>(bytes: &[u8], i: usize) -> [i64; N] {
    std::array::from_fn(|j| {
        let off = (i * N + j) * 8;
        i64::from_le_bytes(bytes[off..off + 8].try_into().unwrap())
    })
}
impl Batch {
    fn read(input: &mut impl Read) -> Result<Option<Self>> {
        let mut h = [0u8; 16];
        input.read_exact(&mut h).map_err(|e| e.to_string())?;
        let [magic, ops, refs, finish] =
            std::array::from_fn(|i| u32::from_le_bytes(h[i * 4..i * 4 + 4].try_into().unwrap()));
        if magic != MAGIC || ops > 65536 || refs > 1048576 {
            return Err("invalid transaction header".into());
        }
        if (ops, refs, finish) == (0, 0, 1) {
            return Ok(None);
        }
        if ops == 0 || finish != 0 {
            return Err("invalid finish or empty transaction".into());
        }
        let mut bytes = vec![0; ops as usize * 40 + refs as usize * 32];
        input.read_exact(&mut bytes).map_err(|e| e.to_string())?;
        let mut start = 0;
        for i in 0..ops as usize {
            let [kind, id, rid, pc, end] = row::<5>(&bytes, i);
            if !(0..=1).contains(&kind)
                || id <= 0
                || rid < 0
                || (kind == 0 && pc != -1)
                || (kind == 1 && pc < 0)
                || end < start
                || end > i64::from(refs)
            {
                return Err("invalid transaction descriptor".into());
            }
            start = end;
        }
        if start != i64::from(refs) {
            return Err("unowned transaction references".into());
        }
        Ok(Some(Self {
            bytes,
            ops: ops as usize,
        }))
    }
}

struct Computed {
    value: Value,
    sort: String,
}
impl History {
    fn computation(
        &self,
        g: &Graph,
        rid: usize,
        pc: usize,
        refs: &[[i64; 4]],
        prior: &[Option<Computed>],
    ) -> std::result::Result<Computed, &'static str> {
        let rule = &g.program.rules[rid];
        let atom = rule.query.get(pc).ok_or("invalid_computation")?;
        let Call::Primitive(name, sort) = &atom.call else {
            return Err("invalid_computation");
        };
        let (_, args) = atom.args.split_last().ok_or("arity")?;
        if args.len() != refs.len() {
            return Err("arity");
        }
        let mut inputs = Vec::with_capacity(args.len());
        for (arg, &[token, op, version, col]) in args.iter().zip(refs) {
            match arg {
                Arg::Literal(v) if [token, op, version, col] == [0, -1, 0, 0] => {
                    inputs.push(v.clone())
                }
                Arg::Literal(_) => return Err("invalid_computation"),
                Arg::Slot(slot) if token == 0 => {
                    let result = prior
                        .get(op as usize)
                        .and_then(Option::as_ref)
                        .ok_or("bad_dependency")?;
                    let expected = &g.program.templates[rule.template].sorts[*slot]["name"];
                    if version != 0 || col != 0 || expected.as_str() != Some(&result.sort) {
                        return Err("bad_dependency");
                    }
                    inputs.push(result.value.clone());
                }
                Arg::Slot(_) => {
                    let dep = self
                        .resolve(Address {
                            token,
                            op: op.try_into().map_err(|_| "unknown_output")?,
                        })
                        .ok_or("unknown_output")?;
                    let r = g.row(dep).map_err(|_| "retired")?.ok_or("retired")?;
                    if r.hidden {
                        return Err("hidden");
                    }
                    if Some(r.epoch) != version.try_into().ok() || r.epoch >= g.epoch {
                        return Err("version");
                    }
                    if !rule.query.iter().any(|q| {
                        matches!(q.call,Call::Table(t) if t==r.table)
                            && q.args.get(col as usize) == Some(arg)
                    }) {
                        return Err("type");
                    }
                    inputs.push(r.values.get(col as usize).ok_or("type")?.clone());
                }
            }
        }
        let value = g
            .primitive(name, &inputs, sort)
            .map_err(|_| "invalid_computation")?
            .ok_or("guard")?;
        Ok(Computed {
            value,
            sort: sort.clone(),
        })
    }
    pub(super) fn receive_transactions(
        &mut self,
        g: &Graph,
        run: usize,
        rules: &[(usize, u64)],
        dirty: &[bool],
        check_dirty: bool,
    ) -> Result<()> {
        let mut input = std::io::stdin().lock();
        loop {
            // Header wait is client inference time; decode starts after header availability.
            use std::io::BufRead;
            input.fill_buf().map_err(|e| e.to_string())?;
            let t = Instant::now();
            let Some(batch) = Batch::read(&mut input)? else {
                return Ok(());
            };
            let dt = elapsed(t);
            let t = Instant::now();
            let mut local = Vec::with_capacity(batch.ops);
            let mut replies = Vec::with_capacity(batch.ops);
            let (mut start, mut proofs, mut computations, mut successes, mut deps) =
                (0, 0, 0, 0, 0);
            let mut proof_time = Duration::ZERO;
            for i in 0..batch.ops {
                let [kind, id, rid, pc, end] = row::<5>(&batch.bytes, i);
                let rid = rid as usize;
                let (_, wm) = rules
                    .iter()
                    .find(|&&(r, _)| r == rid)
                    .ok_or("unscheduled transaction rule")?;
                if !self
                    .memory
                    .as_mut()
                    .unwrap()
                    .online_ids
                    .as_mut()
                    .unwrap()
                    .insert(id)
                {
                    return Err("duplicate transaction identity".into());
                }
                let refs =
                    &batch.bytes[batch.ops * 40 + start * 32..batch.ops * 40 + end as usize * 32];
                start = end as usize;
                let mut computed = None;
                let verdict = if kind == 0 {
                    proofs += 1;
                    let clock = Instant::now();
                    let parents = (0..refs.len() / 32)
                        .map(|j| {
                            let [token, op, version, col] = row::<4>(refs, j);
                            if col != -1 || token == 0 || op < 0 || version < 0 {
                                return Err("invalid proof port");
                            }
                            Ok(Premise {
                                address: Address {
                                    token,
                                    op: op as usize,
                                },
                                version: version as u64,
                            })
                        })
                        .collect::<std::result::Result<Vec<_>, _>>()?;
                    let packet = Request {
                        token: id,
                        run,
                        rule: rid,
                        parents,
                        unit: None,
                        side: None,
                        closed_branch: None,
                        graph: None,
                        step: 0,
                    };
                    let v = if check_dirty && !dirty[rid] {
                        *self.counts.rejected.entry("untriggered_rule").or_default() += 1;
                        "untriggered_rule"
                    } else {
                        let (answer, v) = self.admit(g, rid, *wm, &packet)?;
                        if let Some(answer) = answer {
                            self.waves
                                .as_mut()
                                .unwrap()
                                .ready
                                .entry((run, rid))
                                .or_default()
                                .push((packet, answer));
                        }
                        v
                    };
                    proof_time += clock.elapsed();
                    v
                } else {
                    computations += 1;
                    let refs = (0..refs.len() / 32)
                        .map(|j| row::<4>(refs, j))
                        .collect::<Vec<_>>();
                    deps += refs.iter().filter(|r| r[0] == 0 && r[1] >= 0).count();
                    match self.computation(g, rid, pc as usize, &refs, &local) {
                        Ok(value) => {
                            successes += 1;
                            computed = Some(value);
                            "computed"
                        }
                        Err(reason) => reason,
                    }
                };
                let code = STATUS
                    .iter()
                    .position(|s| *s == verdict)
                    .ok_or("unknown transaction verdict")? as i64;
                let hash = computed.as_ref().map_or(0, |v| value_hash(&v.value)) as i64;
                replies.push([id, code, pc, hash]);
                local.push(computed);
            }
            self.verify_time += proof_time;
            let w = self.waves.as_mut().unwrap();
            w.batches += 1;
            w.requests += proofs;
            let m = w.transactions.as_mut().unwrap();
            m.execute_ns += elapsed(t);
            m.decode_ns += dt;
            m.batches += 1;
            m.proof_ops += proofs;
            m.compute_ops += computations;
            m.computed += successes;
            m.local_reads += deps;
            m.request_bytes += (16 + batch.bytes.len()) as u64;
            let t = Instant::now();
            let mut buf = Vec::with_capacity(replies.len() * 32);
            for v in replies {
                pack(&mut buf, v);
            }
            m.encode_ns += elapsed(t);
            m.response_bytes += buf.len() as u64;
            let t = Instant::now();
            let writer = &mut self.memory.as_mut().unwrap().writer;
            writer
                .write_all(&buf)
                .and_then(|_| writer.flush())
                .map_err(|e| e.to_string())?;
            m.response_write_ns += elapsed(t);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn frame(ops: &[[i64; 5]], refs: &[[i64; 4]]) -> Vec<u8> {
        let mut v = Vec::new();
        for n in [MAGIC, ops.len() as u32, refs.len() as u32, 0] {
            v.extend_from_slice(&n.to_le_bytes());
        }
        for op in ops {
            pack(&mut v, *op);
        }
        for r in refs {
            pack(&mut v, *r);
        }
        v
    }
    #[test]
    fn variable_arity_frames_have_exact_bounds() {
        let ops = [[0, 3, 1, -1, 0], [1, 4, 1, 2, 2]];
        let refs = [[-1, 0, 1, 2], [-3, 1, 1, 0]];
        let data = frame(&ops, &refs);
        let batch = Batch::read(&mut data.as_slice()).unwrap().unwrap();
        assert_eq!(row::<5>(&batch.bytes, 1), ops[1]);
        assert_eq!(row::<4>(&batch.bytes[80..], 1), refs[1]);
        assert!(Batch::read(&mut &data[..data.len() - 1]).is_err());
        for offsets in [[1, 0], [1, 3], [0, 1]] {
            let mut malformed = ops;
            for (op, end) in malformed.iter_mut().zip(offsets) {
                op[4] = end;
            }
            assert!(Batch::read(&mut frame(&malformed, &refs).as_slice()).is_err());
        }
    }
    #[test]
    fn excessive_batch_and_invalid_finish_rejected_before_body_read() {
        for h in [
            [MAGIC, 65537, 0, 0],
            [MAGIC, 0, 0, 0],
            [MAGIC, 1, 0, 1],
            [MAGIC, 1, 1048577, 0],
        ] {
            let v: Vec<_> = h.into_iter().flat_map(u32::to_le_bytes).collect();
            assert!(Batch::read(&mut v.as_slice()).is_err());
        }
        let finish: Vec<_> = [MAGIC, 0, 0, 1]
            .into_iter()
            .flat_map(u32::to_le_bytes)
            .collect();
        assert!(Batch::read(&mut finish.as_slice()).unwrap().is_none());
    }
    #[test]
    fn published_hash_bits_and_named_ports_preserve_full_width() {
        let a = Address { token: -7, op: 2 };
        let observation = PortObservation {
            table: 3,
            version: 5,
            forwarded: true,
            hashes: vec![u64::MAX, 1 << 63],
        };
        let mut b = Vec::new();
        let mut m = Metrics::default();
        publish(&mut b, &[], &[(&a, &observation)], &[&a], &mut m).unwrap();
        assert_eq!(row::<6>(&b, 0), [-7, 2, 3, 5, 1, 2]);
        assert_eq!(row::<2>(&b[48..], 0), [-1, i64::MIN]);
        assert_eq!(row::<2>(&b[64..], 0), [-7, 2]);
        assert_eq!(m.port_bytes, 80);
    }
}
