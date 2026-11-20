"""Compose the native fast path with versioned, shared typed source-column projections."""

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def replace(s, old, new):
    if s.count(old) != 1:
        raise ValueError(f"source no longer matches {old[:80]}")
    return s.replace(old, new)


def install(crate):
    p = crate / "src/single_epochs.rs"
    s = p.read_text()
    s = replace(
        s,
        "struct SingleEpochs {",
        "struct SingleEpochs {\n    typed: TypedPortIndexes,",
    )
    s = replace(
        s,
        'json!({"rules":self.counts,"max_bytes":self.budget})',
        'json!({"rules":self.counts,"max_bytes":self.budget,"typed":self.typed.stats})',
    )
    s = replace(
        s,
        "s.enabled = true;",
        's.enabled = true;\n        s.typed.budget=spec.get("typed_bytes").and_then(Json::as_u64).unwrap_or(0) as usize;\n        s.typed.delta=spec.get("changed_ports").and_then(Json::as_bool).unwrap_or(false);\n        s.typed.maintain=spec.get("changed_epochs").and_then(Json::as_bool).unwrap_or(false);s.typed.sparse=spec.get("fresh_build").and_then(Json::as_bool).unwrap_or(false);',
    )
    s = replace(
        s,
        "        let mut verdicts = [0u8; 1 << B];",
        """        let typed=if let Some(col)=shared && state.typed.budget!=0 {
            state.typed.for_pivot(g,owner,col,bank,frame,&code,s.detailed)?
        }else{None};
        let mut verdicts = [0u8; 1 << B];""",
    )
    start = s.index("            let fallback;\n            let row = if let Some(r)")
    split = s.index("            if let Some(col) = shared {", start)
    old_read = s[start:split]
    key = "            if let Some(col) = shared {\n                let key = code(&row.values[col]);"
    s = replace(
        s,
        old_read + key,
        """            if let Some(col) = shared {
                let key = if let Some(codes)=&typed{usize::from(codes[i])}else{
"""
        + old_read
        + """                    code(&row.values[col])
                };""",
    )
    s = replace(
        s,
        "            let mut any_exact = false;",
        old_read + "            let mut any_exact = false;",
    )
    start = "            if needs_rows {\n                let cold;"
    s = replace(
        s,
        start,
        """            if needs_rows && !state.oracle && state.typed.budget!=0 {
                let room=(state.budget/DIR_BYTES).saturating_sub(state.private.len());
                let missing=atom.fields.iter().zip(&cols).filter(|(_,(_,d))|d.is_none()).take(room).map(|((col,_),_)|*col).collect::<Vec<_>>();
                let reusable=!missing.is_empty() && missing.iter().all(|col|state.typed.columns.get(&(t,*col)).is_some_and(|x|x.generation==generation && x.union==jun));
                if reusable{
                    scanned+=state.typed.columns[&(t,missing[0])].codes.len();
                    for ((col,_),(_,dir)) in atom.fields.iter().zip(cols.iter_mut()) {
                        if dir.is_none() && state.private.len()<state.budget/DIR_BYTES {
                            let high=state.typed.epoch_directory(t,*col,g).ok_or("lost typed directory")?;
                            state.private.insert((t,*col),(generation,jun,high.clone()));*dir=Some(high);
                        }
                    }
                    needs_rows=false;
                }
            }
"""
        + start,
    )
    s = replace(
        s,
        "                    let a = Rc::new(a);",
        "                    state.typed.offer_rows(t,*col,g,rows,&code);\n                    let a = Rc::new(a);",
    )
    s = replace(
        s,
        "        let cached = |t: usize| {",
        """        if state.typed.sparse{
            state.private.retain(|k,_|state.typed.floors.get(k).copied().unwrap_or(0)<=wm);
        }
        let cached = |t: usize| {""",
    )
    s = replace(
        s,
        "                let cold;",
        "                let cold;let mut marginal_count=None;",
    )
    s = replace(
        s,
        "                    cold = g",
        """                    if state.typed.sparse{
                        let mut batch=vec![];let mut visible=0;
                        for w in g.witnesses(t){
                            if let Some(epoch)=g.visible_epoch(w){visible+=1;state.typed.stats.scanned_epoch_headers+=1;
                                if epoch>=wm{if let Some(row)=g.row(w)? && !row.hidden {batch.push(row)}}
                                else{state.typed.stats.skipped_cold_rows+=1;}
                            }
                        }
                        marginal_count=Some(visible);cold=batch;
                    }else{cold = g""",
    )
    s = replace(
        s,
        "                    &cold\n",
        "                    }\n                    &cold\n",
    )
    s = replace(
        s,
        "                scanned += rows.len();",
        "                scanned += marginal_count.unwrap_or(rows.len());",
    )
    s = replace(
        s,
        "                    state.typed.offer_rows(t,*col,g,rows,&code);",
        "                    if !state.typed.sparse {state.typed.offer_rows(t,*col,g,rows,&code);}else{state.typed.floors.insert((t,*col),wm);}",
    )
    p.write_text(s + '\ninclude!("integrated_typed_ports.rs");\n')
    shutil.copyfile(HERE / "ports.rs", crate / "src/integrated_typed_ports.rs")
    p = crate / "src/incremental_raw.rs"
    s = p.read_text()
    marker = "        if !s.frame_delta {"
    s = replace(
        s,
        marker,
        """        s.publish_epoch_bounds(graph);
        if s.single_epochs.typed.delta {
            s.single_epochs.typed.publish(graph);
        }
"""
        + marker,
    )
    p.write_text(s)
