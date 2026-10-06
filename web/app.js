const API_BASE="/api";
const state={events:[],filter:"ALL"};
const $=s=>document.querySelector(s);
const esc=v=>String(v==null?"—":v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
const pick=(o,...k)=>{for(const x of k)if(o&&o[x]!=null)return o[x]};
const dir=s=>String(pick(s,"direction","side","signal")||"").toUpperCase();
const hor=s=>String(pick(s,"horizon","mode","profile")||"—").toUpperCase();
const life=s=>String(pick(s,"lifecycle","status")||"").toUpperCase();
const tm=ms=>ms?new Date(Number(ms)).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}):"—";
function scans(){return state.events.filter(e=>e.event_type==="scan").sort((a,b)=>Number(b.timestamp_ms||0)-Number(a.timestamp_ms||0))}
function latest(rows){const m=new Map();const head=rows[0]?.payload||{};const rotation=Number(head.rotation_id||0);const position=Number(head.queue_position||0);for(const e of rows)for(const x of e.payload?.markets||[]){const p=Number(e.payload?.queue_position||0);const r=Number(e.payload?.rotation_id||0);if(rotation&&(r!==rotation||p>position))continue;const o=m.get(x.asset);if(!o||Number(e.timestamp_ms)>Number(o.timestamp_ms))m.set(x.asset,{...x,timestamp_ms:e.timestamp_ms,rotation_id:r,queue_position:p})}return [...m.values()]}
function active(ms){const out=[];const seen=new Set();for(const m of ms)for(const s of m.setups||[]){const c=s.candidate||s;const d=dir(c);if((d==="LONG"||d==="SHORT")&&(life(s.lifecycle_result)==="ACTIVE"||!s.lifecycle_result)){const geometry=JSON.stringify({
scenario:c.scenario||"",
entry:c.entry_zone||[],
invalid:c.invalidation_level||null,
targets:c.target_levels||[]
});
const key=[m.asset,hor(s.mode),d,geometry].join("|");if(seen.has(key))continue;seen.add(key);out.push({asset:m.asset,mode:s.mode,setup:c,lifecycle:s.lifecycle_result,evidence_concepts:s.evidence_concepts||[],decision_action:s.decision_action||""})}}return out}
function conceptSet(s,x){return new Set([...(s.supporting_concepts||[]),...(s.zone_concepts||[]),...(x?.evidence_concepts||[])])}
function evidence(s,x){const c=conceptSet(s,x);const rows=[
["Market Structure",c.has("market_structure.bos")||c.has("market_structure.choch"),c.has("market_structure.bos")?"BOS confirmed":c.has("market_structure.choch")?"CHoCH observed":"Not confirmed"],
["Liquidity",c.has("liquidity.sweep"),c.has("liquidity.sweep")?"Sweep observed":"No confirmed sweep"],
["BOS",c.has("market_structure.bos"),c.has("market_structure.bos")?"Confirmed":"Not confirmed"],
["CHoCH / MSS",c.has("market_structure.choch")||c.has("market_structure.mss"),c.has("market_structure.mss")?"MSS confirmed":c.has("market_structure.choch")?"CHoCH confirmed":"Not confirmed"],
["Order Block",c.has("order_block.bullish")||c.has("order_block.bearish"),c.has("order_block.bullish")?"Bullish OB":c.has("order_block.bearish")?"Bearish OB":"Not present"],
["FVG",c.has("imbalance.fvg"),c.has("imbalance.fvg")?"Active evidence":"Not present"],
["Zone Reaction",c.has("price_action.rejection"),c.has("price_action.rejection")?"Confirmed":"Not confirmed"],
["Volume",c.has("volume.evidence")||c.has("volume.confirmation"),c.has("volume.evidence")||c.has("volume.confirmation")?"Confirming evidence":"No confirming evidence"]];
return rows.map(r=>'<div class="evidence-row"><span>'+esc(r[0])+'</span><b class="'+(r[1]?"yes":"no")+'">'+(r[1]?"✓":"—")+'</b><small>'+esc(r[2])+'</small></div>').join("")}
function scenarioText(s){
 const map={
  continuation:"Continuation: higher-timeframe structure is preserved; BOS and displacement must deliver in the active direction, then price must react from a valid OB/FVG zone.",
  reversal:"Reversal: prior structure is being challenged; liquidity must be swept and a same-direction CHoCH or MSS must confirm the transition before entry.",
  breakout_failure:"Breakout failure: price must raid liquidity, fail acceptance beyond the level, reject/reclaim it and confirm the failure direction structurally."
 };
 return map[String(s.scenario||"").toLowerCase()]||"Scenario is supported by the currently observed market evidence.";
}
function setupMap(s){
 const entry=s.entry_zone||[],targets=s.target_levels||[];
 const vals=[...entry.map(x=>Number(x.value)),...(s.invalidation_level?[Number(s.invalidation_level.value)]:[]),...targets.map(x=>Number(x.value))].filter(Number.isFinite);
 if(!vals.length)return '<div class="setup-map empty-map">NO PRICE GEOMETRY</div>';
 const min=Math.min(...vals),max=Math.max(...vals),span=Math.max(max-min,Math.abs(max)*0.0001);
 const y=v=>Math.round(92-((Number(v)-min)/span)*72);
 const line=(v,cls,label)=>'<div class="map-line '+cls+'" style="top:'+y(v)+'%"><span>'+esc(label)+'</span><b>'+esc(v)+'</b></div>';
 let html='<div class="setup-map"><div class="map-axis">';
 if(s.invalidation_level)html+=line(s.invalidation_level.value,"sl","INVALID");
 if(entry.length)html+=line(entry[0].value,"entry","ENTRY");
 if(entry.length>1)html+=line(entry[entry.length-1].value,"entry","ENTRY");
 if(targets[0])html+=line(targets[0].value,"tp","TP1");
 if(targets[1])html+=line(targets[1].value,"tp","TP2");
 html+='</div><div class="map-caption">'+esc(hor(xmode(s)))+' · '+esc(s.scenario||"setup")+'</div></div>';
 return html;
}
function xmode(s){return s.mode||""}
function chartTf(mode){
 const m=String(mode||"").toUpperCase();
 return m==="POSITION"?"4h":m==="SWING"?"1h":"5m";
}
function renderCandleChart(node,candles,s){
 if(!candles?.length){node.innerHTML='<div class="chart-empty">NO OHLCV DATA</div>';return}
 if(!window.LightweightCharts){node.innerHTML='<div class="chart-empty">CHART LIBRARY UNAVAILABLE</div>';return}
 node.innerHTML="";
 const chart=LightweightCharts.createChart(node,{width:node.clientWidth,height:360,layout:{background:{type:"solid",color:"#0b0e13"},textColor:"#7e8795"},grid:{vertLines:{color:"#171c23"},horzLines:{color:"#171c23"}},crosshair:{mode:LightweightCharts.CrosshairMode.Normal},rightPriceScale:{borderColor:"#252b34"},timeScale:{borderColor:"#252b34",timeVisible:true,secondsVisible:false},handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true},handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:true}});
 const series=chart.addCandlestickSeries({upColor:"#61df9a",downColor:"#ff687b",borderUpColor:"#61df9a",borderDownColor:"#ff687b",wickUpColor:"#61df9a",wickDownColor:"#ff687b"});
 const data=candles.map(k=>({time:Math.floor(Number(k.timestamp)/1000),open:Number(k.open),high:Number(k.high),low:Number(k.low),close:Number(k.close)})).filter(k=>Number.isFinite(k.time)&&Number.isFinite(k.open)&&Number.isFinite(k.high)&&Number.isFinite(k.low)&&Number.isFinite(k.close));
 series.setData(data);
 const overlay=document.createElement("canvas");overlay.className="chart-overlay";node.appendChild(overlay);
 const ctx=overlay.getContext("2d"),dpr=window.devicePixelRatio||1;
 const levels=[],entry=s.entry_zone||[],targets=s.target_levels||[];
 if(entry[0])levels.push({price:Number(entry[0].value),label:"ENTRY",cls:"entry"});
 if(entry[1])levels.push({price:Number(entry[1].value),label:"ENTRY",cls:"entry"});
 if(s.invalidation_level)levels.push({price:Number(s.invalidation_level.value),label:"SL",cls:"sl"});
 if(targets[0])levels.push({price:Number(targets[0].value),label:"TP1",cls:"tp"});
 if(targets[1])levels.push({price:Number(targets[1].value),label:"TP2",cls:"tp"});
 function draw(){
  const w=node.clientWidth,h=node.clientHeight;ctx.clearRect(0,0,w,h);
  for(const l of levels){if(!Number.isFinite(l.price))continue;const y=series.priceToCoordinate(l.price);if(y==null||y<0||y>h)continue;ctx.beginPath();ctx.moveTo(0,y+.5);ctx.lineTo(w,y+.5);ctx.lineWidth=1;ctx.setLineDash([7,5]);ctx.strokeStyle=l.cls==="entry"?"#d7ff58":l.cls==="sl"?"#ff687b":"#61df9a";ctx.stroke();ctx.setLineDash([]);const text=l.label+"  "+l.price;ctx.font="700 10px system-ui,-apple-system,Segoe UI,sans-serif";const tw=ctx.measureText(text).width;ctx.fillStyle=l.cls==="entry"?"#d7ff58":l.cls==="sl"?"#ff687b":"#61df9a";ctx.fillText(text,Math.max(6,w-tw-10),Math.max(12,y-5))}
 }
 function resize(){const w=Math.max(1,node.clientWidth),h=Math.max(1,node.clientHeight);chart.resize(w,h);overlay.width=Math.floor(w*dpr);overlay.height=Math.floor(h*dpr);overlay.style.width=w+"px";overlay.style.height=h+"px";ctx.setTransform(dpr,0,0,dpr,0,0);draw()}
 chart.timeScale().fitContent();chart.timeScale().subscribeVisibleLogicalRangeChange(draw);if(chart.timeScale().subscribeVisibleTimeRangeChange)chart.timeScale().subscribeVisibleTimeRangeChange(draw);
 const ro=new ResizeObserver(resize);ro.observe(node);resize();node._aicfaChartCleanup=()=>{ro.disconnect();chart.remove()};
}
async function hydrateCharts(){
 const nodes=[...document.querySelectorAll(".market-chart[data-symbol]")];
 await Promise.all(nodes.map(async node=>{try{const q=new URLSearchParams({symbol:node.dataset.symbol,timeframe:node.dataset.timeframe||"5m",limit:"160"});const response=await fetch(API_BASE+"/chart?"+q.toString()+"&t="+Date.now(),{cache:"no-store"});const data=response.ok?await response.json():null;renderCandleChart(node,data?.candles||[],JSON.parse(node.dataset.setup||"{}"))}catch(_){node.innerHTML='<div class="chart-empty">CHART UNAVAILABLE</div>'}}))
}

function setupCard(x){
 const s=x.setup||{},entry=s.entry_zone||[],targets=s.target_levels||[];
 const ev=entry.length?entry.map(v=>v.value).join(" — "):"—";
 const sl=s.invalidation_level?.value??"—";
 const tp=targets.length?targets.map(v=>v.value).join(" — "):"—";
 const why=(s.rationale||[]).join(" ");
 const hierarchy=(s.rationale||[]).filter(v=>v.startsWith("MTF hierarchy:")).join(" · ");
 return '<article class="setup '+dir(s).toLowerCase()+'"><div class="setup-top"><div><b>'+esc(x.asset)+'</b><span class="muted">'+esc(hor(x.mode))+' · '+esc(s.scenario||"SETUP")+'</span></div><strong>'+esc(dir(s))+'</strong></div><div class="scenario-desc">'+esc(scenarioText(s))+'</div><div class="market-chart" data-symbol="'+esc(x.asset||"")+'" data-timeframe="'+chartTf(x.mode)+'" data-setup="'+esc(JSON.stringify({entry_zone:entry,invalidation_level:s.invalidation_level,target_levels:targets}))+'"></div>'+setupMap({...s,mode:x.mode})+'<div class="analysis"><div class="analysis-title">EVIDENCE</div>'+evidence(s,x)+'</div><div class="chart-meta"><span>'+esc(hor(x.mode))+'</span><span>'+esc(ev?"ENTRY "+ev:"ENTRY —")+'</span><span>'+esc(sl?"SL "+sl:"SL —")+'</span><span>'+esc(tp?"TP "+tp:"TP —")+'</span></div><div class="why"><span>WHY '+esc(dir(s))+'</span><p>'+esc(why||"Current structural evidence supports this setup.")+'</p><small>'+esc(hierarchy)+'</small></div></article>'
}
function waitCards(ms){const out=[];for(const m of ms)for(const h of m.horizons||[]){const action=String(h.decision_action||h.decision||"").toUpperCase();if(action==="LONG"||action==="SHORT"||action==="READY")continue;const c=new Set(h.supported_concepts||[]);const checks=[["Liquidity",c.has("liquidity.sweep")],["Market Structure",c.has("market_structure.bos")||c.has("market_structure.choch")],["OB",c.has("order_block.bullish")||c.has("order_block.bearish")],["FVG",c.has("imbalance.fvg")],["Zone Reaction",c.has("price_action.rejection")],["Volume",c.has("volume.evidence")||c.has("volume.confirmation")]];out.push({asset:m.asset,mode:h.mode,action:action||"WAIT",checks:checks,why:(h.setup_reasons||h.decision_reasons||["structural setup is incomplete"])[0]})}return out}
function render(rows){const e=rows[0],p=e?.payload||{},ms=latest(rows),as=active(ms),u=Number(p.universe_size||0),pos=Number(p.queue_position||0),pct=u?Math.min(100,pos/u*100):0;$("#universe").textContent=u||"—";$("#scanned").textContent=u?pos+"/"+u:"—";$("#rotation").textContent=p.rotation_id?"#"+p.rotation_id:"—";$("#currentMarket").textContent=p.markets?.[0]?.asset||"—";const m=p.markets?.[0];$("#currentStatus").textContent=String(m?.diagnostics?.status||"—").toUpperCase()+" · "+(m?.setups||[]).length+" SETUPS";$("#lastScan").textContent=p.scan_number?"#"+p.scan_number:"—";$("#progress").style.width=pct+"%";$("#rotationMeta").textContent=u?pos+" of "+u+" markets · "+Math.round(pct)+"%":"waiting";$("#active").textContent=as.length;const filtered=as.filter(s=>state.filter==="ALL"||hor(s.mode)===state.filter);$("#setups").innerHTML=filtered.length?filtered.map(setupCard).join(""):'<div class="empty">NO ACTIVE SETUPS</div>';if(filtered.length)hydrateCharts();const waits=waitCards(ms).filter(s=>state.filter==="ALL"||String(s.mode).toUpperCase()===state.filter);$("#waits").innerHTML=waits.length?waits.slice(0,6).map(w=>'<article class="wait"><div><b>'+esc(w.asset)+'</b><span>'+esc(w.mode)+'</span></div><strong>'+esc(w.action)+'</strong><div class="checks">'+w.checks.map(c=>'<span class="'+(c[1]?"ok":"missing")+'">'+(c[1]?"✓":"—")+' '+esc(c[0])+'</span>').join("")+'</div><p>'+esc(w.why)+'</p></article>').join(""):'<div class="empty">NO WAIT ANALYSIS</div>';const recent=rows.slice(0,8);$("#count").textContent=recent.length+" SCANS";$("#activity").innerHTML=recent.map(e=>{const p=e.payload||{},m=p.markets?.[0],d=m?.diagnostics||{};return '<div class="row"><time>'+tm(e.timestamp_ms)+'</time><b>'+esc(m?.asset)+'</b><span class="'+String(d.status||"").toLowerCase()+'">'+esc(String(d.status||"—").toUpperCase())+'</span><span>'+(m?.setups||[]).length+' setups</span><small>rotation '+esc(p.rotation_id||"—")+' · '+esc(p.queue_position||"—")+'/'+esc(p.universe_size||"—")+'</small></div>'}).join("")}
let refreshInFlight=false;
async function refresh(){
 if(refreshInFlight)return;
 refreshInFlight=true;
 try{const[h,d]=await Promise.all([fetch(API_BASE+"/health?t="+Date.now(),{cache:"no-store"}).then(x=>x.json()),fetch(API_BASE+"/journal/scans?limit=500&t="+Date.now(),{cache:"no-store"}).then(x=>x.json())]);state.events=d.events||[];render(scans());$("#statusText").textContent=h.ok?"LIVE":"DEGRADED";$("#updated").textContent=tm(Date.now())}catch(e){$("#statusText").textContent="OFFLINE";$("#updated").textContent="—"}finally{refreshInFlight=false}}
$("#filters").addEventListener("click",e=>{const f=e.target.dataset.filter;if(!f)return;document.querySelectorAll("#filters button").forEach(b=>b.classList.remove("active"));e.target.classList.add("active");state.filter=f;render(scans())});refresh();setInterval(refresh,3000);