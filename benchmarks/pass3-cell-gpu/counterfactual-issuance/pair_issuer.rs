// The two witnesses in a claim are always in consumer atom order.
type VersionedPort = [u64; 3];

#[derive(Deserialize)]
pub struct PairPolicy {
    #[serde(default)]
    takeover: bool,
    #[serde(default)]
    ambiguous_control: bool,
    column: usize,
    target: usize,
    wiring: BTreeMap<usize, Vec<[usize; 2]>>,
    actions: [bool; 32],
}
struct PairIssuer {
    policy: PairPolicy,
    frame: BTreeMap<usize, (VersionedPort, bool)>,
    claimed: std::collections::BTreeSet<[VersionedPort; 2]>,
    ready: BTreeMap<Dependency, ReturnedPair>,
    children: Vec<(u64, usize)>,
    external: Vec<[u64; 3]>,
    checked: usize,
    verified: usize,
    proposals: Vec<(usize, [VersionedPort; 2])>,
}
pub fn configure_pair_policy(policy: PairPolicy, program: &Program, source: &[u8]) -> Result<()> {
    validate_pair_wiring(&policy, program, source)?;

    STATE.with_borrow_mut(|state| {
        if let Some(state) = state {
            for &rid in policy.wiring.keys() {
                Rc::make_mut(&mut state.layout[rid]).pair_program = policy.takeover;
            }
            state.pair_issuer = Some(PairIssuer {
                policy,
                frame: Default::default(),
                claimed: Default::default(),
                ready: Default::default(),
                children: vec![],
                external: vec![],
                checked: 0,
                verified: 0,
                proposals: vec![],
            });
        }
    });
    Ok(())
}
pub(crate) fn finish_pair(epoch: u64, success: bool) {
    STATE.with_borrow_mut(|state| {
        let Some(state) = state else { return };
        let Some(issuer) = &mut state.pair_issuer else {
            return;
        };
        if success
            && let Some((ordinal, _, _, rule, _)) = state.active
            && let Some(pairs) = issuer.policy.wiring.get(&rule)
        {
            for [outer, inner] in pairs {
                let (Some(&(a, reused_a)), Some(&(b, reused_b))) =
                    (issuer.frame.get(outer), issuer.frame.get(inner))
                else {
                    continue;
                };
                let key = [a, b];
                let flags = [
                    reused_a,
                    reused_b,
                    a[2] == epoch,
                    b[2] == epoch,
                    issuer.claimed.contains(&key),
                ];
                let lane = flags
                    .into_iter()
                    .fold(0, |i, flag| i * 2 + usize::from(flag));
                if issuer.policy.actions[lane] {
                    issuer.proposals.push((ordinal, key));
                    issuer.claimed.insert(key);
                }
            }
        }
        issuer.frame.clear();
    });
}

/// Check each proposed pair at the first consumer query boundary after issuance.
pub(crate) fn check_pairs(g: &Graph, rid: usize, watermark: u64) -> Result<()> {
    STATE.with_borrow_mut(|state| {
        let Some(issuer) = state.as_mut().and_then(|s| s.pair_issuer.as_mut()) else {
            return Ok(());
        };
        if rid != issuer.policy.target {
            return Ok(());
        }
        // Any unused pivot belonged to the previous query snapshot.
        issuer.ready.clear();
        let query = &g.program.rules[rid].query;
        let [outer, inner] = query.as_slice() else {
            return Err("expected two pair atoms".into());
        };
        let (Call::Table(a), Call::Table(b)) = (&outer.call, &inner.call) else {
            return Err("expected two pair tables".into());
        };
        for &(owner, [x, y]) in &issuer.proposals[issuer.checked..] {
            let read = |p: VersionedPort, table| -> Result<Option<crate::graph::Row>> {
                let d = Dependency::Fact(crate::graph::FactRef {
                    cell: p[0] as u32,
                    op: p[1] as u32,
                });
                Ok(g.row(d)?
                    .filter(|r| r.table == table && !r.hidden && r.epoch == p[2]))
            };
            if let (Some(left), Some(right)) = (read(x, *a)?, read(y, *b)?)
                && left.epoch.max(right.epoch) >= watermark
                && left
                    .values
                    .get(issuer.policy.column)
                    .is_some_and(|v| Some(v) == right.values.last())
            {
                issuer.verified += 1;
                if issuer.policy.takeover
                    && !issuer.policy.ambiguous_control
                    && unique_pair(right.values.last())
                {
                    let refs = [
                        Ref {
                            atom: 0,
                            row: left.witness,
                            version: x[2],
                        },
                        Ref {
                            atom: 1,
                            row: right.witness,
                            version: y[2],
                        },
                    ];
                    if issuer
                        .ready
                        .insert(left.witness, ReturnedPair { owner, refs })
                        .is_some()
                    {
                        return Err("duplicate protected pivot".into());
                    }
                }
            }
        }
        issuer.checked = issuer.proposals.len();
        Ok(())
    })
}
