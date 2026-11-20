from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent

def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)

def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=change(s,'struct Store {','struct Store {lazy_eq:LazyEquations,')
    s=change(s,'let s=Store{','let s=Store{lazy_eq:LazyEquations::default(),')
    s=change(s,'"equations":s.equations.stats,','"lazy_eq":s.lazy_eq.stats,"equations":s.equations.stats,')
    p.write_text(s+'\ninclude!("lazy_equations.rs");\n');shutil.copyfile(HERE/'lazy.rs',src/'lazy_equations.rs')
    p=src/'incremental_raw.rs';s=p.read_text()
    s=change(s,'        let eq = if self.equations.mode!=0{', '''        let delayed=if self.lazy_eq.mode>=2{self.equations.plans.get(self.rule).and_then(|e|e.clone())}else{None};
        let eq = if self.equations.mode!=0 && delayed.is_none(){''')
    s=change(s,'            let row = &left.frame.rows[l];','            let row = &left.frame.rows[l];\n            let mut left_output=None;')
    s=change(s,'if let Some(e)=&eq && (reverse.is_some()||!narrow_index){','if let Some(e)=&eq && self.lazy_eq.mode==0 && (reverse.is_some()||!narrow_index){')
    marker='                self.counts.approximate_visits += 1;'
    s=change(s,marker,'''                if self.lazy_eq.mode==1 && let Some(e)=&eq{
                    self.lazy_eq.stats.checks+=1;
                    if e.left[l]==u32::MAX || e.left[l]!=e.right[r]{self.lazy_eq.stats.rejected+=1;continue;}
                }
                if let Some(eq)=&delayed{
                    self.lazy_eq.stats.checks+=1;
                    let a=if let Some(value)=left_output{self.lazy_eq.stats.left_reused+=1;value}else{
                        let value=self.lazy_equation_value(c,eq,0,row);
                        left_output=Some(value);value
                    };
                    let b=self.lazy_equation_value(c,eq,1,other);
                    if matches!((a,b),(Some(x),Some(y)) if x==u32::MAX || x!=y){
                        self.lazy_eq.stats.rejected+=1;continue;
                    }
                }
'''+marker);p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),a,'''        if let Some(mode)=req["lazy_equations"].as_u64(){ordinary_witness::configure_lazy(mode)?;}
'''+a))
