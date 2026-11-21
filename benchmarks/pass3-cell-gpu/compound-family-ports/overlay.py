from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent
def change(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)
def install(crate):
    src=crate/'src';p=src/'learned_pair_family.rs';s=p.read_text()
    def patch(a,b):
        nonlocal s
        s=change(s,a,b)
    patch('type FamilyKey = u32;', 'type FamilyKey = u64;')
    patch('fn wire(&self) -> Vec<u8> {','fn wire(&self,compound:bool) -> Vec<u8> {')
    patch('72 + 4 * self.keys.len()', '72 + (if compound{8}else{4}) * self.keys.len()')
    patch('            self.extent as u64,','            self.extent as u64 | ((compound as u64)<<63),')
    patch('            out.extend_from_slice(&k.to_le_bytes());','            if compound{out.extend_from_slice(&k.to_le_bytes());}else{out.extend_from_slice(&(*k as u32).to_le_bytes());}')
    patch('fn read(buf: &[u8], id: u64) -> Result<Self> {','fn read(buf: &[u8], id: u64,compound:bool) -> Result<Self> {\n        let width=if compound{8}else{4};')
    patch('buf.len() > 104 || (buf.len() - 72) % 4 != 0','buf.len() > 72+8*width || (buf.len() - 72) % width != 0')
    a=s.index('        let keys = buf[72..]');b=s.index('        Ok(Self {',a)
    s=s[:a]+'''        if (words[8]>>63 != 0)!=compound{return Err("invalid family signature layout".into());}
        let keys = buf[72..].chunks_exact(width).map(|p|if compound{u64::from_le_bytes(p.try_into().unwrap())}else{u64::from(u32::from_le_bytes(p.try_into().unwrap()))}).collect();
'''+s[b:]
    patch('extent: words[8] as usize,','extent: (words[8]&!(1u64<<63)) as usize,')
    patch('    mode: u8,','''    compound:bool,corrupt_compound:bool,compound_work:CompoundWork,
    scalar_columns:HashMap<(usize,usize),ScalarColumn>,mode: u8,''')
    patch('hist: HashMap<(usize, usize),','hist: HashMap<(usize, usize,usize),')
    patch('public: HashMap<(usize, usize),','public: HashMap<(usize, usize,usize),')
    patch('        s.family.mode = mode as u8;', '''        s.family.compound=cfg["compound"]==true;s.family.corrupt_compound=cfg["bad_scalar"]==true;
        s.family.mode = mode as u8;''')
    patch('codes: &[Port]) -> Rc<CodeStats> {','codes: &[Port], second:Option<&[u32]>) -> Rc<CodeStats> {')
    patch('let tag = (step.table, col);','let tag=(step.table,col,if second.is_some(){1+self.rule}else{0});')
    patch('for (r, p) in f.rows.iter().zip(codes) {','for (i,(r, p)) in f.rows.iter().zip(codes).enumerate() {')
    patch('m.entry(signature(*p, false, self.views))','m.entry(paired_code(signature(*p,false,self.views),second.map(|q|q[i])))')
    patch('        g: &Graph,\n        step: &StackStep,','        c:&Context,eq:Option<&Equation>,side:usize,\n        step: &StackStep,')
    patch('        let key = (step.table, col);','        let g=c.graph;let key=(step.table,col,if eq.is_some(){1+2*self.rule+side}else{0});')
    patch('let code = signature(self.code(&r.values[col]), false, self.views);','''let primary=signature(self.code(&r.values[col]),side==0,self.views);
                let secondary=if let Some(eq)=eq{self.family.compound_work.receiver_computed+=1;
                    Some(self.lazy_equation_value(c,eq,side,&r).ok_or("independent compound source type unavailable")?)
                }else{None};
                let code=paired_code(primary,secondary);''')
    patch('        right: &CodeStats,','        right: &CodeStats, second:Option<&[u32]>,')
    patch('heads.entry(signature(*l, true, self.views))','heads.entry(paired_code(signature(*l,true,self.views),second.map(|q|q[lo+i])))')
    patch('let mut push = |keys: Vec<u32>,','let mut push = |keys: Vec<u64>,')
    patch('stat.wire_bytes += (72 + keys.len() * 4) as u64;', '''let compound=second.is_some();let span_bytes=(72+keys.len()*(if compound{8}else{4}))as u64;
                stat.wire_bytes+=span_bytes;
                if compound{self.family.compound_work.compound_packets+=1;self.family.compound_work.compound_keys+=keys.len() as u64;self.family.compound_work.compound_bytes+=span_bytes;}''')
    patch('                    .wire(),','                    .wire(compound),')
    patch('        let hist = self.family_hist(right, rc, &rp);','''        let eq=self.equations.plans.get(self.rule).and_then(|e|e.clone());
        let second=if self.family.compound && let Some(eq)=eq.as_ref(){
            self.family.compound_work.planned+=1;
            let left_scalar=self.family_scalar_column(c,left,eq,0);
            let right_scalar=self.family_scalar_column(c,right,eq,1);
            left_scalar.zip(right_scalar)
        }else{None};
        let compound=second.is_some();
        if self.family.compound && eq.is_some(){if compound{self.family.compound_work.admitted+=1;}else{self.family.compound_work.fallback+=1;}}
        let hist=self.family_hist(right,rc,&rp,second.as_ref().map(|p|p.1.as_slice()));''')
    patch('self.issue_families(c, steps, &lp, &hist, cut);','self.issue_families(c,steps,&lp,&hist,second.as_ref().map(|p|p.0.as_slice()),cut);')
    patch('self.family_public(c.graph, left, lc)?','self.family_public(c,eq.as_ref().filter(|_|compound),0,left,lc)?')
    patch('self.family_public(c.graph, right, rc)?','self.family_public(c,eq.as_ref().filter(|_|compound),1,right,rc)?')
    patch('        let eq = self.equations.plans.get(self.rule).and_then(|e| e.clone());','')
    patch('for (offset, wire) in packets.into_iter().enumerate() {','''for (offset, mut wire) in packets.into_iter().enumerate() {
            if compound && self.family.corrupt_compound{wire[79]^=0x80;}''')
    patch('Packet::read(&wire, first_action + offset as u64)?','Packet::read(&wire, first_action + offset as u64,compound)?')
    p.write_text(s+'\ninclude!("compound_family_scalar.rs");\n');copyfile(HERE/'compound.rs',src/'compound_family_scalar.rs')
    p=src/'ordinary_witness.rs';p.write_text(change(p.read_text(),'"family_work":s.family.metrics,','"compound_work":s.family.compound_work,"family_work":s.family.metrics,'))
