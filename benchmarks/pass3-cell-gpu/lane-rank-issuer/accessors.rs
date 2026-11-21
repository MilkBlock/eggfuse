// Read sealed packet metadata only. No graph or verifier is accessible here.
impl RootPage {
    pub(crate) fn ranking_parent(&self, lane: usize) -> Option<(usize, Dependency, u64)> {
        let w = &self.words;
        let pos = 8 + 3 * lane;
        match w[pos] {
            0 => None,
            1 => Some((
                w[5] as usize,
                Dependency::Fact(crate::graph::FactRef {
                    cell: (w[pos + 1] >> 32) as u32,
                    op: w[pos + 1] as u32,
                }),
                w[pos + 2],
            )),
            2 => Some((
                w[5] as usize,
                Dependency::Function(w[pos + 1] as usize),
                w[pos + 2],
            )),
            _ => unreachable!("invalid internally emitted single-parent tag"),
        }
    }
}
