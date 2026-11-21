#[cfg(test)]
mod inline_fact_lane_tests {
    use super::*;
    #[test]
    fn inline_fact_lane_spill_move_and_roundtrip() {
        fn state() -> crate::graph::FactState {
            serde_json::from_value(serde_json::json!({"hash":0,"hidden":false,"epoch":7,"born":0})).unwrap()
        }
        let mut a=CellFacts::stage_reserved(0);
        assert_eq!(a.stage_bytes(),0);
        for i in 0..FACT_LANES as u32 {a.insert(3+i,state());}
        assert_eq!(a.stage_inline(),FACT_LANES>0);
        a.insert(2,state()); assert!(!a.stage_inline()); assert!(a.stage_bytes()>0);
        assert!(a.insert(2,state()).is_some()); assert!(a.remove(&2).is_some());
        let encoded=serde_json::to_value(&a).unwrap();
        let copy:CellFacts=serde_json::from_value(encoded.clone()).unwrap();
        let mut dest=CellFacts::stage_reserved(0);dest.stage_move_from(copy);
        assert_eq!(serde_json::to_value(&dest).unwrap(),encoded);
        assert_eq!(dest.keys().copied().collect::<Vec<_>>(),(3..(3+FACT_LANES as u32)).collect::<Vec<_>>());
    }
}
