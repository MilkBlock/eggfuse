#[derive(Clone, Copy)]
struct ScalarRef {
    dep: Dependency,
    version: u64,
}

#[derive(Default)]
struct PointPage {
    serials: Vec<u64>,
    points: Vec<ScalarRef>,
    consumed: usize,
}
impl PointPage {
    fn push(&mut self, id: u64, points: &[ScalarRef]) {
        self.serials.push(id);
        self.points.extend_from_slice(points);
    }
    fn get(&mut self, id: u64, width: usize) -> Result<Option<&[ScalarRef]>> {
        let Some(&next) = self.serials.get(self.consumed) else {
            return Ok(None);
        };
        if next < id {
            return Err("scalar proof page lost its owner".into());
        }
        if next > id {
            return Ok(None);
        }
        let begin = self.consumed * width;
        self.consumed += 1;
        Ok(Some(&self.points[begin..begin + width]))
    }
    fn finish(&mut self) -> Result<()> {
        if self.consumed != self.serials.len() {
            return Err("unconsumed scalar proof lane".into());
        }
        self.serials.clear();
        self.points.clear();
        self.consumed = 0;
        Ok(())
    }
}
struct PointLane<'a> {
    points: &'a [ScalarRef],
    mapping: &'a [usize],
    audit: bool,
}
impl ScalarProofs {
    fn lane(&mut self, rid: usize, id: u64) -> Result<Option<PointLane<'_>>> {
        if !self.positive {
            return Ok(None);
        }
        let Some(plan) = &self.plans[rid] else {
            return Ok(None);
        };
        let points = self.pages[rid].get(id, plan.points.len())?;
        Ok(points.map(|p| PointLane {
            points: p,
            mapping: &plan.mapping,
            audit: self.audit,
        }))
    }
}
