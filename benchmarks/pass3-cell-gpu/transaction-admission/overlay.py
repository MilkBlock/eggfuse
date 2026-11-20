from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent


def swap(text,old,new):
    if text.count(old)!=1:raise ValueError(old)
    return text.replace(old,new)


def install(crate):
    p=crate/'src/request_transactions.rs'
    s=swap(p.read_text(),'struct Transactions {','struct Transactions {\n    learned_schedule: Option<Vec<u8>>,')
    s=swap(s,'if self.eligible.get(rule) == Some(&true) {','if self.eligible.get(rule) == Some(&true) && self.learned_schedule.as_ref().is_none_or(|a|a[rule]!=0) {')
    p.write_text(s+'\n'+(HERE/'schedule.rs').read_text())
    p=crate/'src/ordinary_witness.rs'
    s=swap(p.read_text(),'let batch = s.transactions.width_for(rid);','let batch = s.transactions.width_for(rid);\n            let streamed = s.transactions.learned_schedule.as_ref().map_or(s.transactions.streaming,|a|a[rid]==1);')
    p.write_text(swap(s,'if s.transactions.streaming{s.flush_requests','if streamed{s.flush_requests'))
    p=crate/'examples/joint_witness_session.rs'
    marker='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(swap(p.read_text(),marker,'''        if let Some(policy)=req.get("request_policy"){
            if policy["program_sha256"].as_str()!=Some(digest.as_str()){return Err("request policy source mismatch".into());}
            ordinary_witness::install_request_schedule(serde_json::from_value(policy["actions"].clone())?)?;
        }
'''+marker))
