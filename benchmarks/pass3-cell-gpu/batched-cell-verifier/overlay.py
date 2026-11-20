from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def rep(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)


def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=rep(s,'struct Store {','struct Store {blocks:BlockCounts,')
    s=rep(s,'let s=Store{','let s=Store{blocks:BlockCounts::default(),')
    s=rep(s,'"premises":s.premises.stats,','"blocks":s.blocks,"premises":s.premises.stats,')
    start=s.index('            if p.picks<2{return Err("unscored source tuple"')
    end=s.index('\n        }',start)
    original=s[start:end]
    s=s[:start]+'            return self.complete_source_binding(c,p,out);'+s[end:]
    s+='\nimpl Store {fn complete_source_binding(&mut self,c:&Context,mut p:Prefix,out:&mut Vec<Instance>)->Result<()>{\n'+original+'\n}}\ninclude!("batched_block.rs");\n'
    p.write_text(s);copyfile(HERE/'block.rs',src/'batched_block.rs')
    p=src/'page_premises.rs';s=p.read_text()
    s=rep(s,'struct PageProgram {','struct PageProgram {\n    tail:BlockTail,')
    s=rep(s,'        Some(Self {\n            roles,','        Some(Self {\n            tail:BlockTail::compile(rule,plan,&first,roles.len())?,\n            roles,')
    s=rep(s,'1..=6','1..=9')
    s=rep(s,'let shared = matches!(mode, 2 | 4 | 6);','let block=mode>=7;\n        let shared = block || matches!(mode, 2 | 4 | 6);')
    s=rep(s,'let wired = matches!(mode, 3 | 4 | 6);','let wired = block || matches!(mode, 3 | 4 | 6);')
    s=rep(s,'        let mut cache =','        let mut ports=PortMemo::default();\n        let mut cache =')
    s=rep(s,'matches!(mode, 5 | 6)','matches!(mode, 5 | 6 | 8)')
    s=rep(s,'            let mut exact = base.clone();','''            let mut exact=if block && !self.detailed{
                Prefix{root_recipe:None,latents:BTreeMap::new(),slots:Slots::default(),witness:vec![],anchors:vec![],epoch:0,picks:0}
            }else{base.clone()};''')
    s=rep(s,'                    exact.witness[role.atom] = Some(row.witness);','                    if !block || self.detailed{exact.witness[role.atom] = Some(row.witness);}')
    s=rep(s,'            if wired && pass {','            if wired && pass && (!block || self.detailed) {')
    a='            self.descend(c, c.pick_count, exact, out, &mut unused)?;'
    s=rep(s,a,'''            if block{
                let epoch=exact.epoch;
                self.run_block(c,&plan,&rows,epoch,exact,&mut ports,out)?;
            }else {
'''+a+'\n            }')
    p.write_text(s)
