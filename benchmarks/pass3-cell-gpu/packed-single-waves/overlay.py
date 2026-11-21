from pathlib import Path
from shutil import copyfile
HERE = Path(__file__).resolve().parent


def change(s, old, new):
    if s.count(old) != 1:
        raise ValueError(old)
    return s.replace(old, new)


def install(crate):
    src = crate / "src"
    p = src / "single_witness.rs"
    s = change(p.read_text(), "pub(crate) struct Trial{", """pub(crate) struct Trial{
    packed: bool, packed_banks: BTreeMap<usize,PackedOffers>, packed_stats: PackedStats,""")
    s = change(s, "Ok(Self{waiting_wave:","Ok(Self{packed:false,packed_banks:Default::default(),packed_stats:Default::default(),waiting_wave:")
    s = change(s, "let issued=offers.len();","""if !self.packed {
            let bytes=offers.capacity()*std::mem::size_of::<(Token,[u8;N],bool)>();
            self.packed_stats.total_queue_capacity_bytes+=bytes;
            self.packed_stats.pending_bytes+=bytes;
            self.packed_stats.peak_pending_bytes=self.packed_stats.peak_pending_bytes.max(self.packed_stats.pending_bytes);
        }
        let issued=self.packed_banks.get(&rid).map_or(offers.len(),|b|b.lanes.len());""")
    s = change(s, "            crate::ordinary_witness::wave_single_consumed();","""            if !self.packed {
                self.packed_stats.pending_bytes -= offers.capacity()*std::mem::size_of::<(Token,[u8;N],bool)>();
            }
            crate::ordinary_witness::wave_single_consumed();""")
    a = s.index("        let verification_start=self.rows.profile")
    b = s.index("        for (token,f,send) in offers{", a)
    s = s[:a] + """        if let Some(bank)=self.packed_banks.remove(&rid) {
            assert!(offers.is_empty());
            self.packed_stats.pending_bytes-=bank.capacity_bytes();
            let issued=bank.lanes.len();
            return self.verify_offers(g,rid,wm,&p,n,delivered,issued,bank.iter(rid));
        }
        let issued=offers.len();
        self.verify_offers(g,rid,wm,&p,n,delivered,issued,offers.into_iter().map(|(t,f,s)|(t,f,s,None)))
    }
    fn verify_offers<'a>(&mut self,g:&Graph,rid:usize,wm:u64,p:&Plan,n:usize,delivered:usize,issued:usize,
        offers:impl Iterator<Item=(Token,[u8;N],bool,Option<(&'a crate::joint_root::RootPage,usize)>)>)->Result<Vec<Instance>> {
        let r=&g.program.rules[rid];
""" + s[a:b].replace("!offers.is_empty()", "issued!=0") + s[b:].replace(
        "        for (token,f,send) in offers{", "        for (mut token,f,send,packed_page) in offers{", 1)
    s = change(s, "let root_recipe=crate::joint_root::bind_single(", """if let Some((page,index))=packed_page {
                        token.recipe=Some(page.at(index));
                        self.packed_stats.verified+=1;
                    }
                    let root_recipe=crate::joint_root::bind_single(""")
    s = change(s,'json!({"adaptive_rows":self.rows.report(),',
               'json!({"packed":self.packed_stats,"ordinary_lane_bytes":std::mem::size_of::<(Token,[u8;N],bool)>(),"packed_lane_bytes":std::mem::size_of::<PackedLane>(),"adaptive_rows":self.rows.report(),')
    p.write_text(s+'\ninclude!("packed_offers.rs");\n')
    p = src / "adaptive_rows.rs"
    s = change(p.read_text(), "        let mut result = Vec::new();", """        let mut result = Vec::new();
        let mut packed = PackedOffers::default();""")
    s = change(s, "            let recipe = if send && !self.rows.batch {", """            if self.packed {
                if !send || !self.rows.batch || self.residual || self.mode!="learned" {
                    return Err("packed issuance needs learned, page-issued exclusive proposals".into());
                }
                packed.lanes.push(PackedLane {source:h.source,version:h.version,token_id:self.serial,score,initial:h.initial});
                emitted+=1;
                continue;
            }
            let recipe = if send && !self.rows.batch {""")
    s = change(s, "        if self.rows.batch && !result.is_empty() {", """        if self.packed && !packed.lanes.is_empty() {
            packed.seal(g,rid,p.pivot,width(action));
            let bytes=packed.capacity_bytes();
            self.packed_stats.banks+=1;
            self.packed_stats.lanes+=packed.lanes.len();
            self.packed_stats.pages+=packed.pages.len();
            self.packed_stats.total_queue_capacity_bytes+=bytes;
            self.packed_stats.pending_bytes+=bytes;
            self.packed_stats.peak_pending_bytes=self.packed_stats.peak_pending_bytes.max(self.packed_stats.pending_bytes);
            if self.packed_banks.insert(rid,packed).is_some(){return Err("unconsumed packed rule page".into());}
        }
        if self.rows.batch && !result.is_empty() {""")
    p.write_text(s)
    p = src / "runtime.rs"
    s = change(p.read_text(),"    pub fn set_single_winner_archive(", """    pub fn use_packed_single(&mut self)->Result<()> {
        self.stage_spine.single.as_mut().ok_or("packed singles require an active learned issuer")?.enable_packed()
    }
    pub fn set_single_winner_archive(""")
    p.write_text(s)
    p = crate / "examples/joint_witness_session.rs"
    s = change(p.read_text(),"        runtime.set_single_winner_archive(", """        if req["packed_single"]==true {
            if req["proposal_wave"].as_u64().unwrap_or(0)==0 {return Err("packed pages need wave issuance".into());}
            runtime.use_packed_single()?;
        }
        runtime.set_single_winner_archive(""")
    p.write_text(s)
    copyfile(HERE / "packed.rs", src / "packed_offers.rs")
    with (src / "packed_offers.rs").open("a") as out:
        out.write('impl Trial {pub(crate) fn enable_packed(&mut self)->Result<()> { if self.mode!="learned" || self.residual {return Err("packed singles require exclusive learned policy".into());} self.packed=true;Ok(())}}\n')
