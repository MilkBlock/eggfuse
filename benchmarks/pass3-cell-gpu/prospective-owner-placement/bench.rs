    if a[1] == "bench" {
        let placement = match a[3].as_str() {
            "pooled" => 0, "isolate" => 1, "defer" => 2,
            "defer-only" => 3, "multi-prefix" => 4,
            _ => return Err("unknown benchmark placement".into()),
        };
        let mut counts = [0; 5];
        let mut maintenance = std::time::Duration::ZERO;
        let start = std::time::Instant::now();
        loop {
            let previous = e.steps.len();
            e.execute_until(Some(previous+1))?;
            if e.steps.len()==previous { break; }
            let _=audit::take_trial_unions();
            let begin = std::time::Instant::now();
            e.graph.place_completed_fragments(placement,&mut counts)?;
            e.graph.compact_source_record_capacity();
            e.graph.compact_retired_prefixes()?;
            maintenance += begin.elapsed();
        }
        let elapsed = start.elapsed();
        let runs=e.steps.len();
        let graph=artifact_digest(&e.graph.export()?);
        let slots=e.graph.prospective_owner_charge();
        fs::write(&a[2],serde_json::to_vec(&json!({"runs":runs,"graph":graph,"placement":counts,
            "owner_final":slots,"ms":elapsed.as_secs_f64()*1000.,"maintenance_ms":maintenance.as_secs_f64()*1000.}))?)?;
        return Ok(());
    }
