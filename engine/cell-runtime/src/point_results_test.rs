use super::*;

#[test]
fn point_results_follow_full_rows_without_retaining_their_fields() {
    let eq = json!({"kind":"eq","name":"E"});
    let int = json!({"kind":"i64","name":"i64"});
    let tables = [vec![eq.clone(),int.clone()], vec![int.clone()],
        vec![eq.clone(),int.clone(),eq.clone()], vec![eq.clone(),eq]].into_iter()
        .enumerate().map(|(i,schema)| json!({"name":format!("f{i}"),"schema":schema,
            "constructor":false,"virtual_fact":false,"internal":false,"merge":{"var":"new"}})).collect::<Vec<_>>();
    let p = serde_json::from_value(json!({
        "multi_stage":crate::multistage::MultiStage::default(),
        "entry_schedule":crate::entry_schedule::Plan::default(),"tables":tables,
        "templates":[],"rules":[],"sets":{},"control":[],"initial":[],
        "table_templates":[],"artifact":{}
    })).unwrap();
    let mut g = Graph::new(p).unwrap();
    g.merge_programs_enabled = false;
    let keys = [vec![Value::Eq(7)], vec![], vec![Value::Eq(7), Value::Int(4)], vec![Value::Eq(7)]];
    let compare = |g:&mut Graph, table, key:&[Value]| {
        let expected = g.lookup_canonical(table,key).unwrap().as_ref().map(Point::from);
        let lookups = g.key_lookup_calls.get();
        assert_eq!(g.lookup_point(table,key).unwrap(),expected);
        assert_eq!(g.key_lookup_calls.get()-lookups,1,"no second lookup or fallback probe");
    };
    for (t,key) in keys.iter().enumerate() {
        compare(&mut g,t,key);
        let value=if t<2 {Value::Int(1)} else {Value::Eq(9)};
        g.set_function(t,key.clone(),value).unwrap();
        let i=g.function_index(t,key).unwrap();
        compare(&mut g,t,key);
        let fields=g.function(i).unwrap().values;
        #[cfg(feature="sparse-cells")]
        let owners=std::sync::Arc::strong_count(&fields);
        #[cfg(not(feature="sparse-cells"))]
        let owners=std::rc::Rc::strong_count(&fields);
        let point=g.lookup_point(t,key).unwrap().unwrap();
        #[cfg(feature="sparse-cells")]
        assert_eq!(std::sync::Arc::strong_count(&fields),owners);
        #[cfg(not(feature="sparse-cells"))]
        assert_eq!(std::rc::Rc::strong_count(&fields),owners);
        assert_eq!(point.witness,Dependency::Function(i));
    }
    // Match both cached pre-repair fields and invalidated/decoded fields exactly.
    g.enqueue_union(Value::Eq(7),Value::Eq(8)).unwrap();
    g.enqueue_union(Value::Eq(9),Value::Eq(10)).unwrap();
    for (t,key) in keys.iter().enumerate() { compare(&mut g,t,key); }
    g.repair().unwrap();
    for (t,key) in keys.iter().enumerate() {
        let key=key.iter().map(|v|canon(v,&g.parents)).collect::<Vec<_>>();
        compare(&mut g,t,&key);
        let i=g.function_index(t,&key).unwrap();
        g.function_decoded[i]=None;
        compare(&mut g,t,&key);
        g.hide(t,&key,true).unwrap();
        compare(&mut g,t,&key);
        assert!(g.lookup_point(t,&key).unwrap().is_none());
        g.epoch+=1;
        let value=if t<2 {Value::Int(2)} else {Value::Eq(11)};
        g.set_function(t,key.clone(),value).unwrap();
        compare(&mut g,t,&key);
    }
}
