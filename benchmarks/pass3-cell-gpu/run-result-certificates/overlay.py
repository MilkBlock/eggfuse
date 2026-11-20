from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def change(text,old,new):
    if text.count(old)!=1:raise ValueError(old)
    return text.replace(old,new)


def install(crate):
    src=crate/'src';path=src/'projected_checks.rs';s=path.read_text()
    s=change(s,'struct ProjectedChecks {','struct ProjectedChecks {\n    cuts:ResultCertificates,')
    s=change(s,'struct ProjectedRule {','struct ProjectedRule {\n    pure_certificate:bool,')
    s=change(s,'!(1..=2).contains(&mode)','!(1..=9).contains(&mode)')
    s=change(s,'        s.mode = mode;', '''        s.mode = mode;
        if mode>=3 {
            s.cuts.mode=(mode-2).min(3) as u8;
            s.cuts.physical=match mode{7=>1,8|9=>2,_=>0};
            s.cuts.audit=self.rows.detailed;
            if (6..=8).contains(&mode){s.cuts.warm.resize(8192,None);}
            s.cuts.entries.resize_with(8192,||None);
        }''')
    s=change(s,'                Some(std::rc::Rc::new(ProjectedRule {','''                let pure_certificate=!query.steps.is_empty()
                    && r.query.iter().all(|a|a.args.iter().all(|v|match v{
                        Arg::Slot(_)=>true, Arg::Literal(v)=>matches!(v,Value::Int(_) | Value::Text(_) | Value::Float(_))})
                        && match &a.call {Call::Table(_)=>true,Call::Primitive(op,_)=>matches!(op.as_str(),"+"|"-"|"*"|"/"|"%"|">"|"<"|">="|"<="|"!="|"min"|"max")});
                Some(std::rc::Rc::new(ProjectedRule {pure_certificate,''')
    s=change(s,'        self.projected.stats.attempts += 1;', '''        let record=compiled.pure_certificate && self.projected.cuts.mode!=0 && !self.projected.cuts.held;
        if record && self.projected.cuts.probe(g,tok,wm)?{
            if self.projected.audit {
                self.projected.cuts.held=true;
                let gold=self.verify_projected(g,r,tok,wm,&mut [0;8],compiled.clone());
                self.projected.cuts.held=false;
                if gold?.is_some(){return Err("invalid retained no-binding certificate".into())}
                self.projected.cuts.stats.audited+=1;
            }
            return Ok(None)
        }
        self.projected.stats.attempts += 1;''')
    mark='        let mut receipts = smallvec::SmallVec::<[(usize, Dependency); 8]>::new();'
    s=change(s,mark,'''        let mut evidence=(record && self.projected.cuts.admit(tok)).then(||ResultCertificate{rule:tok.rid,anchor:w,anchor_epoch:row.epoch,
            run_epoch:g.epoch,unions:g.stats.unions,supports:smallvec::SmallVec::new(),missing:None,cutoff:None});
        ResultCertificate::push(&mut evidence,g,compiled.table,&row);
'''+mark)
    mark='                    let Some(found) = row.filter(|q| !q.hidden) else {\n                        return Ok(None);\n                    };'
    s=change(s,mark,'''                    let Some(found) = row.filter(|q| !q.hidden) else {
                        if let Some(e)=&mut evidence && keys.len()<=8 && keys.iter().all(|v|matches!(v,Value::Int(_) | Value::Eq(_))){
                            e.missing=Some(MissingPoint{table:*table,generation:g.query_versions[*table],key:keys.to_vec()});
                            self.projected.cuts.put(evidence,None);
                        }
                        return Ok(None);
                    };
                    ResultCertificate::push(&mut evidence,g,*table,&found);''')
    mark='let Some(v) = g.primitive(name, &keys, ty)? else {'
    s=change(s,mark,mark+'\n                        self.projected.cuts.put(evidence,None);')
    mark='&& !expected.agrees(&value, g, |i| &fields[i], &results, None)\n            {'
    s=change(s,mark,mark+'\n                self.projected.cuts.put(evidence,None);')
    s=change(s,'        if r.seminaive && epoch < wm {','        if r.seminaive{self.projected.cuts.put(evidence,Some(epoch));}\n        if r.seminaive && epoch < wm {')
    path.write_text(s+'\ninclude!("result_certificates.rs");\n')
    copyfile(HERE/'certificates.rs',src/'result_certificates.rs')
    p=src/'adaptive_rows.rs'
    p.write_text(change(p.read_text(),'"projection":self.verify.projected.stats,','"result_certificates":self.verify.projected.cuts.stats,"projection":self.verify.projected.stats,'))
    path=src/'graph.rs'
    original=path.read_text()
    start=original.index('        let op = self.program.templates[c.template]',original.index('    fn decode_fact('))
    end=original.index('        self.fact_decode_ports.set(',start)
    if 'invalid fact recipe position' not in original[start:end]:raise ValueError('fact recipe source')
    path.write_text(original[:start]+'        let (table,args,result)=self.certificate_fact_args(f,c)?;\n'+original[end:]+'\ninclude!("certificate_physical.rs");\n')
    copyfile(HERE/'physical.rs',src/'certificate_physical.rs')
