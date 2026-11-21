// A sealed parent lane can authorize at most one record from its rule/template
// span. Failed verification never releases a published record or a source ID.
#[derive(Debug, Eq, PartialEq)]
enum GroupError {
    Withheld,
    Stale,
    Foreign,
    Duplicate,
}
impl Page {
    fn redeem(
        &mut self,
        epoch: u64,
        rid: usize,
        template: usize,
        serial: u64,
        foreign: bool,
    ) -> std::result::Result<usize, GroupError> {
        if self.voucher_epoch != epoch {
            return Err(GroupError::Stale);
        }
        if self.voucher_rule != rid || self.voucher_template != template {
            return Err(GroupError::Foreign);
        }
        let lane = serial
            .checked_sub(self.first)
            .and_then(|n| usize::try_from(n).ok())
            .filter(|i| *i < self.n)
            .ok_or(GroupError::Foreign)?;
        let handle = self.handle.as_ref().ok_or(GroupError::Withheld)?;
        let initialized = self
            .claimed
            .get_mut(lane / 64)
            .ok_or(GroupError::Withheld)?;
        let bit = 1u64 << (lane % 64);
        if *initialized & bit != 0 {
            return Err(GroupError::Duplicate);
        }
        // The foreign control presents a different lane on multirow pages and an
        // out-of-range lane on singleton pages, preserving the real verifier input.
        let offered = if foreign {
            if self.n > 1 { (lane + 1) % self.n } else { 1 }
        } else {
            lane
        };
        let receipt = handle.recipe(offered).ok_or(GroupError::Foreign)?;
        if !crate::joint_root::same_staged_parent(&receipt) {
            return Err(GroupError::Foreign);
        }
        *initialized |= bit;
        Ok(lane)
    }
}
