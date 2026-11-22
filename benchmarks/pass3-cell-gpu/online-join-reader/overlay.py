from pathlib import Path
from shutil import copyfile


def install(crate):
    d=Path(__file__).resolve().parent
    copyfile(d/'issuer.rs',crate/'src/live_issuer.rs')
    with (crate/'src/lib.rs').open('a') as stream:
        stream.write('\npub mod live_issuer;\n')
    path=crate/'src/named_only.rs'
    receiver = path.read_text()
    receiver = receiver.replace("    pub rejected: usize,", "    pub rejected: usize,\n    pub primitive_rejects: BTreeMap<String,u64>,")
    for anchor in ("let Some(value) = g.primitive(op, &values, ty)? else {",
                   "if !g.bind(dest, &value, &mut frame) {"):
        if receiver.count(anchor) != 1:
            raise ValueError("unexpected primitive verification site")
        receiver = receiver.replace(anchor, anchor+"\n                    *self.primitive_rejects.entry(op.clone()).or_default() += 1;")
    receiver = receiver.replace("pub struct Packet {", "pub struct Packet {\n    #[serde(default)] family: Option<usize>,")
    receiver = receiver.replace("pub struct Inbox {", "pub struct Inbox {\n    pub families: Families,")
    receiver = receiver.replace("        wm: u64,", "        wm: u64, family:Option<usize>, capture:&mut Vec<FamilyRow>,")
    receiver = receiver.replace("            self.rejected += 1;", """            if packet.family!=family {return Err("unlicensed query family".into());}
            if family.is_some(){self.families.signed+=1;}
            self.rejected += 1;""")
    receiver = receiver.replace("            output.push(Instance::matched(", """            if family.is_some() {
                capture.push(FamilyRow{serial:self.families.signed,values:frame,evidence:QueryFacts::Ports(receipts.clone()),epoch});
            }
            output.push(Instance::matched(""")
    receiver = receiver.replace("                epoch,\n            ));",
        "                epoch,\n            ));\n            if family.is_some() {output.last_mut().unwrap().family_token=Some((self.families.signed,false));}")
    for name in ("runtime", "cell_match", "execute_kernel", "query_workers", "view_exec"):
        frame = crate/"src"/(name+".rs")
        content = frame.read_text().replace("ordinary_id:0,", "family_token:None,ordinary_id:0,")
        if name=="cell_match":
            content=content.replace("pub(crate) ordinary_id:usize,", "pub(crate) family_token:Option<(u64,bool)>,\n    pub(crate) ordinary_id:usize,")
        if name=="runtime":
            anchor="        let result=self.apply_owned(rid,b,"
            if content.count(anchor)!=1:
                raise ValueError("unexpected RHS commit site")
            content=content.replace(anchor,"        let family_token=b.family_token;\n"+anchor)
            anchor="        crate::joint_root::end();"
            content=content.replace(anchor,"        if result.is_ok(){self.issued.families.committed(rid,family_token)?;}\n"+anchor,1)
        frame.write_text(content)
    path.write_text(receiver+'\ninclude!("same_query.rs");\n')
    copyfile(d/'same_query.rs',crate/'src/same_query.rs')
    with path.open('a') as stream:
        stream.write('''
impl Packet {
    pub(crate) fn issue(family:Option<usize>,run:usize,rule:usize,parents:Vec<(Dependency,u64)>)->Self{Self{family,run,rule,parents}}
}
''')
    path=crate/'src/runtime.rs'
    text=path.read_text()
    lines=text.splitlines(keepends=True)
    hits=[i for i,line in enumerate(lines) if "let rows = self.issued.verify(" in line]
    if len(hits)!=1:
        raise ValueError('unexpected rule entry')
    lines[hits[0]]="        let rows=self.issued.family_matches(&self.graph,self.steps.len()+1,rid,self.watermarks[rid])?;\n"
    path.write_text("".join(lines))
    copyfile(d/'session.rs',crate/'examples/joint_witness_session.rs')
