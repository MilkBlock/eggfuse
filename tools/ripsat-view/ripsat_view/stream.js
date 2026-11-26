(() => {
"use strict";
const by = id => document.getElementById("ts-" + id);
const make = (tag, text, cls) => {
  const n = document.createElement(tag);
  n.textContent = text;
  if (cls) n.className = cls;
  return n;
};
const names = ["已接受","重复","规则未触发","父引用数量错误","输出未知","端口已退役","端口已隐藏","类型错误","版本错误","绑定错误","水位拒绝","原语未绑定","Guard 失败","输入未绑定","计算完成","依赖错误","非法计算","等待端口"];
const status = code => names[code] ?? ("未知回执 " + code);
const groups = {network:"网络", teacher:"Teacher", random:"随机策略", audit:"离线审计"};
let data, runs, requests, publications, consumers, finalGains, ri=0, page=0, picked=null, visible=[], ticket=0;
const size=14, fmt=n=>n.toLocaleString("zh-CN");
function lossless(text) {
  // Keep i64 IDs and u64 field hashes exact on browsers with IEEE-754 numbers.
  const lex=/"(?:\\.|[^"\\])*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
  return JSON.parse(text.replace(lex, s => s[0]!=='"' && /^-?\d+$/.test(s) && !Number.isSafeInteger(Number(s)) ? JSON.stringify(s) : s));
}
function push(map,key,item){if(!map.has(key))map.set(key,[]);map.get(key).push(item)}
function requireThat(ok, what) {if(!ok) throw Error(what)}
function index(x) {
  requireThat(Array.isArray(x.events) && x.events.length,"需要含 events 的非空经验分片。");
  const ids=new Map(), pubs=new Map(), uses=new Map(), runIDs=new Set();
  const entries=x.events.map((e,i)=>{
    const f=e.frame, loc="第 "+(i+1)+" 条 Run 记录";
    requireThat(f && Number.isInteger(f.run) && !runIDs.has(f.run),loc+" 的 Run 编号无效或重复。");
    runIDs.add(f.run);
    for(const key of ["generated","response","signed_gain","assisted","assisted_response","omitted"])
      requireThat(Array.isArray(e[key]),loc+" 缺少 "+key);
    requireThat(e.generated.length===e.response.length && e.generated.length===e.signed_gain.length && e.assisted.length===e.assisted_response.length,loc+" 的请求与回执未对齐。");
    requireThat(Number.isInteger(e.random_count) && e.random_count>=0 && e.random_count<=e.assisted.length && typeof e.stable==="boolean",loc+" 的辅助来源或审计标记不完整。");
    requireThat(Array.isArray(f.updates)&&Array.isArray(f.retired),loc+" 缺少发布记录。");
    requireThat(e.stable || e.omitted.length===0,loc+" 的未确认分叉含有遗漏标签。");
    const rows=[];
    function add(c,resp,gain,source){
      requireThat(Array.isArray(c)&&c.length===3&&Number.isInteger(c[0])&&typeof c[1]==="boolean"&&Array.isArray(c[2])&&c[2].every(p=>Array.isArray(p)&&p.length===3),loc+" 的 Cell Token 无效。");
      if(source!=="audit") requireThat(Array.isArray(resp)&&resp.length===4&&resp[0]!=null&&Number.isInteger(resp[1])&&!ids.has(String(resp[0])),loc+" 的请求 ID 或回执无效。");
      if(gain!==null) requireThat(Number.isSafeInteger(gain)&&gain>=0,loc+" 的贡献数无效。");
      const row={c,resp,gain,source,i,id:resp?String(resp[0]):null};
      rows.push(row);
      if(resp){
        ids.set(row.id,row);
        for(const [owner,op,v] of c[2]) push(uses,[String(owner),String(op),String(v)].join("/"),row);
      }
    }
    e.generated.forEach((c,j)=>add(c,e.response[j],e.signed_gain[j],"network"));
    e.assisted.forEach((c,j)=>add(c,e.assisted_response[j],null,j<e.random_count?"random":"teacher"));
    e.omitted.forEach(([c,g])=>add(c,null,g,"audit"));
    for(const [addr,r] of f.updates) push(pubs,String(addr.token),{i,op:addr.op,v:r.version,table:r.table,forwarded:r.forwarded});
    for(const addr of f.retired) push(pubs,String(addr.token),{i,op:addr.op,retired:true});
    return {e,f,rows};
  });
  const final = Array.isArray(x.origins) ? new Map(x.origins.map(([id,gain])=>[String(id),gain])) : null;
  return {entries,ids,pubs,uses,final};
}
function install(x,name) {
  const z=index(x);
  data=x; runs=z.entries; requests=z.ids; publications=z.pubs; consumers=z.uses; finalGains=z.final;
  const branch=["Teacher 辅助采集","随机与 Teacher 混合采集","自主执行采集"][x.branch];
  by("source").textContent=[name,branch,runs.length+" 个 Run"].filter(Boolean).join(" · ");
  by("error").textContent="";by("content").hidden=false;by("empty").hidden=true;
  by("metrics").replaceChildren();
  const own=runs.flatMap(r=>r.rows.filter(x=>x.source==="network"));
  const total=(items,fn)=>items.reduce((v,r)=>v+fn(r),0);
  for(const [label,n] of [["网络签发",own.length],["原生接受 · 网络",total(own,r=>Number(r.resp[1]===0))],["当轮有效操作 · 网络",total(own,r=>r.gain)],["实际辅助签发",requests.size-own.length]]){
    const card=make("div","","card");card.append(make("small",label),make("b",fmt(n)));by("metrics").append(card);
  }
  by("runs").replaceChildren();
  runs.forEach((r,i)=>{const b=make("button","Run "+r.f.run);b.onclick=()=>chooseRun(i);by("runs").append(b)});
  chooseRun(0);
}
function chooseRun(i) {
  ri=i;page=0;picked=null;by("find").value="";
  [...by("runs").children].forEach((b,j)=>b.setAttribute("aria-pressed",String(i===j)));
  const {e,f}=runs[i];by("runline").textContent="发布版本 epoch "+f.epoch+" · 本帧 "+fmt(f.updates.length)+" 项端口更新，"+fmt(f.retired.length)+" 项退役 · "+(e.stable?"遗漏分叉保留原贡献归属":"分叉改变了贡献归属，遗漏未知");
  const details=by("frame").parentElement;
  by("frame").replaceChildren();
  const showFrame=()=>{if(details.open && !by("frame").childElementCount)by("frame").append(make("pre",JSON.stringify({accepted:f.accepted,updates:f.updates,retired:f.retired},null,2)))};
  details.ontoggle=showFrame;showFrame();
  changeSource();
}
function changeSource() {
  const source=by("origin").value;
  const codes=[...new Set(runs[ri].rows.filter(r=>r.source===source&&r.resp).map(r=>r.resp[1]))].sort((a,b)=>a-b);
  by("status").replaceChildren(new Option("全部回执",""),...codes.map(c=>new Option(status(c),String(c))));
  by("status").disabled=source==="audit";page=0;picked=null;filter();
}
function filter() {
  const q=by("find").value.trim().toLowerCase(), code=by("status").value;
  visible=runs[ri].rows.filter(r=>r.source===by("origin").value && (!code||r.resp?.[1]===Number(code)) && (!q||("#"+r.id)===q||("r"+r.c[0])===q||r.id===q));
  page=Math.max(0,Math.min(page,Math.ceil(visible.length/size)-1));
  if(!visible.slice(page*size,(page+1)*size).includes(picked))picked=visible[page*size]??null;
  draw();
}
function jump(row){
  by("origin").value=row.source;chooseRun(row.i);
  page=Math.floor(visible.indexOf(row)/size);picked=row;draw();
}
function link(txt,fn){const b=make("button",txt,"link");b.onclick=fn;return b}
window.tsHasRule=(sha,rid)=>data?.program===sha && runs.some(run=>run.rows.some(r=>r.resp && r.c[0]===rid && !r.c[1]));
window.tsGoRule=rid=>{
  const match=runs[ri].rows.find(r=>r.resp && r.c[0]===rid && !r.c[1]) ||
    runs.flatMap(run=>run.rows).find(r=>r.resp && r.c[0]===rid && !r.c[1]);
  if(match){jump(match);by("find").value="R"+rid;page=0;filter()}
};
function draw(){
  const list=by("list");list.replaceChildren();
  for(const r of visible.slice(page*size,(page+1)*size)){
    const b=make("button","");b.setAttribute("aria-pressed",String(r===picked));
    b.append(make("span",r.id?"#"+r.id:"分叉见证"),make("span","规则 R"+r.c[0]),
      make("span",r.resp?status(r.resp[1]):"已核验遗漏","tag "+(!r.resp?"wait":r.resp[1]===0?"good":"bad")));
    b.onclick=()=>{picked=r;draw()};list.append(b);
  }
  if(!visible.length)list.append(make("p","当前筛选没有记录。","empty"));
  by("prev").disabled=page===0;by("next").disabled=(page+1)*size>=visible.length;
  by("count").textContent=visible.length?((page*size+1)+"–"+Math.min((page+1)*size,visible.length)+" / "+fmt(visible.length)):"0 条";
  const panel=by("detail");panel.replaceChildren();
  if(!picked){panel.append(make("h2","请求详情"),make("p","选择一条记录查看执行经过。","dim"));return}
  const r=picked, f=runs[ri].f;
  panel.append(make("h2",r.id?"请求 #"+r.id:"离线遗漏见证"),make("p",groups[r.source]+" · "+(r.c[1]?"Higher":"Primitive")+" · 规则 R"+r.c[0],"dim"));
  if(window.tsStructureAvailable?.(data.program,r.c[0],r.c[1]))panel.append(link("查看 R"+r.c[0]+" 的 Cell 结构 →",()=>window.tsOpenStructure(r.c[0])));
  const life=make("ol","","life");
  function line(head,body){const l=make("li","");l.append(make("b",head),make("span",body));life.append(l)}
  if(r.resp){
    line("生成与签发","Run "+f.run+"，epoch "+f.epoch+"。"+(r.source==="network"?"本页各请求基于同一次生成前状态。":"此请求由训练采集的辅助策略签发。"));
    line("CPU 回执 · "+status(r.resp[1]),r.gain===null?"辅助签发单独归账。":"原生账本归给这次请求 "+r.gain+" 项当轮有效操作。");
    if(finalGains)line("终图贡献归属","原生终图账本归给这次请求 "+(finalGains.get(r.id)??0)+" 项有效操作。");
    const ps=publications.get(r.id)||[];
    line("后续发布",ps.length?"分片中有 "+ps.length+" 条直接以此请求为 owner 的更新或退役记录。":"分片中未见以此请求为 owner 的端口更新。");
    panel.append(life);
    for(const p of ps){
      const h=make("p","Run "+runs[p.i].f.run+" · op"+p.op+(p.retired?" 已退役":" · v"+p.v+" · 表 "+p.table+(p.forwarded?" · 已转发":"")));
      if(!p.retired){
        const children=[...new Set(consumers.get([r.id,p.op,p.v].join("/"))||[])];
        for(const c of children.filter(c=>c.i>=p.i))h.append(" ",link("消费者 #"+c.id,()=>jump(c)));
      }
      panel.append(h);
    }
  }else{
    panel.append(make("p","同一入口状态的离线原生分叉为这个绑定确认了 "+r.gain+" 项新增操作。它没有网络请求 ID。"));
  }
  panel.append(make("h3","父端口引用"));
  if(!r.c[2].length)panel.append(make("p","零父输入。"));
  else {const ul=make("ul","");r.c[2].forEach(([owner,op,v],j)=>{const li=make("li","输入 "+j+" · ");const parent=requests.get(String(owner));li.append(parent?link("请求 #"+owner,()=>jump(parent)):make("span","owner "+owner));li.append(" · op"+op+" · v"+v);ul.append(li)});panel.append(ul)}
  const raw=make("details","");raw.append(make("summary","原始 Token 与回执"),make("pre",JSON.stringify({token:r.c,response:r.resp,signed_gain:r.gain},null,2)));panel.append(raw);
}
by("origin").onchange=changeSource;
by("status").onchange=by("find").oninput=()=>{page=0;picked=null;filter()};
by("prev").onclick=()=>{page--;filter()};by("next").onclick=()=>{page++;filter()};
by("help").onclick=()=>{by("faq").open=true;by("faq").scrollIntoView({block:"start"});by("faq").querySelector("summary").focus()};
by("file").onchange=async e=>{
  const f=e.target.files[0];if(!f)return;const mine=++ticket;
  try {
    const magic=new Uint8Array(await f.slice(0,2).arrayBuffer());
    const packed=magic[0]===31&&magic[1]===139;
    if(packed && !window.DecompressionStream)throw Error("当前浏览器不能解压 gzip，请先解压为 JSON。");
    const text=packed?await new Response(f.stream().pipeThrough(new DecompressionStream("gzip"))).text():await f.text();
    if(mine===ticket)install(lossless(text),f.name);
  }catch(err){if(mine===ticket)by("error").textContent="无法打开轨迹："+err.message}
  e.target.value="";
};
const initial=document.getElementById("ts-data");
if(initial?.textContent.trim()){
  try{const {trace,name}=lossless(initial.textContent);if(trace)install(trace,name)}catch(err){by("error").textContent="轨迹读取失败："+err.message}
}
})();
