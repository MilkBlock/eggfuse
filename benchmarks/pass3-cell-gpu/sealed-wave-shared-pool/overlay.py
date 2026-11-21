"""Compose the existing whole-wave demand and cross-rule storage overlays."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location("wave_demand_overlay", HERE.parent / "wave-demand-policy/overlay.py")
wave = module_from_spec(spec)
spec.loader.exec_module(wave)
change = wave.replace


def install(crate):
    target = crate / "src/speculative_staging.rs"
    s = target.read_text()
    # Normalize the two initialization and report anchors consumed by both overlays.
    init = "        Ok(Self { pool:Pool{shared,fault:layout_fault,..Default::default()},\n            timing,"
    s = change(s, init, "        Ok(Self {\n            timing,")
    s = change(s, 'json!({"pool":self.pool.counts,"counts":self.stats,"samples":',
               'json!({"counts":self.stats,"samples":')
    target.write_text(s)
    wave.install(crate)
    s = target.read_text()
    s = change(s, "            wave_demand, demand_counts: Default::default(),",
               "            wave_demand, demand_counts: Default::default(), pool:Pool{shared,fault:layout_fault,..Default::default()},")
    s = change(s, 'json!({"wave_demand":self.demand_counts,', 'json!({"pool":self.pool.counts,"wave_demand":self.demand_counts,')
    a = s.index("self.pool.records[r.pool_id].issued+=n;")
    b = s.index("        let bits=if watch", a)
    # The late forecast has no allocated donor spans at emission. The wave
    # extension already retains pending immutable handles until it knows the grants.
    s = s[:a] + """let watch=if let Some(d)=self.pool.records.get_mut(r.pool_id) {
            d.issued+=n;
            !self.pool.buckets[d.class].is_empty() && self.fault!=1
        }else{ false };
""" + s[b:]
    target.write_text(s)
    demand = target.with_name("wave_demand.rs")
    s = demand.read_text()
    s = change(s, "            let grant = rule.span.len;", """            let grant = rule.span.len;
            let donor=&mut self.pool.records[rule.pool_id];
            donor.issued=rule.now.offers;
            let eligible=!self.pool.buckets[donor.class].is_empty();""")
    s = change(s, "if grant == 0 || self.fault == 1 {", "if !eligible || self.fault == 1 {")
    demand.write_text(s)
