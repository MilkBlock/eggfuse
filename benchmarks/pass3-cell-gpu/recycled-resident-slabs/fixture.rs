#[cfg(test)]
mod recycle_test {
    use super::*;
    fn make_cells(epoch: u64, n: usize) -> impl Iterator<Item = Cell> {
        (0..n).map(move |template| Cell {
            template,
            started_epoch: epoch,
            values: Default::default(),
            facts: crate::slots::FrameMap::stage_reserved(2),
            parent: None,
            completed_prefix: 0,
            completed: false,
            recipe_depth: 0,
        })
    }
    #[test]
    fn dense_refill_keeps_neighbours_and_retires_old_ids() {
        let mut g = NativeCells::default();
        let start = |g: &mut NativeCells, epoch, n| {
            g.start_reused(epoch, 16, n, make_cells(epoch, n), true)
        };
        assert_eq!(start(&mut g, 1, 18), (18, 2));
        // The short page with one of two live outranks the page with two of sixteen live.
        g.publish(9, 0);
        g.publish(8, 3);
        g.publish(u32::MAX, 16);
        g.finish();
        let keep = g.get(&u32::MAX).unwrap() as *const Cell;
        let pos = g.position(u32::MAX).unwrap();
        assert_eq!(start(&mut g, 2, 1), (0, 0));
        assert_eq!(g.current_loc(0), (pos.0, 1));
        assert!(g.get(&3).is_none());
        assert_eq!(g.get(&u32::MAX).unwrap() as *const Cell, keep);
        g.publish(3, 0);
        let reused = g.get(&3).unwrap() as *const Cell;
        g.remove(&3).unwrap();
        // Removing the last public neighbour of a reserved open page must not
        // free it underneath an outstanding grant.
        g.finish();
        assert_eq!(start(&mut g, 3, 1), (0, 0));
        g.remove(&u32::MAX).unwrap();
        assert!(g.get(&u32::MAX).is_none() && g.get(&3).is_none());
        g.publish(19, 0);
        assert_eq!(g.get(&19).unwrap() as *const Cell, reused);
        g.finish();
        g.remove(&9);
        g.remove(&8);
        g.remove(&19);
        assert_eq!(start(&mut g, 4, 0), (0, 0));
        g.finish();
        assert_eq!((g.live, g.holes, g.occupied), (0, 0, 0));
        assert_eq!(g.recycle.grants_into_old_holes, 2);
        assert_eq!(g.recycle.published_from_old_holes, 2);
        assert_eq!(g.recycle.new_pages_avoided, 2);
        assert_eq!(g.recycle.empty_runs, 1);
        assert_eq!(g.recycle.all_reused_runs, 2);
        assert_eq!(g.stats.grants, g.stats.published + g.stats.private_dropped);
    }
}
