// Sender output. The constructor has no graph, source iterator, masks of
// individual members or source-value tensor. Current recurrent state is causal.
struct ClassAction([u8; 64]);
struct Decision {
    mask: u8,
    logits: [f32; 2],
    table: usize,
}

#[derive(Default, serde::Serialize)]
struct ActionCounts {
    issued: usize,
    empty: usize,
    logit_evaluations: usize,
    public_headers: usize,
    eligible_after_prefilters: usize,
    accepted_by_action: usize,
    scalar_rejected: usize,
    internal_receipts: usize,
    feedback_bytes: usize,
    residual_calls: usize,
    residual_receipts: usize,
    empty_table_skips: usize,
    masks: [usize; 4],
    audit_ranges: Vec<[u64; 2]>,
    rule_calls: Vec<[u64; 10]>,
    recurrence_digest: u64,
}
fn checksum(bytes: &[u8]) -> u32 {
    bytes.iter().fold(2_166_136_261u32, |h, b| {
        (h ^ u32::from(*b)).wrapping_mul(16_777_619)
    })
}
impl ClassAction {
    fn issue(
        model: &Model,
        state: &[f32; H],
        base: [u8; N],
        floor: f32,
        rid: usize,
        pivot: usize,
        table: usize,
        epoch: u64,
        generation: u64,
        wm: u64,
        first: u64,
    ) -> Result<Self> {
        let mut packet = [0u8; 64];
        for (i, v) in [
            1u32,
            u32::try_from(rid).map_err(|_| "rule too wide")?,
            u32::try_from(table).map_err(|_| "table too wide")?,
            u32::try_from(pivot).map_err(|_| "pivot too wide")?,
        ]
        .into_iter()
        .enumerate()
        {
            packet[4 * i..4 * i + 4].copy_from_slice(&v.to_le_bytes());
        }
        for (i, v) in [epoch, generation, wm, first].into_iter().enumerate() {
            packet[16 + 8 * i..24 + 8 * i].copy_from_slice(&v.to_le_bytes());
        }
        for group in 0..2 {
            let mut f = base;
            f[5] = 32 * group as u8;
            let score = model.score(&f, rid, state);
            if !score.is_finite() {
                return Err("nonfinite class output".into());
            }
            packet[48 + 4 * group..52 + 4 * group].copy_from_slice(&score.to_bits().to_le_bytes());
            packet[56] |= u8::from(score >= floor) << group;
        }
        let ck = checksum(&packet[..60]);
        packet[60..].copy_from_slice(&ck.to_le_bytes());
        Ok(Self(packet))
    }

    // Receives only the fixed action, current public source epoch and scheduled
    // rule identity. It reads no model parameters, scores, or membership vector.
    fn receive(
        mut self,
        g: &Graph,
        rid: usize,
        pivot: usize,
        wm: u64,
        first: u64,
        mode: u8,
    ) -> Result<Decision> {
        let b = &mut self.0;
        if mode == 2 {
            b[56] ^= 1;
        }
        if mode == 3 {
            b[24] ^= 1;
            let ck = checksum(&b[..60]);
            b[60..].copy_from_slice(&ck.to_le_bytes());
        }
        if mode == 4 {
            b[40] ^= 1;
            let ck = checksum(&b[..60]);
            b[60..].copy_from_slice(&ck.to_le_bytes());
        }
        let w = |i: usize| u32::from_le_bytes(b[i..i + 4].try_into().unwrap());
        let dw = |i: usize| u64::from_le_bytes(b[i..i + 8].try_into().unwrap());
        if checksum(&b[..60]) != w(60) {
            return Err("class-action checksum mismatch".into());
        }
        let table = w(8) as usize;
        if w(0) != 1
            || w(4) as usize != rid
            || w(12) as usize != pivot
            || dw(16) != g.epoch
            || dw(32) != wm
            || !matches!(g.program.rules[rid].query[pivot].call,Call::Table(t) if t==table)
            || g.query_versions[table] != dw(24)
        {
            return Err("class-action generation mismatch".into());
        }
        if dw(40) != first {
            return Err("class-action source serial mismatch".into());
        }
        let logits = [f32::from_bits(w(48)), f32::from_bits(w(52))];
        if b[56] > 3 || b[57..60] != [0; 3] || !logits.iter().all(|x| x.is_finite()) {
            return Err("invalid class-action fields".into());
        }
        Ok(Decision {
            mask: b[56],
            logits,
            table,
        })
    }
}
fn class_feedback(delivered: usize, fresh: f32, n: usize) -> (usize, f32, usize) {
    let mut b = [0u8; 20];
    b[..8].copy_from_slice(&(delivered as u64).to_le_bytes());
    b[8..12].copy_from_slice(&fresh.to_bits().to_le_bytes());
    b[12..].copy_from_slice(&(n as u64).to_le_bytes());
    (
        u64::from_le_bytes(b[..8].try_into().unwrap()) as usize,
        f32::from_bits(u32::from_le_bytes(b[8..12].try_into().unwrap())),
        u64::from_le_bytes(b[12..].try_into().unwrap()) as usize,
    )
}

#[derive(Default)]
struct ClassGate;
impl ClassGate {
    fn choose(
        &mut self,
        _g: &Graph,
        _rid: usize,
        _wm: u64,
        _p: &Plan,
        _base: &[u8; N],
        _state: &[f32; H],
    ) -> bool {
        true
    }
    fn observe(&mut self, _epoch: u64, _rid: usize, _after_prefilter: usize, _after_scalar: usize) {
    }
}
