// Versioned routing metadata lives with the immutable table frame that it describes.
const PAGE_SIZE: usize = 8;
#[derive(Default)]
struct Header {
    bits: [u64; 3],
}
impl Header {
    fn score(&self, query: [u16; 3], weights: &[f32; 6]) -> f32 {
        let mut score = 0.;
        for i in 0..3 {
            let present = ((self.bits[i] >> (query[i] % 64)) & 1) as f32;
            score += present
                * (weights[i] + weights[3 + i] * (1. - self.bits[i].count_ones() as f32 / 8.));
        }
        score
    }
}
impl Store {
    fn page_choices(&mut self, frame: &Frame, col: usize, query: Port) -> Rc<Vec<usize>> {
        use std::collections::hash_map::Entry;
        let mut catalog = frame.pages.borrow_mut();
        let headers = match catalog.entry(col) {
            Entry::Occupied(e) => e.into_mut(),
            Entry::Vacant(e) => {
                let mut headers = Vec::new();
                for page in frame.rows.chunks(PAGE_SIZE) {
                    let mut header = Header::default();
                    for row in page {
                        crate::search_work::add(2, 1);
                        let p = self.code(&row.values[col]);
                        for (i, k) in [p.key, p.extra[0][1], p.extra[1][1]]
                            .into_iter()
                            .enumerate()
                        {
                            header.bits[i] |= 1u64 << (k % 64);
                        }
                    }
                    headers.push(header);
                }
                e.insert(headers)
            }
        };
        let q = [query.key, query.extra[0][1], query.extra[1][1]];
        let weights = self.page_weights.as_ref().unwrap();
        let mut ranked: Vec<_> = headers
            .iter()
            .enumerate()
            .map(|(i, h)| (h.score(q, weights), i))
            .collect();
        crate::search_work::add(8, ranked.len());
        ranked.retain(|(score, _)| *score > 0.);
        ranked.sort_unstable_by(|a, b| b.0.total_cmp(&a.0).then(a.1.cmp(&b.1)));
        let rows = ranked
            .into_iter()
            .take(self.page_budget)
            .flat_map(|(_, i)| i * PAGE_SIZE..((i + 1) * PAGE_SIZE).min(frame.rows.len()))
            .collect();
        Rc::new(rows)
    }
}
