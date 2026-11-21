"""Route original, globally clipped quotas within physical header-layout classes."""
from pathlib import Path
from shutil import copyfile

HERE = Path(__file__).resolve().parent


def replace(s, old, new):
    if s.count(old) != 1:
        raise ValueError(old)
    return s.replace(old, new)


def install(crate):
    f = crate / "src/speculative_staging.rs"
    s = f.read_text()
    s = replace(s, "    wave_demand: WaveDemand,", "    router: Router,\n    wave_demand: WaveDemand,")
    s = replace(s, "        Ok(Self {\n            wave_demand,", """        let routing=Routing::parse(&cfg["layout_routing"])?;
        if routing.is_some() && !(matches!(wave_demand,WaveDemand::Delay) || (matches!(routing,Some(Routing::Original)) && matches!(wave_demand,WaveDemand::EntryForecast))){return Err("fixed-layout routing requires delayed original quotas".into());}
        Ok(Self {
            router: Router{mode:routing,..Default::default()},wave_demand,""")
    s = replace(s, "        let slab = self.fill_slab(g, &forecasts);",
                "        self.route_layout_budgets(g,&mut forecasts);\n        let slab = self.fill_slab(g, &forecasts);")
    s = replace(s, "        let history = self", "        self.audit_layout_run();\n        let history = self")
    s = replace(s, "            s.borrow_mut().finish();", """            let mut state=s.borrow_mut();
            if state.router.mode.is_some() && state.wave_demand.delayed() && state.epoch!=0 && state.first_verify.is_none(){
                state.router.quiet_runs+=1;
                state.allocate_after_issue(self);
            }
            state.finish();""")
    s = replace(s, 'json!({"wave_demand":self.demand_counts,',
                'json!({"layout_runs":std::mem::take(&mut self.router.rows),"quiet_runs":self.router.quiet_runs,"wave_demand":self.demand_counts,')
    f.write_text(s+'\ninclude!("layout_budget_route.rs");\n')
    copyfile(HERE / "route.rs", f.with_name("layout_budget_route.rs"))
