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
    "pending_port",
];

#[derive(Default, Serialize)]
pub struct Metrics {
    pub(crate) ccp: bool,
    sequence: u64,
    cache_hits: usize,
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
    repairs: &[RepairEvent],
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
    if m.ccp {
        let mut end = 0;
        for e in repairs {
            end += e.operations.len();
            let [a, b] = &e.parents;
            let hashes = e.input_hashes.unwrap_or_default();
            pack(
                &mut buf,
                [
                    e.token,
                    e.run as i64,
                    e.merge_table as i64,
                    e.visible_from_run as i64,
                    a.address.token,
                    a.address.op as i64,
                    a.version as i64,
                    b.address.token,
                    b.address.op as i64,
                    b.version as i64,
                    i64::from(e.input_hashes.is_some()),
                    hashes[0] as i64,
                    hashes[1] as i64,
                    end as i64,
                ],
            );
        }
        for e in repairs {
            for &op in &e.operations {
                pack(&mut buf, [op as i64]);
            }
        }
    }
    m.port_bytes += buf.len() as u64;
    m.publication_encode_ns += elapsed(t);
    let t = Instant::now();
    writer.write_all(&buf).map_err(|e| e.to_string())?;
    m.publication_write_ns += elapsed(t);
    Ok(())
}

// CCP 0.1 is opt-in. CTX1-only clients retain their original wire format.
fn envelope(tag: &[u8; 4], seq: u64, run: usize, epoch: u64) -> [u8; 32] {
    let mut out = [0; 32];
    out[..4].copy_from_slice(tag);
    out[6..8].copy_from_slice(&1u16.to_le_bytes());
    out[8..16].copy_from_slice(&seq.to_le_bytes());
    out[16..24].copy_from_slice(&(run as u64).to_le_bytes());
    out[24..].copy_from_slice(&epoch.to_le_bytes());
    out
}

fn size(out: &mut Vec<u8>, len: usize) {
    out.extend_from_slice(&(len as u64).to_le_bytes());
}

// Lossless observation arena. Equality-class IDs are scoped to the snapshot.
fn encode_value(v: &Value, out: &mut Vec<u8>) {
    match v {
        Value::Eq(x) => {
            out.push(0);
            out.extend_from_slice(&x.to_le_bytes());
        }
        Value::Int(x) => {
            out.push(1);
            out.extend_from_slice(&x.to_le_bytes());
        }
        Value::Float(x) => {
            out.push(2);
            out.extend_from_slice(&x.0.to_le_bytes());
        }
        Value::Text(x) => {
            out.push(3);
            size(out, x.len());
            out.extend_from_slice(x.as_bytes());
        }
        Value::Set(xs) => {
            out.push(4);
            size(out, xs.len());
            for x in xs.iter() {
                encode_value(x, out);
            }
        }
        Value::Key(k) => {
            out.push(5);
            let key = k.to_wire();
            size(out, key.root);
            size(out, key.nodes.len());
            for node in key.nodes {
                out.push(u8::from(node.anchor));
                size(out, node.label.len());
                out.extend_from_slice(node.label.as_bytes());
                size(out, node.children.len());
                for child in node.children {
                    size(out, child);
                }
            }
        }
    }
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
    fn read(input: &mut impl Read, ccp: bool) -> Result<Option<Self>> {
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
            if !(0..=if ccp { 2 } else { 1 }).contains(&kind)
                || id <= 0
                || rid < 0
                || (kind != 1 && pc != -1)
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

#[derive(Clone)]
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
        scalars: &crate::value::ScalarContext,
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
                    if !crate::receipt_contract::accepts_field(rule, arg, r.table, col as usize) {
                        return Err("type");
                    }
                    inputs.push(r.values.get(col as usize).ok_or("type")?.clone());
                }
            }
        }
        let value = scalars
            .primitive(name, &inputs, sort, g.program.key_nodes())
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
        let mut pending_ports = BTreeSet::new();
        loop {
            // Header wait is client inference time; decode starts after header availability.
            use std::io::BufRead;
            input.fill_buf().map_err(|e| e.to_string())?;
            let t = Instant::now();
            let metrics = self.waves.as_mut().unwrap().transactions.as_mut().unwrap();
            let ccp = metrics.ccp;
            let sequence = metrics.sequence + 1;
            if ccp {
                let mut header = [0u8; 32];
                input.read_exact(&mut header).map_err(|e| e.to_string())?;
                if header != envelope(b"CCPQ", sequence, run, g.epoch) {
                    return Err("CCP version, sequence or snapshot mismatch".into());
                }
                metrics.sequence = sequence;
                metrics.request_bytes += 32;
            }
            let Some(batch) = Batch::read(&mut input, ccp)? else {
                metrics.request_bytes += 16;
                return Ok(());
            };
            let mut observe = vec![1u8; batch.ops];
            if ccp {
                input.read_exact(&mut observe).map_err(|e| e.to_string())?;
                if observe.iter().any(|&mask| mask > 3) {
                    return Err("unknown observation mask".into());
                }
                metrics.request_bytes += batch.ops as u64;
            }
            let mut arena = Vec::new();
            let mut ends = Vec::new();
            let has_values = ccp && observe.iter().any(|m| m & 2 != 0);
            let mut cache = BTreeMap::new();
            let mut hits = 0;
            let mut value_encode_ns = 0;
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
                let pending = ccp
                    && (0..refs.len() / 32).any(|j| pending_ports.contains(&row::<4>(refs, j)[0]));
                let verdict = if pending {
                    if kind == 0 {
                        proofs += 1;
                    } else {
                        computations += 1;
                    }
                    "pending_port"
                } else if kind == 0 {
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
                            if ccp {
                                pending_ports.insert(id);
                            }
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
                    let result = if kind == 2 {
                        match refs.as_slice() {
                            [[owner, op, version, col]]
                                if *owner != 0 && *op >= 0 && *version >= 0 && *col >= 0 =>
                            {
                                self.resolve(Address {
                                    token: *owner,
                                    op: *op as usize,
                                })
                                .ok_or("unknown_output")
                                .and_then(|a| g.row(a).map_err(|_| "retired")?.ok_or("retired"))
                                .and_then(|r| {
                                    if r.hidden {
                                        return Err("hidden");
                                    }
                                    if Some(r.epoch) != (*version).try_into().ok()
                                        || r.epoch >= g.epoch
                                    {
                                        return Err("version");
                                    }
                                    let c = usize::try_from(*col).map_err(|_| "type")?;
                                    let value = r.values.get(c).ok_or("type")?.clone();
                                    let sort = g.program.tables[r.table]
                                        .schema
                                        .get(c)
                                        .and_then(|s| s["name"].as_str())
                                        .ok_or("type")?
                                        .to_owned();
                                    Ok(Computed { value, sort })
                                })
                            }
                            [_] => Err("invalid_computation"),
                            _ => Err("arity"),
                        }
                    } else if ccp {
                        // Same explicit primitive and operand references in the same immutable batch.
                        let key = (rid, pc, refs);
                        if let Some(index) = cache.get(&key).copied() {
                            hits += 1;
                            Ok(Option::<Computed>::clone(&local[index]).unwrap())
                        } else {
                            let value = self.computation(
                                g,
                                rid,
                                pc as usize,
                                &key.2,
                                &local,
                                &g.scalars.snapshot(),
                            );
                            if value.is_ok() {
                                cache.insert(key, i);
                            }
                            value
                        }
                    } else {
                        self.computation(g, rid, pc as usize, &refs, &local, &g.scalars)
                    };
                    match result {
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
                let hash = if observe[i] & 1 != 0 {
                    computed.as_ref().map_or(0, |v| value_hash(&v.value)) as i64
                } else {
                    0
                };
                if has_values {
                    let t = Instant::now();
                    if observe[i] & 2 != 0 {
                        if let Some(value) = &computed {
                            encode_value(&value.value, &mut arena);
                            if arena.len() > 64 * 1024 * 1024 {
                                return Err("CCP observation arena exceeds limit".into());
                            }
                        }
                    }
                    ends.push(arena.len() as u64);
                    value_encode_ns += elapsed(t);
                }
                replies.push([id, code, pc, hash]);
                local.push(computed);
            }
            self.verify_time += proof_time;
            let w = self.waves.as_mut().unwrap();
            w.batches += 1;
            w.requests += proofs;
            let m = w.transactions.as_mut().unwrap();
            m.cache_hits += hits;
            m.execute_ns += elapsed(t).saturating_sub(value_encode_ns);
            m.encode_ns += value_encode_ns;
            m.decode_ns += dt;
            m.batches += 1;
            m.proof_ops += proofs;
            m.compute_ops += computations;
            m.computed += successes;
            m.local_reads += deps;
            m.request_bytes += (16 + batch.bytes.len()) as u64;
            let t = Instant::now();
            let mut buf = Vec::with_capacity(replies.len() * 32);
            if ccp {
                buf.extend_from_slice(&envelope(b"CCPR", sequence, run, g.epoch));
                size(&mut buf, arena.len());
            }
            for v in replies {
                pack(&mut buf, v);
            }
            for end in ends {
                buf.extend_from_slice(&end.to_le_bytes());
            }
            buf.extend_from_slice(&arena);
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
    fn ccp_v01_wire_values_and_envelope() {
        use crate::value::FloatBits;
        let prefix = envelope(b"CCPQ", 256, 3, 9);
        assert_eq!(
            prefix,
            *b"CCPQ\0\0\x01\0\0\x01\0\0\0\0\0\0\x03\0\0\0\0\0\0\0\x09\0\0\0\0\0\0\0"
        );
        let mut bytes = Vec::new();
        for v in [
            Value::Eq(3),
            Value::Int(-2),
            Value::Float(FloatBits(i64::MIN)),
            Value::Text("λ".to_owned().into()),
            Value::Set(vec![Value::Int(2)].into()),
        ] {
            encode_value(&v, &mut bytes);
        }
        assert_eq!(
            bytes,
            [
                0, 3, 0, 0, 0, 0, 0, 0, 0, 1, 254, 255, 255, 255, 255, 255, 255, 255, 2, 0, 0, 0,
                0, 0, 0, 0, 128, 3, 2, 0, 0, 0, 0, 0, 0, 0, 0xce, 0xbb, 4, 1, 0, 0, 0, 0, 0, 0, 0,
                1, 2, 0, 0, 0, 0, 0, 0, 0
            ]
        );
        let k = eggfuse_structural_key::Key::new("x".into(), vec![]);
        let mut key = Vec::new();
        encode_value(&Value::Key(k), &mut key);
        assert_eq!(
            key,
            [
                5, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, b'x',
                0, 0, 0, 0, 0, 0, 0, 0
            ]
        );
    }
    #[test]
    fn variable_arity_frames_have_exact_bounds() {
        let ops = [[0, 3, 1, -1, 0], [1, 4, 1, 2, 2]];
        let refs = [[-1, 0, 1, 2], [-3, 1, 1, 0]];
        let data = frame(&ops, &refs);
        let batch = Batch::read(&mut data.as_slice(), false).unwrap().unwrap();
        assert_eq!(row::<5>(&batch.bytes, 1), ops[1]);
        assert_eq!(row::<4>(&batch.bytes[80..], 1), refs[1]);
        assert!(Batch::read(&mut &data[..data.len() - 1], false).is_err());
        for offsets in [[1, 0], [1, 3], [0, 1]] {
            let mut malformed = ops;
            for (op, end) in malformed.iter_mut().zip(offsets) {
                op[4] = end;
            }
            assert!(Batch::read(&mut frame(&malformed, &refs).as_slice(), false).is_err());
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
            assert!(Batch::read(&mut v.as_slice(), false).is_err());
        }
        let finish: Vec<_> = [MAGIC, 0, 0, 1]
            .into_iter()
            .flat_map(u32::to_le_bytes)
            .collect();
        assert!(
            Batch::read(&mut finish.as_slice(), false)
                .unwrap()
                .is_none()
        );
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
        publish(&mut b, &[], &[(&a, &observation)], &[&a], &[], &mut m).unwrap();
        assert_eq!(row::<6>(&b, 0), [-7, 2, 3, 5, 1, 2]);
        assert_eq!(row::<2>(&b[48..], 0), [-1, i64::MIN]);
        assert_eq!(row::<2>(&b[64..], 0), [-7, 2]);
        assert_eq!(m.port_bytes, 80);
    }
}
