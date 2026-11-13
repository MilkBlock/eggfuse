//! Reuse the completed-source directory for ownership routing. Ordinary or
//! retired-but-still-addressable sources retain only the fallback route.
use super::*;
use crate::graph::cell_ownership::composition::Frame;

impl Cells {
    pub(crate) fn source_route(&self, id: &u32) -> Option<&Frame> {
        if let Some(index) = self.completed_index(*id) {
            return self.completed.frames[index].routing.as_ref();
        }
        self.route_fallback.get(id)
    }
    pub(crate) fn set_source_route(&mut self, id: u32, route: Frame) {
        if let Some(index) = self.completed_index(id) {
            self.completed.frames[index].routing = Some(route);
        } else {
            self.route_fallback.insert(id, route);
        }
    }
    pub(crate) fn remove_source_route(&mut self, id: &u32) {
        if let Some(index) = self.completed_index(*id) {
            self.completed.frames[index].routing = None;
        } else {
            self.route_fallback.remove(id);
        }
    }
    pub(crate) fn source_route_count(&self) -> usize {
        self.route_fallback.len()
            + self.completed.frames.iter().filter(|frame| frame.routing.is_some()).count()
    }
}
