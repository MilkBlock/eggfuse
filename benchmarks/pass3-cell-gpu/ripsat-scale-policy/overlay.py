"""Carry the sampled stopping position in the existing root word."""
from pathlib import Path
from runpy import run_path
from shutil import copyfile

HERE = Path(__file__).resolve().parent
edit = run_path(str(HERE.parent / "ripsat-set-receipt/overlay.py"))["edit"]


def install(crate):
    src = crate / "src"
    strict = src / "strict_named.rs"
    page = src / "adaptive_root_page.rs"
    pub = src / "ripsat_set_publication.rs"
    copyfile(HERE / "policy.rs", src / "scale_policy.rs")
    with strict.open("a") as out:
        out.write('\ninclude!("scale_policy.rs");\n')
    edit(strict, "struct State {", "struct State {scale:Option<ScalePolicy>,")
    edit(strict, 's.actor=Actor::parse', '''s.scale=ScalePolicy::parse(&spec["scale_policy"],s.set_plan.as_ref(),g)?;
    if s.scale.is_some() && (!s.block_enabled || !spec["issuance_actor"].is_null()){
        return Err("scale policy requires one checked block issuer".into());
    }
    s.actor=Actor::parse''')
    edit(strict, '"issuance_actor":s.actor', '"scale_policy":s.scale.as_ref().map(|a|json!({"choices":a.choices,"trace":a.trace})), "issuance_actor":s.actor')
    edit(page, 'let action=crate::strict_named::leaf_bit', 'let action=crate::strict_named::scale_bits(template,state.serial,dep).unwrap_or_else(||crate::strict_named::leaf_bit')
    edit(page, 'inputs.len(),run.saturating_sub(version));', 'inputs.len(),run.saturating_sub(version)));')
    for old in ('match w[i] & !(1u64<<63)', 'if w[i] & !(1u64<<63)'):
        edit(page, old, old.replace('1u64<<63', '3u64<<62'))
    edit(page, 'if leaf {0} else {(w[4]>>32) as usize}', '''if leaf {0} else {
            (w[4]>>32) as usize | if w[i] & (1u64<<62)!=0 {1usize<<30} else {0}
        }''')
    edit(strict, 'struct Permit {', 'struct Permit {prefix_only:bool,')
    edit(strict, 'struct Owner {', 'struct Owner {prefix_only:bool,')
    edit(strict, 'block:internal.block,', 'prefix_only:internal.prefix_only,block:internal.block,')
    edit(strict, '                block:s.block_enabled', '                prefix_only:prefix,block:s.block_enabled')
    edit(strict, 'if code != selection(s,rid)', '''let prefix=code & (1usize<<30)!=0;
            if prefix && (s.scale.is_none() || code & (1usize<<31)==0) {return Err("unauthorized prefix".into())}
            if code & !(1usize<<30) != selection(s,rid)''')
    edit(strict, 'let owner = Owner {', 'let owner = Owner {prefix_only:a.prefix_only,')
    edit(pub, 'let o = Owner {block:', 'let o = Owner {prefix_only:false,block:')
    edit(pub, 'if s.physical != Some(cell)', 'if a.prefix_only || s.physical != Some(cell)')
    # Only sampled training rollouts need a per-root receiver ledger.
    edit(strict, "s.receipt_index.work.row_reads+=1;", """s.receipt_index.work.row_reads+=1;
            if let Some(ledger)=s.scale.as_mut().and_then(|p|p.receiver_reads.as_mut()) {
                *ledger.entry((o.root,o.path.len()-1)).or_default()+=1;
            }""")
    edit(strict, '"choices":a.choices,"trace":a.trace', '''"choices":a.choices,"trace":a.trace,
        "receiver_reads":a.receiver_reads.as_ref().map(|m|m.iter().map(|(&(root,step),&n)|(root,step,n)).collect::<Vec<_>>())''')
    edit(strict, "s.set_counts.admissions+=1;", """s.set_counts.admissions+=1;
                if let Some(p)=s.scale.as_mut().filter(|p|p.receiver_reads.is_some()) {p.admitted.push(serial);}""")
    edit(strict, '"trace":a.trace,', '"trace":a.trace,"admitted":a.admitted,')
