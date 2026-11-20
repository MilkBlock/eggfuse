// The rule's next RHS operation pays for a key only when this entry fails its source checks.
// An entry is populated solely by a canonical native read in this Graph.
#[derive(Default)]
struct RhsReads {
    mode: u8,
    verify: bool,
    eligible: Vec<bool>,
    rows: Vec<Option<(u64, u64, u64, Row)>>,
    by_table: Vec<[u64; 4]>,
    calls: [u64; 4],
}
impl Graph {
    pub fn configure_ordered_reads(&mut self, mode: u8, verify: bool) -> Result<()> {
        if mode > 2 {
            return Err("unknown ordered RHS read plan".into());
        }
        let mut eligible: Vec<bool> = self
            .program
            .tables
            .iter()
            .map(|t| t.constructor && t.virtual_fact && (mode == 2 || t.schema.len() == 1))
            .collect();
        // Only constructor tables with no explicitly mutable source operation are admitted.
        for template in &self.program.templates {
            for op in template.ops.iter() {
                if let Op::Set(t, ..) | Op::Hide(t, ..) = op {
                    eligible[*t] = false;
                }
            }
        }
        self.rhs_reads = RhsReads {
            mode,
            verify,
            rows: vec![None; eligible.len()],
            by_table: vec![[0; 4]; eligible.len()],
            eligible,
            ..Default::default()
        };
        Ok(())
    }
    fn rhs_lookup(&mut self, t: usize, key: &[Value], site: usize) -> Result<Option<Row>> {
        if self.rhs_reads.mode == 0 {
            return self.lookup_canonical(t, key);
        }
        self.rhs_reads.calls[site] += 1;
        if !self.rhs_reads.eligible[t] || !self.dirty_facts[t].is_empty() {
            return self.lookup_canonical(t, key);
        }
        self.rhs_reads.by_table[t][0] += 1;
        let version = self.query_versions[t];
        if let Some((epoch, table_generation, unions, row)) = &self.rhs_reads.rows[t] {
            if self.epoch == *epoch && version == *table_generation && self.stats.unions == *unions
            {
                if row.values.len() == key.len() + 1 && row.values[..key.len()] == *key {
                    if self.rhs_reads.verify {
                        let canonical = self
                            .lookup_canonical(t, key)?
                            .ok_or("reused RHS fact disappeared")?;
                        if canonical.witness != row.witness
                            || canonical.values != row.values
                            || canonical.table != row.table
                            || canonical.epoch != row.epoch
                            || canonical.hidden != row.hidden
                        {
                            return Err("reused RHS fact changed".into());
                        }
                    }
                    self.rhs_reads.by_table[t][1] += 1;
                    return Ok(Some(row.clone()));
                }
                self.rhs_reads.by_table[t][2] += 1;
            } else {
                self.rhs_reads.by_table[t][3] += 1;
            }
        }
        let result = self.lookup_canonical(t, key)?;
        if let Some(row) = &result {
            self.rhs_reads.rows[t] = Some((self.epoch, version, self.stats.unions, row.clone()));
        }
        Ok(result)
    }
    pub fn rhs_read_report(&self) -> J {
        let mut totals = [0u64; 4];
        for table in &self.rhs_reads.by_table {
            for (to, from) in totals.iter_mut().zip(table) {
                *to += from;
            }
        }
        json!({"mode":self.rhs_reads.mode,"verified":self.rhs_reads.verify,
               "eligible_tables":self.rhs_reads.eligible.iter().filter(|&&v|v).count(),"sites":self.rhs_reads.calls,
               "eligible_hits_keymiss_stampmiss":totals,"tables":self.rhs_reads.by_table,
               "constructor_requests":self.stats.constructor_requests,"constructor_reused":self.stats.constructor_reused,
               "cells":self.stats.cells_created,"lookups":self.key_lookup_calls.get()})
    }
}
