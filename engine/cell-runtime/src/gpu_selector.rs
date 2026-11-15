//! Optional exact GPU filtering of an existing query expansion domain.
//! The CPU retains query ordering, delta ownership, effects and repair.
use crate::{graph::{Dependency, Graph}, program::{Arg, Atom, Result}, value::Value};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, io::{BufRead, BufReader, Write}, net::{TcpListener, TcpStream},
    process::{Child, Command}, rc::Rc, time::{Duration, Instant}};

#[derive(Default, Serialize)]
pub struct Stats {
    pub batches: u64,
    pub input_rows: u64,
    pub retained_rows: u64,
    pub rejected_rows: u64,
    pub decoded_rows: u64,
    pub bypassed_domains: u64,
    pub failures: u64,
    pub request_bytes: u64,
    pub preparation_seconds: f64,
    pub exchange_seconds: f64,
    pub device_service_seconds: f64,
    pub last_error: Option<String>,
}
#[derive(Serialize)]
struct Request {
    rows: Vec<Vec<i32>>,
    bound: Vec<i32>,
    equal: Vec<(usize, usize)>,
    live: Vec<bool>,
}
#[derive(Deserialize)]
struct Response {
    mask: Vec<bool>,
    complete: bool,
    seconds: f64,
}
pub struct Selector {
    child: Child,
    stream: BufReader<TcpStream>,
    enabled: bool,
    min_rows: usize,
    pub stats: Stats,
}
impl Drop for Selector {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
impl Selector {
    pub fn start(python: &str, service: &str, min_rows: usize) -> Result<Self> {
        if min_rows == 0 { return Err("GPU minimum rows must be positive".into()); }
        let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(|e| e.to_string())?;
        listener.set_nonblocking(true).map_err(|e| e.to_string())?;
        let port = listener.local_addr().map_err(|e| e.to_string())?.port();
        let mut child = Command::new(python).arg(service).arg(port.to_string())
            .spawn().map_err(|e| e.to_string())?;
        let start = Instant::now();
        let stream = loop {
            match listener.accept() {
                Ok((stream, _)) => break stream,
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    if start.elapsed() > Duration::from_secs(20) || child.try_wait().map_err(|e| e.to_string())?.is_some() {
                        let _ = child.kill(); let _ = child.wait();
                        return Err("GPU selector service failed to start".into());
                    }
                    std::thread::sleep(Duration::from_millis(5));
                }
                Err(e) => {
                    let _ = child.kill(); let _ = child.wait();
                    return Err(e.to_string());
                }
            }
        };
        stream.set_nonblocking(false).map_err(|e| e.to_string())?;
        stream.set_read_timeout(Some(Duration::from_secs(10))).map_err(|e| e.to_string())?;
        stream.set_write_timeout(Some(Duration::from_secs(10))).map_err(|e| e.to_string())?;
        Ok(Self { child, stream: BufReader::new(stream), enabled: true, min_rows, stats: Stats::default() })
    }

    pub fn select(&mut self, graph: &Graph, atom: &Atom, bound: &[Option<Value>],
        refs: Rc<Vec<Dependency>>) -> Result<Rc<Vec<Dependency>>> {
        if !self.enabled || refs.len() < self.min_rows || refs.len() > 65536 || bound.len() > 64 {
            self.stats.bypassed_domains += 1;
            return Ok(refs);
        }
        let clock = Instant::now();
        let mut first = BTreeMap::new();
        let mut equal = Vec::new();
        for (column, arg) in atom.args.iter().enumerate() {
            if let Arg::Slot(slot) = arg {
                if let Some(&prior) = first.get(slot) { equal.push((prior, column)); }
                else { first.insert(*slot, column); }
            }
        }
        if equal.is_empty() && bound.iter().all(Option::is_none) {
            self.stats.bypassed_domains += 1;
            return Ok(refs);
        }
        // Exact typed equality interning. No hashes or float casts enter the GPU ABI.
        let mut identities = BTreeMap::<Value, i32>::new();
        let mut encode = |value: &Value| {
            let next = identities.len() as i32;
            *identities.entry(value.clone()).or_insert(next)
        };
        let bound = bound.iter().map(|v| v.as_ref().map(&mut encode).unwrap_or(-1)).collect::<Vec<_>>();
        let mut rows = Vec::with_capacity(refs.len());
        let mut live = Vec::with_capacity(refs.len());
        for &witness in refs.iter() {
            self.stats.decoded_rows += 1;
            match graph.row(witness)? {
                Some(row) if row.values.len() == bound.len() => {
                    live.push(!row.hidden);
                    rows.push(row.values.iter().map(&mut encode).collect());
                }
                _ => { live.push(false); rows.push(vec![-1; bound.len()]); }
            }
        }
        let request = Request { rows, bound, equal, live };
        let payload = serde_json::to_vec(&request).map_err(|e| e.to_string())?;
        self.stats.preparation_seconds += clock.elapsed().as_secs_f64();
        self.stats.request_bytes += payload.len() as u64 + 1;
        let clock = Instant::now();
        let response = self.exchange(&payload, refs.len());
        self.stats.exchange_seconds += clock.elapsed().as_secs_f64();
        match response {
            Ok(response) => {
                self.stats.batches += 1;
                self.stats.input_rows += refs.len() as u64;
                self.stats.device_service_seconds += response.seconds;
                let selected: Vec<_> = refs.iter().zip(response.mask).filter_map(|(&w, keep)| keep.then_some(w)).collect();
                self.stats.retained_rows += selected.len() as u64;
                self.stats.rejected_rows += (refs.len() - selected.len()) as u64;
                Ok(Rc::new(selected))
            }
            Err(error) => {
                self.enabled = false;
                self.stats.failures += 1;
                self.stats.last_error = Some(error);
                Ok(refs)
            }
        }
    }
    fn exchange(&mut self, payload: &[u8], rows: usize) -> Result<Response> {
        let stream = self.stream.get_mut();
        stream.write_all(payload).and_then(|_| stream.write_all(b"\n")).map_err(|e| e.to_string())?;
        let mut line = String::new();
        self.stream.read_line(&mut line).map_err(|e| e.to_string())?;
        let response: Response = serde_json::from_str(&line).map_err(|e| e.to_string())?;
        if !response.complete || response.mask.len() != rows || !response.seconds.is_finite() || response.seconds < 0.0 {
            return Err("incomplete or malformed GPU selection".into());
        }
        Ok(response)
    }
}
