    if a[1] == "prefix" {
        let mut e=Held(Some(e));
        let mut curve=Vec::new();
        let cfg: Value = serde_json::from_slice(&fs::read(&a[3])?)?;
        let focus = cfg["focus"].as_u64();
        // The source executor is single-threaded. The two Unix processes inherit
        // one real graph and allocator state immediately before this decision.
        unsafe extern "C" {
            fn fork() -> i32;
            fn waitpid(pid: i32, status: *mut i32, options: i32) -> i32;
        }
        let paired = cfg["paired"].as_bool() == Some(true);
        #[cfg(target_os = "macos")]
        unsafe extern "C" {
            fn pthread_is_threaded_np() -> i32;
        }
        #[cfg(target_os = "macos")]
        if paired && unsafe { pthread_is_threaded_np() } != 0 {
            return Err("matched source fork requires a single-threaded process".into());
        }
        #[cfg(not(target_os = "macos"))]
        if paired {
            return Err(
                "matched fork guard is implemented for this Darwin research executable".into(),
            );
        }

        let mut private_child = false;
        let mut child_pid = None;
        let private = cfg["private"].as_bool() == Some(true);
        let capture = cfg["capture"].as_bool() == Some(true);
        let weights = cfg["weights"]
            .as_array()
            .map(|line| line.iter().map(|v| v.as_f64().unwrap()).collect::<Vec<_>>());
        if let Some(w) = &weights {
            assert_eq!(w.len(), 9)
        }
        let mut offers = Vec::new();
        let mut focused = Value::Null;
        let mut max_backing = 0;
        let mut merged_later = 0;
        let mut observed_ids = Vec::new();
        let mut ports = Vec::new();
        let mut later = Vec::new();
        let (mut ordinal, mut selected) = (0u64, 0u64);
        let mut counts = [0; 5];
        let mut owner_byte_runs = 0u64;
        let mut pre_byte_runs = 0u64;
        let mut peak = 0;
        let mut stages = Vec::new();
        let mut trace = Vec::new();
        loop {
            audit::set_active(true);
            audit::enable_write_audit();
            let prev = e.steps.len();
            e.execute_until(Some(prev + 1))?;
            if e.steps.len() == prev {
                break;
            }
            let rhs = audit::take_digests();
            let writes = audit::take_write_digests();
            let spine = audit::take_resume_digests();
            let unions = audit::take_trial_unions();
            let st = e.steps.last().unwrap();
            stages.push(json!([
                st.ruleset,
                st.path,
                st.iterations,
                st.epoch,
                st.executed_bindings,
                st.changed,
                rhs,
                writes,
                spine,
                unions
            ]));
            let run = e.steps.len();
            let mut hit = false;
            e.graph.place_with_prefix_gate(cfg["separate_arrivals"].as_bool()==Some(true),&mut |shape,ids,x|{
                let id=ordinal;ordinal+=1;
                if paired && id==focus.unwrap_or(0){
                    let pid=unsafe{fork()};
                    assert!(pid>=0,"could not fork a matched native source state");
                    if pid==0{private_child=true;}else{child_pid=Some(pid);}
                }
                let choose=if paired && !private_child {false}
                else if let Some(w)=&weights{
                    w[8]+(0..8).map(|i|w[i]*x[i] as f64).sum::<f64>()>0.
                }else{focus==Some(id) && private};
                if choose {selected+=1;trace.push(json!([id,run,shape,ids,x]));}
                if capture {offers.push(json!([id,run,shape,ids,x]));}
                if focus==Some(id){
                    hit=true;observed_ids.extend(ids);pre_byte_runs=owner_byte_runs;
                    focused=json!({"ordinal":id,"run":run,"shape":shape,"members":ids,"features":x,"selected":choose});
                }
                choose
            },&mut counts)?;
            e.graph.compact_source_record_capacity();
            e.graph.compact_retired_prefixes()?;
            let charge = e.graph.prospective_owner_charge();
            owner_byte_runs += charge[6] as u64;
            peak = peak.max(charge[6]);
            if hit {
                focused["backings"] = json!(e.graph.prefix_backings(&observed_ids));
                focused["owner_bytes_at_birth"] = json!(charge[6]);
                ports = e.graph.prefix_source_ports(&observed_ids);
                focused["ports"] = json!(ports);
            }
            if !observed_ids.is_empty() {
                later.push(e.graph.prefix_port_values(&ports)?);
                if cfg["graph_curve"].as_bool()==Some(true){curve.push(graph_probe(&mut e,false)?[0]);}
                let first = e.graph.prefix_backings(&observed_ids)[0];
                if let Some((_, n)) = first {
                    if !hit && n > max_backing {
                        merged_later += 1;
                    }
                    max_backing = max_backing.max(n);
                }
            }
        }
        audit::set_active(false);
        let with_curve=cfg["graph_curve"].as_bool()==Some(true);
        let final_probe=if with_curve {Some(graph_probe(&mut e,true)?)}else{None};
        let graph = artifact_digest(&e.graph.export()?);
        let terminal = e.graph.prospective_owner_charge();
        let n = e.steps.len();
        let physical = json!({"extensions":e.graph.stats.shared_owner_extensions,"extended_frames":e.graph.stats.shared_owner_extension_frames,
                            "merged_owners":e.graph.stats.shared_owner_merged_owners,"focus_backing_max":max_backing,
                            "focus_later_growth_steps":merged_later,"focus_final":e.graph.prefix_backings(&observed_ids)});
        let retained=e.0.take().unwrap();
        let before = LIVE.load(Relaxed);
        drop(retained.graph);
        let released = before - LIVE.load(Relaxed);
        let hash =
            |rows: Vec<serde_json::Value>| eggfuse_cell_runtime::checksum::digest(&json!(rows));
        let source_json=json!(stages);
        let source_hash=eggfuse_cell_runtime::checksum::digest(&source_json);
        let mismatch=cfg["expected_source"].as_str().is_some_and(|expected|expected!=source_hash);
        let later_count = later.len();
        let output = if private_child {
            format!("{}.private", a[2])
        } else {
            a[2].clone()
        };
        fs::write(
            output,
            serde_json::to_vec(&json!({"runs":n,"source":source_hash,"mismatched_stages":if mismatch{Some(source_json)}else{None},"graph":graph,
             "terminal_graph_bytes":released,"graph_curve":curve,"final_probe":final_probe,"physical":physical,"terminal_owner_charge":terminal,
             "owner_byte_runs":owner_byte_runs,"owner_peak":peak,"pre_owner_byte_runs":pre_byte_runs,
             "offers":offers,"count":ordinal,"selected":selected,"trace":trace,"focus":focused,
             "port_runs":later_count,"later_ports":hash(later),"placement":counts}))?,
        )?;
        if let Some(pid) = child_pid {
            let mut status = 0;
            if unsafe { waitpid(pid, &mut status, 0) } != pid || status != 0 {
                return Err("matched child failed".into());
            }
        }
        return Ok(());
    }
