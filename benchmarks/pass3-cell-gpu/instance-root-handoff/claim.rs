#[derive(Debug)]
pub(crate) struct DirectClaim {
    id: usize,
    rule: usize,
    width: usize,
    root: Option<Rc<crate::joint_root::Bound>>,
}

#[derive(Default, serde::Serialize)]
struct ClaimCounts {
    attached: usize,
    transferred: usize,
    archived_comparisons: usize,
}

pub fn configure_instance_claim(mode: u8) -> Result<()> {
    if mode > 2 {
        return Err("invalid instance-claim mode".into());
    }
    STORE.with_borrow_mut(|s| {
        let Some(state) = s.as_mut() else {
            return if mode == 0 {
                Ok(())
            } else {
                Err("instance claims require a multi-parent issuer".into())
            };
        };
        state.instance_mode = mode;
        Ok(())
    })
}

pub(crate) fn take_instance_claim(
    id: usize,
    rule: usize,
    mark: DirectClaim,
    slots: &Slots,
    inputs: &[usize],
) -> Result<Option<Rc<crate::joint_root::Bound>>> {
    STORE.with_borrow_mut(|s| {
        let s = s.as_mut().expect("attached source issuer");
        if id == 0 || id > s.claim_counts.attached || rule != mark.rule || id != mark.id {
            return Err("instance claim disagrees with winning source rule".into());
        }
        s.global_rhs += 1;
        s.counts.committed += 1;
        *s.by_width.entry(mark.width).or_default() += 1;
        s.claim_counts.transferred += 1;
        if s.detailed {
            let reference = &s.tickets[id - 1];
            assert_eq!(
                (reference.rule, reference.width, reference.local_token_id),
                (rule, mark.width, id)
            );
            assert!(reference.inputs.iter().eq(inputs.iter().map(|i| &slots[i])));
            match (&reference.root_recipe, &mark.root) {
                (Some(a), Some(b)) => assert!(Rc::ptr_eq(a, b)),
                (None, None) => (),
                _ => panic!("audited ticket has different root proof"),
            }
            let mut winner = reference.clone();
            winner.ordinal = s.global_rhs;
            s.wins.push(winner);
            s.claim_counts.archived_comparisons += 1;
        }
        Ok(mark.root)
    })
}
