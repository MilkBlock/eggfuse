from pathlib import Path
from shutil import copyfile
from textwrap import dedent, indent

HERE = Path(__file__).resolve().parent


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError(old)
    return source.replace(old, new)


def install(crate):
    target = crate / "src/speculative_staging.rs"
    s = target.read_text()
    s = replace(s, "pub(crate) struct Staging {",
                "pub(crate) struct Staging {\n    wave_demand: WaveDemand,\n    demand_counts: DemandCounts,")
    s = replace(s, "        Ok(Self {\n            timing,", """        let wave_demand = WaveDemand::parse(&cfg["wave_demand"])?;
        if wave_demand.delayed() && !(matches!(timing, Timing::Run) && storage == Storage::Group) {
            return Err("wave demand requires original Run groups".into());
        }
        Ok(Self {
            wave_demand, demand_counts: Default::default(),
            timing,""")
    s = replace(s, "let n = if matches!(self.timing, Timing::Run) {",
                "let n = if matches!(self.timing, Timing::Run) && self.wave_demand.uses_entry() {")
    start = s.index("            self.stats.requested += n;\n        }\n        if matches!")
    end = s.index("    pub(crate) fn page(", start)
    block = s[start:end]
    inner = block.split("            self.stats.rule_vectors += 1;", 1)[1].rsplit("        }\n    }", 1)[0]
    s = s[:start] + """            if !self.wave_demand.delayed() { self.stats.requested += n; }
        }
        if matches!(self.timing, Timing::Run) && !self.wave_demand.delayed() {
            self.allocate_forecasts(g, forecasts);
        }
    }
    fn allocate_forecasts(&mut self, g: &Graph, mut forecasts: Vec<(usize, usize)>) {
        self.stats.rule_vectors += 1;
""" + indent(dedent(inner).strip("\n"), "        ") + "\n    }\n" + s[end:]
    s = replace(s, "handle: (watch || (granted>0 && self.storage==Storage::Named)).then_some(handle)",
                "handle: (watch || (self.wave_demand.delayed() && self.first_verify.is_none() && self.fault!=1) || (granted>0 && self.storage==Storage::Named)).then_some(handle)")
    s = replace(s, 'json!({"counts":self.stats,"samples":', 'json!({"wave_demand":self.demand_counts,"counts":self.stats,"samples":')
    s = replace(s, "if state.first_verify.is_none(){state.first_verify=Some((state.issued_this_run,state.used_budget));}",
                """if state.first_verify.is_none() {
                if state.wave_demand.delayed() { state.allocate_after_issue(self); }
                state.first_verify = Some((state.issued_this_run, state.used_budget));
            }""")
    target.write_text(s + '\ninclude!("wave_demand.rs");\n')
    copyfile(HERE / "demand.rs", target.with_name("wave_demand.rs"))
