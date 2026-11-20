    if a[1] == "prefix-bench" {
        let weights: Vec<f64> = serde_json::from_slice(&fs::read(&a[3])?)?;
        if weights.len() != 9 {
            return Err("expected eight feature weights and intercept".into());
        }
        let mut counts = [0; 5];
        let (mut offers, mut selected) = (0, 0);
        let mut placement_time = std::time::Duration::ZERO;
        let start = std::time::Instant::now();
        loop {
            let run = e.steps.len();
            e.execute_until(Some(run + 1))?;
            if e.steps.len() == run {
                break;
            }
            let _ = audit::take_trial_unions();
            let clock = std::time::Instant::now();
            e.graph.place_with_prefix_gate(
                false,
                &mut |_, _, x| {
                    offers += 1;
                    let choose =
                        weights[8] + (0..8).map(|i| weights[i] * x[i] as f64).sum::<f64>() > 0.;
                    selected += u64::from(choose);
                    choose
                },
                &mut counts,
            )?;
            e.graph.compact_source_record_capacity();
            e.graph.compact_retired_prefixes()?;
            placement_time += clock.elapsed();
        }
        let elapsed = start.elapsed();
        fs::write(
            &a[2],
            serde_json::to_vec(
                &json!({"runs":e.steps.len(),"graph":artifact_digest(&e.graph.export()?),
            "offers":offers,"selected":selected,"ms":elapsed.as_secs_f64()*1000.,
            "maintenance_ms":placement_time.as_secs_f64()*1000.}),
            )?,
        )?;
        return Ok(());
    }
