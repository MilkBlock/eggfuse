"""Attach immutable issuer identity to both page kinds and the consumed binding."""
from pathlib import Path
from shutil import copyfile

HERE = Path(__file__).resolve().parent


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(old)
    return source.replace(old, new)


def install(crate):
    src = crate / "src"
    p = src / "adaptive_root_page.rs"
    s = replace_once(p.read_text(), "pub(crate) struct RootPage {", "pub(crate) struct RootPage {\n    seal:u64,")
    p.write_text(replace_once(s, "        Some(RootPage {",
                             "        Some(RootPage {seal:mint_local_seal(state.redemption!=0),"))

    p = src / "multi_root_pages.rs"
    s = replace_once(p.read_text(), "#[derive(Debug)]\nstruct MultiPageData {",
                     "#[derive(Clone,Debug)]\nstruct MultiPageData {\n    seal:u64,")
    p.write_text(replace_once(s, "Ok(MultiPage(Rc::new(MultiPageData {",
                              "Ok(MultiPage(Rc::new(MultiPageData {seal:mint_local_seal(st.redemption!=0),"))

    p = src / "joint_root.rs"
    s = replace_once(p.read_text(), "struct State{", "struct State{redemption:u8,redemption_stats:RedemptionStats,")
    s = replace_once(s, "Some(State{stage_watch:false",
                     "Some(State{redemption:0,redemption_stats:Default::default(),stage_watch:false")
    s = replace_once(s, "struct Bound{recipe:Decoded,", "struct Bound{lane:Option<SealedLane>,recipe:Decoded,")
    if s.count("Bound{recipe,values:") != 2:
        raise ValueError("checked and ordinary binding constructors")
    s = s.replace("Bound{recipe,values:", "Bound{lane:packet.local_lane(),recipe,values:")
    s = replace_once(s, '"root_row_decodes":s.decodes,', '"redemption":s.redemption_stats,"root_row_decodes":s.decodes,')
    first = s.index("pub(crate) fn same_staged_parent(")
    last = s.index("\nimpl RootPage{pub(crate) fn stage_serial", first)
    p.write_text(s[:first] + s[last:] + '\ninclude!("sealed_lane.rs");\n')
    copyfile(HERE / "seal.rs", src / "sealed_lane.rs")

    p = crate / "examples/joint_witness_session.rs"
    anchor = "        let initial_cells = runtime.graph.stats.cells_created;"
    config = '        if let Some(n)=req["sealed_redemption"].as_u64(){eggfuse_cell_runtime::joint_root::configure_redemption(n)?;}\n'
    p.write_text(replace_once(p.read_text(), anchor, config + anchor))
