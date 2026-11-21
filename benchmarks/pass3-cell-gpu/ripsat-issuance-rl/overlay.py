from pathlib import Path
from shutil import copyfile
from runpy import run_path
HERE=Path(__file__).resolve().parent
edit=run_path(str(HERE.parent/'ripsat-set-receipt/overlay.py'))['edit']

def install(crate):
    src=crate/'src'
    strict=src/'strict_named.rs'
    copyfile(HERE/'actor.rs',src/'issuance_actor.rs')
    with strict.open('a') as file:
        file.write('\ninclude!("issuance_actor.rs");\n')
    edit(strict,'struct State {set_plan:', 'struct State {actor:Option<Actor>,set_plan:')
    edit(strict,'s.set_plan=plan_set(spec,g,&s)?;', '''s.set_plan=plan_set(spec,g,&s)?;
    s.actor=Actor::parse(&spec["issuance_actor"])?;
    if s.actor.is_some() && s.set_plan.is_none(){return Err("issuance actor requires a checked continuation".into());}''')
    # Rule 143 has one independent parent. The page retains the checked full
    # program; each token seals its own choice into its existing parent word.
    page=src/'adaptive_root_page.rs'
    edit(page,'let refs = match w[i] {','let leaf = w[i] >> 63 != 0;\n        let refs = match w[i] & !(1u64<<63) {')
    edit(page,'let row = if w[i] == 1','let row = if w[i] & !(1u64<<63) == 1')
    edit(page,'strict_code:(w[4]>>32) as usize','strict_code:if leaf {0} else {(w[4]>>32) as usize}')
    edit(page,'words.extend([tag, addr, v]);',
         'let action=crate::strict_named::leaf_bit(template,state.serial,inputs.len(),run.saturating_sub(version));\n            words.extend([tag|action, addr, v]);')
    edit(strict,'json!({"set_publication":s.set_counts,','''json!({"issuance_actor":s.actor.as_ref().map(|a|json!({"decisions":a.decisions,"tokens":a.tokens})),
           "set_publication":s.set_counts,''')
    session=crate/'examples/joint_witness_session.rs'
    # A generated training environment runs the same rule code and verifier.
    # Explicit opt-in keeps target benchmarking and ordinary source loading separate.
    anchor='let mut runtime = Executor::new(Graph::new(program.clone())?, false);'
    edit(session,anchor,'''let mut episode=program.clone();
        if let Some(rows)=req.get("generated_get_inputs") {
            if std::env::var_os("EGGFUSE_GENERATED_GET_EPISODES").is_none() || one_shot {
                return Err("generated input requires the training session".into());
            }
            episode.initial=serde_json::from_value(rows.clone())?;
            episode.control=vec![serde_json::json!({"repeat":4,"body":{"run":"always-run"}})];
        }
        let mut runtime = Executor::new(Graph::new(episode)?, false);''')
