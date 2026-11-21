#[cfg(test)]
mod resident_lifecycle {
    use super::*;

    fn lane(template: usize) -> Lane {
        Lane::private(Cell {
            template,
            started_epoch: 7,
            values: Default::default(),
            facts: crate::slots::FrameMap::stage_reserved(2),
            parent: None,
            completed_prefix: 0,
            completed: false,
            recipe_depth: 0,
        })
    }
    fn make(n: usize, first: usize) -> Box<[Lane]> {
        let mut page = (0..n)
            .map(|i| lane(first + i))
            .collect::<Vec<_>>()
            .into_boxed_slice();
        for x in page.iter_mut() {
            x.freeze()
        }
        page
    }
    #[test]
    fn private_lanes_become_visible_in_place_and_release_the_last_owner() {
        let mut g = NativeCells::default();
        let page = make(16, 2);
        let address = page[3].header;
        let fact_ptr = page[3].fact_buffer;
        g.start(7, 16, vec![page, make(2, 18)], true);
        assert!(g.is_empty());
        assert!(g.iter().next().is_none());
        g.private_mut(3).completed_prefix = 1;
        assert_eq!(g.publish(u32::MAX, 3), fact_ptr);
        let c = g.get(&u32::MAX).unwrap();
        assert_eq!(address, c as *const Cell as usize);
        assert_eq!((c.template, c.completed_prefix), (5, 1));
        g.publish(1, 16);
        g.finish();
        assert_eq!(
            (g.occupied, g.live, g.holes, g.stats.private_dropped),
            (18, 2, 16, 16)
        );
        g.start(8, 16, vec![make(1, 30)], true);
        let preexisting = g[&u32::MAX].facts.stage_allocation();
        g.get_mut(&u32::MAX).unwrap().completed = true;
        assert_eq!(g[&u32::MAX].facts.stage_allocation(), preexisting);
        g.publish(2, 0);
        g.finish();
        assert_eq!(g.iter().count(), 3);
        g.remove(&1).unwrap();
        assert_eq!((g.live, g.occupied, g.holes), (2, 17, 15));
        assert_eq!(g.remove(&u32::MAX).unwrap().template, 5);
        assert_eq!(g.occupied, 1);
        assert!(g.get(&u32::MAX).is_none());
        // A recycled page directory slot cannot make an old id resolve again.
        g.start(9, 16, vec![make(1, 45)], true);
        g.publish(7, 0);
        g.finish();
        assert!(g.get(&1).is_none() && g.get(&u32::MAX).is_none());
        assert_eq!(g[&7].template, 45);
        g.remove(&2);
        g.remove(&7);
        assert_eq!((g.live, g.occupied, g.holes), (0, 0, 0));
        assert_eq!(g.stats.published, g.stats.retired);
        assert_eq!(g.stats.grants, g.stats.private_dropped + g.stats.published);
        assert!(g.old_run_reads.get() > 0);
    }
}
