//! Optional Metal producer. A token holds the positions of the actual LHS
//! witnesses in the immutable input frame for this rule occurrence.
use crate::{
    cell::{Instance, QueryFacts},
    graph::{Graph, Row},
    program::{Arg, Call, Program, Result},
    value::{Value, canon},
};
use serde::Serialize;
use std::{
    collections::BTreeMap,
    io::{BufRead, BufReader, Write},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    time::Instant,
};

#[derive(Default, Serialize)]
pub struct Stats {
    pub eligible_rules: usize,
    pub retired_entry_nodes: usize,
    pub batches: u64,
    pub device_dispatches: u64,
    pub input_rows: u64,
    pub tested_pairs: u64,
    pub tokens: u64,
    pub admitted_bindings: u64,
    pub request_bytes: u64,
    pub response_bytes: u64,
    pub preparation_seconds: f64,
    pub exchange_seconds: f64,
    pub projection_seconds: f64,
    pub service_seconds: f64,
}

#[cfg(target_os = "macos")]
#[path = "gpu_bindings_native.rs"]
mod native;
enum Transport {
    Python(Service),
    #[cfg(target_os = "macos")]
    Metal(native::Native),
}
struct Service {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
}
pub struct Producer {
    transport: Transport,
    eligible: Vec<bool>,
    pub(crate) batch: bool,
    ready: BTreeMap<usize, Vec<Instance>>,
    pub stats: Stats,
}
impl Drop for Service {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

struct Frame {
    tables: Vec<Vec<Row>>,
    sources: BTreeMap<usize, (usize, usize, i32)>,
    encoded: Vec<Vec<i32>>,
    widths: Vec<usize>,
    checks: Vec<i32>,
}
impl Frame {
    fn pairs(&self) -> usize {
        self.tables[0]
            .len()
            .saturating_mul(self.tables.get(1).map_or(1, Vec::len))
    }
}

impl Producer {
    pub(crate) fn start(p: &Program, python_service: Option<(&str, &str)>) -> Result<Self> {
        let eligible: Vec<_> = p
            .rules
            .iter()
            .map(|r| {
                (1..=2).contains(&r.query.len())
                    && r.query.iter().all(|a| matches!(a.call, Call::Table(_)))
            })
            .collect();
        let transport = if let Some((python, service)) = python_service {
            let mut child = Command::new(python)
                .arg(service)
                .env("PYTORCH_ENABLE_MPS_FALLBACK", "0")
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .spawn()
                .map_err(|e| e.to_string())?;
            let input = child.stdin.take().unwrap();
            let output = BufReader::new(child.stdout.take().unwrap());
            let mut service = Service {
                child,
                input,
                output,
            };
            let mut greeting = String::new();
            service
                .output
                .read_line(&mut greeting)
                .map_err(|e| e.to_string())?;
            let hello: serde_json::Value =
                serde_json::from_str(&greeting).map_err(|e| e.to_string())?;
            if hello != serde_json::json!({"device":"metal","protocol":1}) {
                return Err("incompatible GPU binding producer".into());
            }
            Transport::Python(service)
        } else {
            #[cfg(target_os = "macos")]
            {
                Transport::Metal(native::Native::new()?)
            }
            #[cfg(not(target_os = "macos"))]
            {
                return Err("native Metal requires macOS".into());
            }
        };
        let stats = Stats {
            eligible_rules: eligible.iter().filter(|x| **x).count(),
            ..Stats::default()
        };
        Ok(Self {
            transport,
            batch: false,
            ready: Default::default(),
            eligible,
            stats,
        })
    }
    pub(crate) fn accepts(&self, rid: usize) -> bool {
        self.eligible[rid]
    }

    fn prepare(&mut self, graph: &Graph, rid: usize, watermark: u64) -> Result<Frame> {
        let start = Instant::now();
        let rule = &graph.program.rules[rid];
        let mut ids = BTreeMap::<Value, i32>::new();
        let mut encode = |v: &Value| -> Result<i32> {
            let next = i32::try_from(ids.len()).map_err(|_| "value dictionary overflow")?;
            Ok(*ids.entry(v.clone()).or_insert(next))
        };
        let mut tables: Vec<Vec<Row>> = Vec::new();
        let mut encoded = Vec::new();
        let mut widths = Vec::new();
        let mut checks = Vec::new();
        let mut sources = BTreeMap::new();
        let mut offset = 0i32;
        for (atom, q) in rule.query.iter().enumerate() {
            let Call::Table(t) = q.call else {
                return Err("unsupported GPU atom".into());
            };
            for (column, arg) in q.args.iter().enumerate() {
                let index = offset + column as i32 + 1;
                match arg {
                    Arg::Literal(v) => {
                        checks.extend([index, -1 - encode(&canon(v, &graph.parents))?])
                    }
                    Arg::Slot(slot) => {
                        if let Some(&(_, _, previous)) = sources.get(slot) {
                            checks.extend([index, previous]);
                        } else {
                            sources.insert(*slot, (atom, column, index));
                        }
                    }
                }
            }
            let rows = graph
                .witnesses(t)
                .into_iter()
                .filter_map(|w| graph.row(w).transpose())
                .collect::<Result<Vec<_>>>()?;
            let width = q.args.len() + 1;
            let mut values = Vec::with_capacity(rows.len() * width);
            for row in &rows {
                if row.values.len() != q.args.len() {
                    return Err("GPU relation width mismatch".into());
                }
                values.push(if row.hidden {
                    -1
                } else {
                    i32::from(!rule.seminaive || row.epoch >= watermark)
                });
                for v in row.values.iter() {
                    values.push(encode(v)?);
                }
            }
            self.stats.input_rows += rows.len() as u64;
            tables.push(rows);
            widths.push(width);
            encoded.push(values);
            offset += width as i32;
        }
        if encoded.len() == 1 {
            encoded.push(vec![0]);
            widths.push(1);
        }
        self.stats.tested_pairs +=
            (tables[0].len() as u64) * tables.get(1).map_or(1, |r| r.len() as u64);
        self.stats.preparation_seconds += start.elapsed().as_secs_f64();
        Ok(Frame {
            tables,
            sources,
            encoded,
            widths,
            checks,
        })
    }
    pub(crate) fn generate(
        &mut self,
        graph: &Graph,
        rid: usize,
        watermark: u64,
        facts: &QueryFacts,
    ) -> Result<Vec<Instance>> {
        if self.batch {
            return self
                .ready
                .remove(&rid)
                .ok_or_else(|| format!("missing GPU batch result for rule {rid}"));
        }
        let frame = self.prepare(graph, rid, watermark)?;
        let (encoded, widths, checks) = (&frame.encoded, &frame.widths, &frame.checks);
        self.stats.device_dispatches += frame.pairs().div_ceil(65536) as u64;
        let start = Instant::now();
        let (tokens, service, request_bytes, response_bytes) = match &mut self.transport {
            Transport::Python(pipe) => {
                let mut request =
                    serde_json::to_vec(&(&encoded[0], &encoded[1], &checks, widths[0], widths[1]))
                        .map_err(|e| e.to_string())?;
                request.push(b'\n');
                pipe.input.write_all(&request).map_err(|e| e.to_string())?;
                let mut line = String::new();
                pipe.output
                    .read_line(&mut line)
                    .map_err(|e| e.to_string())?;
                let (tokens, seconds): (Vec<[usize; 2]>, f64) =
                    serde_json::from_str(&line).map_err(|e| format!("GPU bindings: {e}"))?;
                (tokens, seconds, request.len() as u64, line.len() as u64)
            }
            #[cfg(target_os = "macos")]
            Transport::Metal(device) => device.query(&encoded, &widths, &checks)?,
        };
        self.stats.exchange_seconds += start.elapsed().as_secs_f64();
        self.stats.service_seconds += service;
        self.stats.batches += 1;
        self.stats.tokens += tokens.len() as u64;
        self.stats.request_bytes += request_bytes;
        self.stats.response_bytes += response_bytes;
        self.project(frame, tokens, facts)
    }
    fn project(
        &mut self,
        frame: Frame,
        mut tokens: Vec<[usize; 2]>,
        facts: &QueryFacts,
    ) -> Result<Vec<Instance>> {
        let Frame {
            tables, sources, ..
        } = frame;
        let start = Instant::now();
        tokens.sort_unstable();
        let mut found = Vec::with_capacity(tokens.len());
        for token in tokens {
            let rows = tables
                .iter()
                .enumerate()
                .map(|(i, t)| {
                    t.get(token[i])
                        .ok_or_else(|| "invalid GPU witness position".to_string())
                })
                .collect::<Result<Vec<_>>>()?;
            let values = sources
                .iter()
                .map(|(&slot, &(a, c, _))| (slot, rows[a].values[c].clone()))
                .collect();
            let known = facts.with_rows(rows.iter().enumerate().map(|(i, r)| (i, r.witness)));
            found.push(Instance::matched(
                values,
                known,
                rows.iter().map(|r| r.epoch).max().unwrap(),
            ));
        }
        self.stats.projection_seconds += start.elapsed().as_secs_f64();
        Ok(found)
    }

    // Every descriptor reads the same pre-commit graph. Ordinary ordered apply
    // consumes results at the source rule's original position.
    #[cfg(target_os = "macos")]
    pub(crate) fn prepare_run(
        &mut self,
        graph: &Graph,
        jobs: Vec<(usize, u64, QueryFacts)>,
    ) -> Result<()> {
        if !self.ready.is_empty() {
            return Err("unconsumed GPU Run results".into());
        }
        if jobs.is_empty() {
            return Ok(());
        }
        let mut frames = Vec::with_capacity(jobs.len());
        let mut data = [Vec::new(), Vec::new()];
        let mut directory = vec![0; 8 * jobs.len()];
        let mut pairs = 0usize;
        let mut right_counts = Vec::new();
        let pack = Instant::now();
        let previous = self.stats.preparation_seconds;
        for (i, &(rid, watermark, _)) in jobs.iter().enumerate() {
            let mut frame = self.prepare(graph, rid, watermark)?;
            pairs = pairs
                .checked_add(frame.pairs())
                .ok_or("batch pair space overflow")?;
            let right = frame.encoded[1].len() / frame.widths[1];
            let fields = [
                pairs,
                data[0].len(),
                data[1].len(),
                right,
                frame.widths[0],
                frame.widths[1],
                directory.len(),
                frame.checks.len() / 2,
            ];
            for (dst, field) in directory[8 * i..8 * i + 8].iter_mut().zip(fields) {
                *dst = i32::try_from(field)
                    .map_err(|_| "batch address exceeds Metal representation")?;
            }
            right_counts.push(right);
            directory.append(&mut frame.checks);
            for (bank, rows) in data.iter_mut().zip(&mut frame.encoded) {
                bank.append(rows);
            }
            frames.push(frame);
        }
        self.stats.preparation_seconds = previous + pack.elapsed().as_secs_f64();
        let start = Instant::now();
        let Transport::Metal(device) = &self.transport else {
            return Err("batch mode requires native Metal".into());
        };
        let groups = i32::try_from(jobs.len()).map_err(|_| "too many rule groups")?;
        let (tokens, service, tx, rx) =
            device.dispatch(&data, &directory, pairs, [-groups, 0, 0, 0, 0, 0])?;
        self.stats.exchange_seconds += start.elapsed().as_secs_f64();
        self.stats.service_seconds += service;
        self.stats.batches += 1;
        self.stats.device_dispatches += pairs.div_ceil(65536) as u64;
        self.stats.request_bytes += tx;
        self.stats.response_bytes += rx;
        self.stats.tokens += tokens.len() as u64;
        let mut groups = vec![Vec::new(); jobs.len()];
        for [i, pair] in tokens {
            let right = *right_counts.get(i).ok_or("unknown device rule group")?;
            if right == 0 {
                return Err("token from an empty domain".into());
            }
            groups[i].push([pair / right, pair % right]);
        }
        for (((rid, _, facts), frame), tokens) in jobs.into_iter().zip(frames).zip(groups) {
            let rows = self.project(frame, tokens, &facts)?;
            self.ready.insert(rid, rows);
        }
        Ok(())
    }
}
