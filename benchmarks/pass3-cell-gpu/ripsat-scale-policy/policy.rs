// Choose stop/extend at each licensed edge before the external root is checked.
#[derive(Deserialize)]
struct ScaleConfig {
    weights: [f32; 7],
    mode: String,
    seed: u64,
}
struct ScalePolicy {
    config: ScaleConfig,
    rng: u64,
    features: [Vec<[f32;7]>; 2],
    greedy: [usize;2],
    source_op: usize,
    admitted: Vec<u64>,
    receiver_reads: Option<BTreeMap<(u64,usize),u64>>,
    choices: [u64; 3],
    trace: Vec<(u64, usize, [f32; 7], bool)>,
}
impl ScalePolicy {
    fn parse(spec: &J, plan:Option<&SetPlan>, g:&Graph) -> Result<Option<Self>> {
        if spec.is_null() { return Ok(None); }
        let config: ScaleConfig = serde_json::from_value(spec.clone()).map_err(|e|e.to_string())?;
        if !config.weights.iter().all(|w|w.is_finite()) ||
            !matches!(config.mode.as_str(),"sample"|"greedy"|"leaf"|"prefix"|"full") {
            return Err("invalid scale policy".into());
        }
        let plan=plan.ok_or("no verified scale program")?;
        let edges=[plan.first,plan.second];
        let features=std::array::from_fn(|class| edges.iter().enumerate().map(|(i,edge)|{
            let width=g.program.rules[edge[2]].inputs.len() as f32 / 4.;
            let set=f32::from(i==1); // plan_set verifies Let then Set
            let source=class as f32;
            let other=1.-source;
            [other,source,other*set,source*set,other*width,source*width,other/(i+1) as f32]
        }).collect::<Vec<_>>());
        let greedy=std::array::from_fn(|class|features[class].iter().take_while(|x|
            config.weights.iter().zip(x.iter()).map(|(w,x)|w*x).sum::<f32>()>=0.
        ).count());
        let receiver_reads=(config.mode=="sample").then(BTreeMap::new);
        Ok(Some(Self{rng:config.seed,admitted:vec![],receiver_reads,config,features,greedy,source_op:plan.second[1],
            choices:[0;3],trace:vec![]}))
    }

    fn extend(&mut self, serial:u64, depth:usize, x:[f32;7]) -> bool {
        let score:f32 = self.config.weights.iter().zip(x).map(|(w,x)|w*x).sum();
        let take = match self.config.mode.as_str() {
            "leaf" => false, "prefix" => depth==0, "full" => true,
            "sample" => {
                self.rng=self.rng.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                let u=(self.rng>>40) as f32 / 16777216.;
                u < 1./(1.+(-score).exp())
            }
            _ => score>=0.,
        };
        if self.config.mode=="sample" {self.trace.push((serial,depth,x,take));}
        take
    }
}

pub(crate) fn scale_bits(code:usize, serial:u64, dep:Option<Dependency>)->Option<u64>{
    if code & (1usize<<63)==0 {return Some(0);}
    S.with_borrow_mut(|s|{
        let s=s.as_mut()?;
        let policy=s.scale.as_mut()?;
        let class=usize::from(matches!(dep,Some(Dependency::Fact(f)) if f.op as usize==policy.source_op));
        let depth=match policy.config.mode.as_str() {
            "greedy"=>policy.greedy[class],
            "leaf"=>0,
            "prefix"=>1,
            "full"=>policy.features[class].len(),
            _=>{
                let mut count=0;
                for i in 0..policy.features[class].len() {
                    if !policy.extend(serial,i,policy.features[class][i]) {break}
                    count+=1;
                }
                count
            }
        };
        policy.choices[depth]+=1;
        if depth==0 {s.set_counts.encoded-=1;}
        Some([1u64<<63,1u64<<62,0][depth])
    })
}
