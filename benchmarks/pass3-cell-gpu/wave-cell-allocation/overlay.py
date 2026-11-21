from pathlib import Path

def install(crate):
    p=crate/'src/ordinary_witness.rs';s=p.read_text()
    anchor='let bank=crate::joint_root::multi_page(g.epoch,rid,c.pick_count,refs,s.page_fault)?;'
    if s.count(anchor)!=1:raise ValueError(anchor)
    # In a whole-Run wave the producer already holds a sealed page before the
    # normal validation loop starts. Name its reserved records at that point.
    p.write_text(s.replace(anchor,anchor+'''
                if g.spec_cells.is_some(){g.spec_page(rid,bank.stage_serial(),bank.count(),crate::graph::speculative::Handle::Multi(bank.clone()));}
'''))
