"""Move each multi-parent root with its source binding; production no longer retains all tickets."""
from pathlib import Path
from shutil import copyfile

HERE=Path(__file__).resolve().parent


def change(source,old,new):
    if source.count(old)!=1:raise ValueError(old)
    return source.replace(old,new)


def install(crate):
    src=crate/'src'
    p=src/'cell_match.rs'
    s=change(p.read_text(),'    pub(crate) ordinary_id:usize,','    pub(crate) direct_claim:Option<crate::ordinary_witness::DirectClaim>,\n    pub(crate) ordinary_id:usize,')
    p.write_text(s)
    for f in src.glob("*.rs"):
        s=f.read_text()
        if "ordinary_id:0," in s:f.write_text(s.replace("ordinary_id:0,","direct_claim:None,ordinary_id:0,"))
    p=src/'ordinary_witness.rs';s=p.read_text()
    s=change(s,'    tickets:Vec<Ticket>,wins:', '    instance_mode:u8,claim_counts:ClaimCounts,tickets:Vec<Ticket>,wins:')
    s=change(s,'        tickets:vec![],wins:', '        instance_mode:0,claim_counts:Default::default(),tickets:vec![],wins:')
    s=change(s,'json!({"wave":s.wave.stats,','json!({"instance_claims":{"counts":s.claim_counts,"tickets":s.tickets.len(),"directory_bytes":s.tickets.capacity()*std::mem::size_of::<Ticket>(),"instance_bytes":std::mem::size_of::<Instance>()},"wave":s.wave.stats,')
    left=s.index('            self.tickets.push(Ticket{root_recipe,');right=s.index('out.push(b);return Ok(())',left)
    old=s[left:right]
    s=s[:left]+'''            if self.instance_mode!=0{
                self.claim_counts.attached+=1;
                let id=self.claim_counts.attached;
                if self.detailed{
                    self.tickets.push(Ticket{root_recipe:root_recipe.clone(),local_token_id:id,run:self.run,rule:self.rule,width:c.width,anchors:p.anchors,
                        inputs:c.rule.inputs.iter().map(|i|b.values[i].clone()).collect(),ordinal:0});
                }
                b.ordinary_id=id;
                b.direct_claim=Some(DirectClaim{id:if self.instance_mode==2{id^1}else{id},root:root_recipe,rule:self.rule,width:c.width});
            }else{
'''+old+'''            }
            '''+s[right:]
    p.write_text(s+'\ninclude!("source_instance_claim.rs");\n');copyfile(HERE/'claim.rs',src/'source_instance_claim.rs')
    p=src/'runtime.rs';s=p.read_text()
    old='''        crate::ordinary_witness::assert_proposal_inputs(b.ordinary_id,&b.values,&self.graph.program.rules[rid].inputs);
        crate::ordinary_witness::commit(b.ordinary_id,rid);'''
    s=change(s,old,'''        let direct_root = if let Some(mark)=b.direct_claim.take(){
            Some(crate::ordinary_witness::take_instance_claim(b.ordinary_id,rid,mark,&b.values,&self.graph.program.rules[rid].inputs)?)
        }else{
'''+old+'''
            None
        };''')
    s=change(s,'||crate::ordinary_witness::allocation_recipe(b.ordinary_id)',
             '||direct_root.unwrap_or_else(||crate::ordinary_witness::allocation_recipe(b.ordinary_id))')
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';s=p.read_text()
    marker='        if req["packed_single"]==true {'
    s=change(s,marker,'''        ordinary_witness::configure_instance_claim(req["instance_claim"].as_u64().unwrap_or(0).try_into().map_err(|_|"invalid instance-claim mode")?)?;
'''+marker)
    p.write_text(s)
