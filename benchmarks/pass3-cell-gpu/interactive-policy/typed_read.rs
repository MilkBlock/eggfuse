// Immutable batched read of a visible signed i64. Epoch/ticket are checked
// before a payload is returned. No mutation and no allocation in the RPC.
#[no_mangle]
pub unsafe extern "C" fn read_i64(
    ports: *const [i64; 3], n: usize, req: *const [i64; 3], m: usize, out: *mut [i64; 2],
) {
    let ports = std::slice::from_raw_parts(ports, n);
    let req = std::slice::from_raw_parts(req, m);
    let out = std::slice::from_raw_parts_mut(out, m);
    for (reply, &[handle, epoch, ticket]) in out.iter_mut().zip(req) {
        *reply = usize::try_from(handle).ok().and_then(|i| ports.get(i))
            .filter(|p| p[0] == epoch && p[1] == ticket)
            .map_or([0, 0], |p| [1, p[2]]);
    }
}

/// Replay the source scheduling/publication boundary with an authoritative local
/// last-publication ledger. No consumed-event, future Match, or target labels are inputs.
/// Header consistency outside this table (e.g. cross-row e-class forwarding) is
/// deliberately left to an actual engine's graph; this ledger only discharges
/// a guard on its scoped physical address.
#[no_mangle]
pub unsafe extern "C" fn deferred_switch(
    events: *const [i64; 12], n: usize, scheduled: *const i64, runs: usize,
    decisions: *const [i64; 2], proposals: *mut [i64; 4],
) {
    let events=std::slice::from_raw_parts(events,n);
    let scheduled=std::slice::from_raw_parts(scheduled,runs);
    let decisions=std::slice::from_raw_parts(decisions,n);
    let proposals=std::slice::from_raw_parts_mut(proposals,n);
    proposals.fill([0;4]);
    let mut visible=std::collections::HashMap::new();
    let mut pending:Vec<usize>=vec![];
    let mut cursor=0;
    for (i,&ready) in scheduled.iter().enumerate(){
        let run=i as i64+1;
        if ready!=0{
            for ix in pending.drain(..){
                let e=events[ix];
                if visible.get(&e[4])!=Some(&e[1]){
                    proposals[ix][3]=-run;
                    continue
                }
                proposals[ix]=[i64::from(decisions[ix][0]!=0 && e[5]==e[7]),
                               i64::from(decisions[ix][0]!=0 && e[5]>e[7]),
                               i64::from(decisions[ix][1]!=0 && e[6]==e[8]),run];
            }
        }
        while cursor<n && events[cursor][0]==run{
            let e=events[cursor];
            visible.insert(e[4],e[1]);
            pending.push(cursor);
            cursor+=1;
        }
    }
}
