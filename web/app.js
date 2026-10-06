const API_BASE="/api";
const state={events:[],filter:"ALL"};
const $=s=>document.querySelector(s);
const esc=v=>String(v??"—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
const pick=(o,...k)=>{for(const x of k)if(o&&o[x]!=null)return o[x]};
const dir=s=>String(pick(s,"direction","side","signal")||"").toUpperCase();
const hor=s=>String(pick(s,"horizon","mode","profile")||"—").toUpperCase();
const life=s=>String(pick(s,"lifecycle","status")||"").toUpperCase();
const tm=ms=>ms?new Date(Number(ms)).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}):"—";
function scans(){return state.events.filter(e=>e.event_type==="scan").sort((a,b)=>Number(b.timestamp_ms||0)-Number(a.timestamp_ms||0))}
function latest(rows){const m=new Map();for(const e of rows)for(const x of e.payload?.markets||[]){const o=m.get(x.asset);if(!o||Number(e.timestamp_ms)>Number(o.timestamp_ms))m.set(x.asset,{...x,timestamp_ms:e.timestamp_ms})}return [...m.values()]}
function active(ms){const out=[];for(const m of ms)for(const s of m.setups||[])if((dir(s)==="LONG"||dir(s)==="SHORT")&&life(s)==="ACTIVE")out.push({asset:m.asset,direction:dir(s),horizon:hor(s),entry:pick(s,"entry","entry_price","entry_zone"),sl:pick(s,"invalidation","sl","stop_loss"),tp:pick(s,"tp","tp1","target"),rr:pick(s,"rr","risk_reward")});return out}
function render(rows){
 const e=rows[0],p=e?.payload||{},ms=latest(rows),as=active(ms),u=Number(p.universe_size||0),pos=Number(p.queue_position||0),pct=u?Math.min(100,pos/u*100):0;
 $("#universe").textContent=u||"—";$("#scanned").textContent=u?pos+"/"+u:"—";$("#rotation").textContent=p.rotation_id?"#"+p.rotation_id:"—";
 $("#currentMarket").textContent=p.markets?.[0]?.asset||"—";const m=p.markets?.[0],n=(m?.setups||[]).length;
 $("#currentStatus").textContent=String(m?.diagnostics?.status||"—").toUpperCase()+" · "+n+" FOUND";$("#lastScan").textContent=p.scan_number?"#"+p.scan_number:"—";
 $("#progress").style.width=pct+"%";$("#rotationMeta").textContent=u?pos+" of "+u+" markets · "+Math.round(pct)+"%":"waiting";$("#active").textContent=as.length;
 const filtered=as.filter(s=>state.filter==="ALL"||s.horizon===state.filter);
 $("#setups").innerHTML=filtered.length?filtered.map(s=>'<article class="setup '+s.direction.toLowerCase()+'"><div class="setup-top"><b>'+esc(s.asset)+'</b><strong>'+esc(s.direction)+'</strong></div><span class="muted">'+esc(s.horizon)+'</span><div class="levels"><div><small>ENTRY</small><b>'+esc(s.entry)+'</b></div><div><small>SL</small><b>'+esc(s.sl)+'</b></div><div><small>TP</small><b>'+esc(s.tp)+'</b></div><div><small>RR</small><b>'+esc(s.rr)+'</b></div></div></article>').join(""):'<div class="empty">NO ACTIVE SETUPS</div>';
 const recent=rows.slice(0,8);$("#count").textContent=recent.length+" SCANS";
 $("#activity").innerHTML=recent.map(e=>{const p=e.payload||{},m=p.markets?.[0],d=m?.diagnostics||{},n=(m?.setups||[]).length;return '<div class="row"><time>'+tm(e.timestamp_ms)+'</time><b>'+esc(m?.asset)+'</b><span class="'+String(d.status||"").toLowerCase()+'">'+esc(String(d.status||"—").toUpperCase())+'</span><span>'+n+' found</span><small>rotation '+esc(p.rotation_id||"—")+' · '+esc(p.queue_position||"—")+'/'+esc(p.universe_size||"—")+'</small></div>'}).join("")
}
async function refresh(){try{const[h,d]=await Promise.all([fetch(API_BASE+"/health",{cache:"no-store"}).then(x=>x.json()),fetch(API_BASE+"/journal/scans?limit=500",{cache:"no-store"}).then(x=>x.json())]);state.events=d.events||[];render(scans());$("#statusText").textContent=h.ok?"LIVE":"DEGRADED";$("#updated").textContent=tm(Date.now())}catch(e){$("#statusText").textContent="OFFLINE";$("#updated").textContent="—"}}
$("#filters").addEventListener("click",e=>{const f=e.target.dataset.filter;if(!f)return;document.querySelectorAll("#filters button").forEach(b=>b.classList.remove("active"));e.target.classList.add("active");state.filter=f;render(scans())});
refresh();setInterval(refresh,10000);