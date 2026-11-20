// Finite-domain specialization of the learned port map. Only the low F mixed bits
// are observed by either trained head. All views use the same immutable table.
const LUT_MAGIC: &[u8;8] = b"EFCODE01";
struct BakedCodes {
    words: Box<[u32]>,
}
impl BakedCodes {
    fn digest(model:&Model)->[u8;32]{
        let mut hash=Sha256::new();
        for &value in model.q.iter().flatten().chain(model.k.iter().flatten()){
            hash.update(value.to_le_bytes());
        }
        hash.finalize().into()
    }
    fn decode(bytes:&[u8],model:&Model)->Result<Self>{
        const HEADER:usize=8+32+32;
        if bytes.len()!=HEADER+4*(1<<F) || &bytes[..8]!=LUT_MAGIC
            || bytes[8..40]!=Self::digest(model) || bytes[40..HEADER]!=Sha256::digest(&bytes[HEADER..])[..]{
            return Err("incompatible learned port table".into());
        }
        let mut words=Vec::with_capacity(1<<F);
        for word in bytes[HEADER..].chunks_exact(4){
            let code=u32::from_le_bytes(word.try_into().unwrap());
            if code>=(1<<(2*B)){return Err("invalid learned signature width".into());}
            words.push(code);
        }
        Ok(Self{words:words.into_boxed_slice()})
    }
    #[inline]
    fn pair(&self,x:u64)->(u16,u16){
        let word=self.words[(x as usize)&((1<<F)-1)];
        ((word&((1<<B)-1)) as u16,(word>>B) as u16)
    }
    #[inline]
    fn port(&self,value:&Value,views:usize)->Port{
        let seed=code_seed(value);
        let (query,key)=self.pair(mix(seed));
        let mut port=Port{query,key,certified:0,uncertain:0,extra:[[0;4];2]};
        for (i,salt) in [0x8220e116bd89aae9,0x461ac17fc5fe72c3].iter().take(views-1).enumerate(){
            let (q,k)=self.pair(mix(seed^salt));
            port.extra[i]=[q,k,0,0];
        }
        port
    }
}

pub fn bake_port_codes(weights:&[u8])->Result<Vec<u8>>{
    let model:Model=serde_json::from_slice(weights).map_err(|e|e.to_string())?;
    let mut data=Vec::with_capacity(4*(1<<F));
    for x in 0..(1<<F){
        let p=model_port(x,&model,0);
        data.extend((u32::from(p.query)|(u32::from(p.key)<<B)).to_le_bytes());
    }
    let mut out=Vec::with_capacity(72+data.len());
    out.extend_from_slice(LUT_MAGIC);out.extend(BakedCodes::digest(&model));
    out.extend(Sha256::digest(&data));out.extend(data);
    Ok(out)
}

fn signature(port:Port,query:bool,views:usize)->u32{
    let mut key=u32::from(if query{port.query}else{port.key});
    for j in 1..views{
        key |= u32::from(port.extra[j-1][usize::from(!query)])<<(j*B);
    }
    key
}

pub fn use_baked_port_codes(bytes:&[u8],columns:bool,packed:bool)->Result<()>{
    STORE.with_borrow_mut(|store|{
        let state=store.as_mut().ok_or("no neural port policy")?;
        if state.mode!="learned"{return Err("this code table covers the learned threshold scores only".into());}
        if packed && (state.radius!=0 || state.accel<4 || columns){
            return Err("packed index requires a zero-radius stack and no auxiliary column cache".into());
        }
        state.packed_lookup=packed;
        state.column_codes=columns;
        state.baked_codes=Some(BakedCodes::decode(bytes,&state.model)?);
        Ok(())
    })
}
