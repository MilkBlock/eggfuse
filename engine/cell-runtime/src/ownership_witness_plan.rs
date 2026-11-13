//! Compile bounded candidate addresses; exact current keys remain runtime obligations.
use super::*;

impl Graph {
    pub fn compile_ownership_witness_candidates(&self, source: &J, saturation: &J) -> Result<J> {
        if self.program.artifact.get("sha256") != Some(source) || !source.is_string() {
            return Err("witness source program mismatch".into());
        }
        let paths=saturation["witness_paths"].as_array().ok_or("missing witness paths")?;
        let plan=&self.program.cell_ownership;
        let mut entries=BTreeSet::new();
        let mut unsupported=0;
        for path in paths {
            let rid=path["rule"].as_u64().and_then(|n|usize::try_from(n).ok()).ok_or("invalid rule")?;
            let shape_id=path["shape"].as_u64().and_then(|n|usize::try_from(n).ok()).ok_or("invalid shape")?;
            let rule=self.program.rules.get(rid).ok_or("unknown witness rule")?;
            let Some(shape)=plan.composition.shapes.get(shape_id) else {unsupported+=1;continue;};
            let positions:Vec<(usize,usize,u32)>=serde_json::from_value(path["constructor_positions"].clone()).map_err(|e|e.to_string())?;
            let anchors:Vec<(usize,usize,u32)>=serde_json::from_value(path["query_positions"].clone()).map_err(|e|e.to_string())?;
            if anchors.is_empty() {return Err("missing query anchor".into());}
            let supports=|frame:usize,op:u32,table:usize,width:usize| {
                let Some(&program)=shape.programs.get(frame) else {return false;};
                let Some(fields)=plan.programs.get(program).and_then(|p|p.fields.get(op as usize)) else {return false;};
                fields.len()==width && plan.markers.iter().any(|m|m.program_id==program
                    && plan.code_operators.get(m.code).and_then(|ops|ops.get(op as usize))==Some(&table))
            };
            for (operation,frame,op) in positions {
                let Some(Op::Let(_,Call::Table(table),args))=self.program.templates[rule.template].ops.get(operation) else {
                    return Err("witness target is not a constructor operation".into());
                };
                if !self.program.tables[*table].constructor {return Err("non-constructor witness".into());}
                // Start with input-ready constructors; never speculate across an earlier effect.
                if operation!=0 || args.iter().any(|a|matches!(a,Arg::Slot(s) if !rule.inputs.contains(s)))
                    || self.program.known_results.static_skip.get(rid).and_then(|s|s.get(operation))==Some(&true) {
                    unsupported+=1;continue;
                }
                if !supports(frame,op,*table,args.len()+1) {return Err("target layout/operator mismatch".into());}
                for &(atom,anchor_frame,anchor_op) in &anchors {
                    let query=rule.query.get(atom).ok_or("unknown query anchor")?;
                    let Call::Table(anchor_table)=query.call else {return Err("primitive query anchor".into());};
                    if !supports(anchor_frame,anchor_op,anchor_table,query.args.len()) {return Err("anchor layout/operator mismatch".into());}
                    entries.insert((rid,shape_id,atom,anchor_frame,anchor_op,operation,frame,op,*table));
                }
            }
        }
        Ok(json!({"source_program":source,"entries":entries,"unsupported_positions":unsupported,
            "scope":"typed bounded candidate addresses; not an equality or saturation certificate",
            "required_runtime_checks":["anchor incarnation and component shape","source operator and visibility","all current key fields","source effect ordering"]}))
    }
}
