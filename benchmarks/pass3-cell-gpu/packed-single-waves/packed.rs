// The neural token serial includes rejected source rows. Retain the original
// serial separately from the dense lane number in the sealed receipt page.
struct PackedLane {
    source: Option<Dependency>,
    version: u64,
    token_id: u64,
    score: f32,
    initial: bool,
}

#[derive(Default)]
struct PackedOffers {
    lanes: Vec<PackedLane>,
    pages: Vec<Option<crate::joint_root::RootPage>>,
    block: usize,
}

impl PackedOffers {
    fn seal(&mut self, g: &Graph, rid: usize, pivot: Option<usize>, width: usize) {
        self.block = self.lanes.len().div_ceil(width).max(1);
        let mut inputs = Vec::with_capacity(self.block);
        for chunk in self.lanes.chunks(self.block) {
            inputs.clear();
            inputs.extend(chunk.iter().map(|v| (v.source, v.version)));
            let page = crate::joint_root::single_page(g.epoch, rid, pivot, &inputs);
            if let Some(ref p) = page
                && g.spec_cells.is_some()
            {
                g.spec_page(
                    rid,
                    p.stage_serial(),
                    inputs.len(),
                    crate::graph::speculative::Handle::Single(p.clone()),
                );
            }
            self.pages.push(page);
        }
    }

    fn iter(
        &self,
        rid: usize,
    ) -> impl Iterator<
        Item = (
            Token,
            [u8; N],
            bool,
            Option<(&crate::joint_root::RootPage, usize)>,
        ),
    > {
        self.lanes
            .chunks(self.block)
            .zip(&self.pages)
            .flat_map(move |(chunk, receipt)| {
                chunk.iter().enumerate().map(move |(index, lane)| {
                    let token = Token {
                        recipe: None,
                        id: lane.token_id,
                        rid,
                        w: lane.source,
                        version: lane.version,
                        score: lane.score,
                        initial: lane.initial,
                        guarded: false,
                    };
                    (
                        token,
                        [0; N],
                        true,
                        receipt.as_ref().map(|page| (page, index)),
                    )
                })
            })
    }
}

#[derive(Default, serde::Serialize)]
struct PackedStats {
    banks: usize,
    pages: usize,
    lanes: usize,
    verified: usize,
    pending_bytes: usize,
    peak_pending_bytes: usize,
    total_queue_capacity_bytes: usize,
}

impl PackedOffers {
    fn capacity_bytes(&self) -> usize {
        self.lanes.capacity() * std::mem::size_of::<PackedLane>()
            + self.pages.capacity() * std::mem::size_of::<Option<crate::joint_root::RootPage>>()
    }
}
