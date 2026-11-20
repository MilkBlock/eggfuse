//! CPU checker for the source-closed attribute domain. Both backends consume the
//! same five signed words per neural claim and return (illegal, missing) per member.
use std::slice;

fn check_member(
    domain: &[[i64; 2]],
    claims: &[[i64; 5]],
    i: usize,
    initial: i64,
    increment: i64,
) -> [i32; 2] {
    let [present, result, parent, depth, value] = claims[i];
    if present == 0 {
        return [0, 1];
    }
    let range = 0..domain.len() as i64;
    let well_formed = present == 1 && result == domain[i][0] && range.contains(&depth);
    let proved = if i == 0 {
        parent == -1 && depth == 0 && value == initial
    } else if let Some(premise) = usize::try_from(parent).ok().and_then(|p| claims.get(p)) {
        premise[0] == 1
            && premise[1] == domain[i][1]
            && range.contains(&premise[3])
            && premise[3].checked_add(1) == Some(depth)
            && premise[4].wrapping_add(increment) == value
    } else {
        false
    };
    [i32::from(!(well_formed && proved)), 0]
}

/// Validate an entire immutable packet after the neural generator has finished.
///
/// # Safety
/// Caller owns four aligned, contiguous, non-overlapping CPU buffers. Config has
/// three words (count, seed value, increment); domain, claims and output contain
/// count 2-word, 5-word and 2-word records respectively. The source plan has
/// already proved the integer range and the finite domain.
#[no_mangle]
pub unsafe extern "C" fn certify_cpu(
    domain: *const [i64; 2],
    claims: *const [i64; 5],
    config: *const i64,
    out: *mut [i32; 2],
) {
    let config = slice::from_raw_parts(config, 3);
    let n = config[0] as usize;
    let domain = slice::from_raw_parts(domain, n);
    let claims = slice::from_raw_parts(claims, n);
    let output = slice::from_raw_parts_mut(out, n);
    for (i, result) in output.iter_mut().enumerate() {
        *result = check_member(domain, claims, i, config[1], config[2]);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn legal_seed_does_not_cover_missing_child() {
        let domain = [[4, -1], [9, 4]];
        let claims = [[1, 4, -1, 0, 3], [0; 5]];
        assert_eq!(check_member(&domain, &claims, 0, 3, 1), [0, 0]);
        assert_eq!(check_member(&domain, &claims, 1, 3, 1), [0, 1]);
    }

    #[test]
    fn bad_pointer_is_rejected() {
        let domain = [[4, -1], [9, 4]];
        let claims = [[1, 4, -1, 0, 3], [1, 9, -2, 1, 4]];
        assert_eq!(check_member(&domain, &claims, 1, 3, 1), [1, 0]);
    }
}

/// Resolve a batch of read-only port transactions against a versioned integer
/// snapshot. Each request contains a handle, source epoch, publication ticket and
/// a compiled branch threshold. A stale address returns -1. Responses 0, 1 and
/// 2 mean below, equal and above the threshold. Nothing is published by a read.
///
/// # Safety
/// The caller supplies contiguous initialized buffers of the declared lengths.
/// Each port contains (epoch, ticket, i64 value), and each request four words.
#[no_mangle]
pub unsafe extern "C" fn compare_ports(
    ports: *const [i64; 3],
    num_ports: usize,
    requests: *const [i64; 4],
    num_requests: usize,
    replies: *mut i64,
) {
    let ports = slice::from_raw_parts(ports, num_ports);
    let requests = slice::from_raw_parts(requests, num_requests);
    let replies = slice::from_raw_parts_mut(replies, num_requests);
    for (request, output) in requests.iter().zip(replies.iter_mut()) {
        let [address, epoch, version, threshold] = *request;
        *output = usize::try_from(address)
            .ok()
            .and_then(|i| ports.get(i))
            .filter(|p| p[0] == epoch && p[1] == version)
            .map_or(-1, |p| match p[2].cmp(&threshold) {
                std::cmp::Ordering::Less => 0,
                std::cmp::Ordering::Equal => 1,
                std::cmp::Ordering::Greater => 2,
            });
    }
}

#[cfg(test)]
mod transaction_tests {
    use super::compare_ports;

    #[test]
    fn replies_are_bound_to_epoch_and_publication() {
        let ports = [[17, 23, i64::MAX], [18, 35, i64::MIN]];
        let requests = [
            [0, 17, 23, 1],
            [1, 18, 35, i64::MIN],
            [1, 18, 35, 0],
            [0, 16, 23, 1],
            [0, 17, 22, 1],
            [2, 18, 35, 1],
            [-1, 18, 35, 1],
        ];
        let mut replies = [99; 7];
        unsafe {
            compare_ports(
                ports.as_ptr(),
                ports.len(),
                requests.as_ptr(),
                requests.len(),
                replies.as_mut_ptr(),
            );
        }
        assert_eq!(replies, [2, 1, 0, -1, -1, -1, -1]);
    }
}
