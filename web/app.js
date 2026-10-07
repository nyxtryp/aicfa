const API_BASE="/api";
const state={events:[],registry:[],markets:[],prices:{},filter:"ALL"};
const ui={history:[],selected:null,centerKey:null,centerEmpty:false,centerEmptyMarket:"",marketIndex:null,marketBusy:false,lastSelectedSignature:""};
const $=s=>document.querySelector(s);
const esc=v=>String(v==null?"—":v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
const pick=(o,...k)=>{for(const x of k)if(o&&o[x]!=null)return o[x]};
const dir=s=>String(pick(s,"direction","side","signal")||"").toUpperCase();
const hor=s=>String(pick(s,"horizon","mode","profile")||"—").toUpperCase();
const life=s=>String(pick(s,"lifecycle","status")||"").toUpperCase();
const tm=ms=>ms?new Date(Number(ms)).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}):"—";
function scans(){return state.events.filter(e=>e.event_type==="scan").sort((a,b)=>Number(b.timestamp_ms||0)-Number(a.timestamp_ms||0))}
function latest(rows){
 const m=new Map(),head=rows[0]?.payload||{},rotation=Number(head.rotation_id||0),position=Number(head.queue_position||0);
 for(const e of rows)for(const x of e.payload?.markets||[]){
  const p=Number(e.payload?.queue_position||0),r=Number(e.payload?.rotation_id||0);
  if(rotation&&(r!==rotation||p>position))continue;
  const o=m.get(x.asset);
  if(!o||Number(e.timestamp_ms)>Number(o.timestamp_ms))m.set(x.asset,{...x,timestamp_ms:e.timestamp_ms,rotation_id:r,queue_position:p});
 }
 return [...m.values()];
}
function setupKey(x){return String(x.key||[x.asset,hor(x.mode),(x.setup?.scenario||""),dir(x.setup||""),x.setupTimeframe||""].join("|"))}
function active(ms){
 const out=[],seen=new Set();
 for(const m of ms)for(const s of m.setups||[]){
  const c=s.candidate||s,d=dir(c);
  if((d==="LONG"||d==="SHORT")&&(life(s.lifecycle_result)==="ACTIVE"||!s.lifecycle_result)){
   const x={asset:m.asset,mode:s.mode,setup:c,lifecycle:s.lifecycle_result,evidence_concepts:s.evidence_concepts||[],decision_action:s.decision_action||""},key=setupKey(x);
   if(!seen.has(key)){seen.add(key);out.push({...x,key})}
  }
 }
 return out;
}
function registryItems(records){
 const out=[];
 for(const r of records||[]){
  const status=String(r.status||"").toUpperCase();
  if(status!=="ACTIVE"&&status!=="STALE")continue;
  const wrapper=r.setup||{},base=wrapper.candidate||wrapper,candidate={...base,chart:wrapper.chart||base.chart};
  out.push({asset:r.asset,mode:r.mode,setup:candidate,lifecycle:r.lifecycle_status||status.toLowerCase(),status,key:r.setup_id,seenAt:Number(r.last_seen_at_ms||r.created_at_ms||0),lastConfirmedAt:Number(r.last_confirmed_at_ms||0),setupTimeframe:r.structural_timeframe||"",evidence_concepts:wrapper.evidence_concepts||[],decision_action:wrapper.decision_action||""});
 }
 return out.sort((a,b)=>(a.status==="ACTIVE"?0:1)-(b.status==="ACTIVE"?0:1)||Number(b.lastConfirmedAt||b.seenAt)-Number(a.lastConfirmedAt||a.seenAt));
}
function syncRegistry(records){
 const items=registryItems(records),previous=ui.selected,oldKeys=new Set(ui.history.map(x=>x.key));
 const newlyAdded=items.find(x=>!oldKeys.has(x.key));
 ui.history=items;
 if(newlyAdded){
  ui.selected=newlyAdded.key;
  ui.centerKey=newlyAdded.key;
  ui.centerEmpty=false;
  ui.centerEmptyMarket="";
 }else if(previous&&items.some(x=>x.key===previous)){
  ui.selected=previous;
 }else if(!ui.centerEmpty&&ui.centerKey&&items.some(x=>x.key===ui.centerKey)){
  ui.selected=ui.centerKey;
 }else if(!ui.centerEmpty&&ui.centerKey===null&&items.length){
  ui.selected=items[0].key;
  ui.centerKey=items[0].key;
 }
}function conceptSet(s,x){return new Set([...(s.supporting_concepts||[]),...(s.zone_concepts||[]),...(x?.evidence_concepts||[])])}
function evidence(s,x){
 const c=conceptSet(s,x),rows=[
  ["Market Structure",c.has("market_structure.bos")||c.has("market_structure.choch"),c.has("market_structure.bos")?"BOS confirmed":c.has("market_structure.choch")?"CHoCH observed":"Not confirmed"],
  ["Liquidity",c.has("liquidity.sweep"),c.has("liquidity.sweep")?"Sweep observed":"No confirmed sweep"],
  ["BOS",c.has("market_structure.bos"),c.has("market_structure.bos")?"Confirmed":"Not confirmed"],
  ["CHoCH / MSS",c.has("market_structure.choch")||c.has("market_structure.mss"),c.has("market_structure.mss")?"MSS confirmed":c.has("market_structure.choch")?"CHoCH confirmed":"Not confirmed"],
  ["Order Block",c.has("order_block.bullish")||c.has("order_block.bearish"),c.has("order_block.bullish")?"Bullish OB":c.has("order_block.bearish")?"Bearish OB":"Not present"],
  ["FVG",c.has("imbalance.fvg"),c.has("imbalance.fvg")?"Active evidence":"Not present"],
  ["Zone Reaction",c.has("price_action.rejection"),c.has("price_action.rejection")?"Confirmed":"Not confirmed"],
  ["Volume",c.has("volume.evidence")||c.has("volume.confirmation"),c.has("volume.evidence")||c.has("volume.confirmation")?"Confirming evidence":"No confirming evidence"]
 ];
 return rows.map(r=>'<div class="evidence-row"><span>'+esc(r[0])+'</span><b class="'+(r[1]?"yes":"no")+'">'+(r[1]?"✓":"—")+'</b><small>'+esc(r[2])+'</small></div>').join("");
}
function scenarioText(s){
 const map={
  continuation:"Continuation: higher-timeframe structure is preserved; BOS and displacement must deliver in the active direction, then price must react from a valid OB/FVG zone.",
  reversal:"Reversal: prior structure is being challenged; liquidity must be swept and a same-direction CHoCH or MSS must confirm the transition before entry.",
  breakout_failure:"Breakout failure: price must raid liquidity, fail acceptance beyond the level, reject/reclaim it and confirm the failure direction structurally."
 };
 return map[String(s.scenario||"").toLowerCase()]||"Scenario is supported by the currently observed market evidence.";
}
function chartTf(_mode,setup){const entry=Array.isArray(setup?.entry_zone)?setup.entry_zone[0]:null;return String(entry?.timeframe||setup?.timeframe||"").toLowerCase()}
function renderCandleChart(node,candles,s){
 if(!candles?.length){node.innerHTML='<div class="chart-empty">NO OHLCV DATA</div>';return}
 if(!window.LightweightCharts){node.innerHTML='<div class="chart-empty">CHART LIBRARY UNAVAILABLE</div>';return}
 node.innerHTML="";
 const chart=LightweightCharts.createChart(node,{width:node.clientWidth,height:390,layout:{background:{type:"solid",color:"#090c10"},textColor:"#7e8795"},grid:{vertLines:{color:"#171c23"},horzLines:{color:"#171c23"}},crosshair:{mode:LightweightCharts.CrosshairMode.Normal},rightPriceScale:{borderColor:"#252b34"},timeScale:{borderColor:"#252b34",timeVisible:true,secondsVisible:false},handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true},handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:true}});
 const series=chart.addCandlestickSeries({upColor:"#61df9a",downColor:"#ff687b",borderUpColor:"#61df9a",borderDownColor:"#ff687b",wickUpColor:"#61df9a",wickDownColor:"#ff687b"});
 const data=candles.map(k=>({time:Math.floor(Number(k.timestamp)/1000),open:Number(k.open),high:Number(k.high),low:Number(k.low),close:Number(k.close)})).filter(k=>Number.isFinite(k.time)&&Number.isFinite(k.open)&&Number.isFinite(k.high)&&Number.isFinite(k.low)&&Number.isFinite(k.close));
 series.setData(data);
 const overlay=document.createElement("canvas");overlay.className="chart-overlay";node.appendChild(overlay);
 const ctx=overlay.getContext("2d"),dpr=window.devicePixelRatio||1;
 const price=v=>Number(v?.price??v?.value??v);
 const time=v=>Number(v?.timestamp??v?.time??v);
 const entry=s.entry||s.entry_zone||[],targets=s.take_profits||s.target_levels||[];
 const chartData=s.chart||{},zones=s.zones||{},chartZones=chartData.zones||[],obs=[...chartZones.filter(z=>String(z.type).toLowerCase()==="ob"),...(zones.order_blocks||s.order_blocks||[]),...(zones.ob||[])],fvgs=[...chartZones.filter(z=>String(z.type).toLowerCase()==="fvg"),...(zones.fvgs||s.fvgs||[]),...(zones.fvg||[])];
 const chartEvents=chartData.events||[],events={BOS:[...chartEvents.filter(e=>e.type==="BOS"),...(s.bos||s.BOS||[])],CHoCH:[...chartEvents.filter(e=>e.type==="CHoCH"),...(s.choch||s.CHoCH||[])],MSS:[...chartEvents.filter(e=>e.type==="MSS"),...(s.mss||s.MSS||[])]};
 function rangePrice(x){const a=price(x?.priceLow??x?.low??x?.low_price),b=price(x?.priceHigh??x?.high??x?.high_price);return [Math.min(a,b),Math.max(a,b)]}
 function xCoord(t){if(!Number.isFinite(t))return null;return chart.timeScale().timeToCoordinate(Math.floor(t>1e12?t/1000:t))}
 function drawOverlay(){
  const w=node.clientWidth,h=node.clientHeight;ctx.clearRect(0,0,w,h);
  const line=(p,label,kind,dash=[7,5])=>{if(!Number.isFinite(p))return;const y=series.priceToCoordinate(p);if(y==null)return;ctx.beginPath();ctx.moveTo(0,y+.5);ctx.lineTo(w,y+.5);ctx.setLineDash(dash);ctx.lineWidth=1;ctx.strokeStyle=kind==="sl"?"#ff687b":kind==="tp"?"#61df9a":"#d7ff58";ctx.stroke();ctx.setLineDash([]);ctx.font="700 10px system-ui,-apple-system,Segoe UI,sans-serif";ctx.fillStyle=ctx.strokeStyle;const text=label+"  "+p;ctx.fillText(text,Math.max(6,w-ctx.measureText(text).width-10),Math.max(12,y-5))};
  if(Array.isArray(entry))for(const e of entry)line(price(e),"ENTRY","entry");else if(entry)line(price(entry),"ENTRY","entry");
  if(s.stop_loss)line(price(s.stop_loss),"SL","sl",[6,5]);else if(s.invalidation_level)line(price(s.invalidation_level),"SL","sl",[6,5]);
  for(const t of Array.isArray(targets)?targets:[])line(price(t),targets.indexOf(t)===0?"TP1":"TP"+(targets.indexOf(t)+1),"tp",[7,5]);
  const rect=(z,fill,stroke)=>{const [lo,hi]=rangePrice(z);if(!Number.isFinite(lo)||!Number.isFinite(hi))return;const y1=series.priceToCoordinate(hi),y2=series.priceToCoordinate(lo);if(y1==null||y2==null)return;const ts=time(z.timeStart??z.startTime??z.time_start),te=time(z.timeEnd??z.endTime??z.time_end);let x1=xCoord(ts),x2=xCoord(te);if(x1==null)x1=0;if(x2==null)x2=w;if(x2<x1)[x1,x2]=[x2,x1];ctx.fillStyle=fill;ctx.fillRect(x1,Math.min(y1,y2),Math.max(2,x2-x1),Math.abs(y2-y1));ctx.strokeStyle=stroke;ctx.strokeRect(x1,Math.min(y1,y2),Math.max(2,x2-x1),Math.abs(y2-y1))};
  obs.forEach(z=>rect(z,"rgba(255,184,77,.12)","rgba(255,184,77,.55)"));fvgs.forEach(z=>rect(z,"rgba(174,108,255,.13)","rgba(174,108,255,.6)"));
  Object.entries(events).forEach(([name,list])=>{for(const e of list){const p=price(e);if(!Number.isFinite(p))continue;const y=series.priceToCoordinate(p);if(y==null)continue;let x1=xCoord(time(e.timeStart??e.startTime??e.time_start)),x2=xCoord(time(e.timeEnd??e.endTime??e.time_end));if(x1==null)x1=0;if(x2==null)x2=w;ctx.beginPath();ctx.moveTo(x1,y+.5);ctx.lineTo(x2,y+.5);ctx.setLineDash([5,5]);ctx.strokeStyle=name==="BOS"?"#f3c74f":name==="CHoCH"?"#67b7ff":"#ff9d66";ctx.stroke();ctx.setLineDash([]);ctx.font="700 9px system-ui,-apple-system,Segoe UI,sans-serif";ctx.fillStyle=ctx.strokeStyle;ctx.fillText(name,Math.min(w-35,Math.max(4,x1+4)),Math.max(11,y-4))}})}
 function resize(){const w=Math.max(1,node.clientWidth),h=Math.max(1,node.clientHeight);chart.resize(w,h);overlay.width=Math.floor(w*dpr);overlay.height=Math.floor(h*dpr);overlay.style.width=w+"px";overlay.style.height=h+"px";ctx.setTransform(dpr,0,0,dpr,0,0);drawOverlay()}
 chart.timeScale().fitContent();chart.timeScale().subscribeVisibleLogicalRangeChange(drawOverlay);if(chart.timeScale().subscribeVisibleTimeRangeChange)chart.timeScale().subscribeVisibleTimeRangeChange(drawOverlay);
 const ro=new ResizeObserver(resize);ro.observe(node);resize();node._aicfaChartCleanup=()=>{ro.disconnect();chart.remove()};
}
async function hydrateCharts(){
 const nodes=[...document.querySelectorAll(".market-chart[data-symbol]")];
 await Promise.all(nodes.map(async node=>{try{const q=new URLSearchParams({symbol:node.dataset.symbol,timeframe:node.dataset.timeframe,limit:"200"});const response=await fetch(API_BASE+"/chart?"+q.toString()+"&t="+Date.now(),{cache:"no-store"});const data=response.ok?await response.json():null;renderCandleChart(node,data?.candles||[],JSON.parse(node.dataset.setup||"{}"))}catch(_){node.innerHTML='<div class="chart-empty">CHART UNAVAILABLE</div>'}}));
}
function setupCard(x){
 const s=x.setup||{},entry=s.entry_zone||[],targets=s.target_levels||[],ev=entry.length?entry.map(v=>v.value).join(" — "):"—",sl=s.invalidation_level?.value??"—",tp=targets.length?targets.map(v=>v.value).join(" — "):"—";
 const why=(s.rationale||[]).filter(v=>!v.startsWith("MTF hierarchy:")),hierarchy=(s.rationale||[]).filter(v=>v.startsWith("MTF hierarchy:")).join(" · "),side=dir(s),tf=chartTf(x.mode,s);
 return '<article class="setup '+side.toLowerCase()+'">'+
 '<header class="setup-head"><div class="symbol-block"><b>'+esc(x.asset)+'</b><span>'+esc(hor(x.mode))+' / '+esc(s.scenario||"SETUP")+'</span></div><div class="signal"><i></i><strong>'+esc(side)+'</strong></div></header>'+
 '<div class="setup-grid"><section class="chart-panel"><div class="panel-kicker">MARKET STRUCTURE · '+esc(tf.toUpperCase())+'</div><div class="market-chart" data-symbol="'+esc(x.asset||"")+'" data-timeframe="'+tf+'" data-setup="'+esc(JSON.stringify({entry_zone:entry,invalidation_level:s.invalidation_level,target_levels:targets,zones:s.zones,order_blocks:s.order_blocks,fvgs:s.fvgs,bos:s.bos,choch:s.choch,mss:s.mss,chart:s.chart}))+'"></div><div class="chart-meta"><span>ENTRY <b>'+esc(ev)+'</b></span><span>SL <b>'+esc(sl)+'</b></span><span>TP <b>'+esc(tp)+'</b></span></div></section>'+
 '<aside class="setup-side"><div class="scenario"><span class="panel-kicker">SCENARIO</span><p>'+esc(scenarioText(s))+'</p></div><div class="evidence"><span class="panel-kicker">EVIDENCE</span>'+evidence(s,x)+'</div><div class="decision"><span class="panel-kicker">WHY '+esc(side)+'</span><p>'+esc(why.length?why.join(" · "):"Current structural evidence supports this setup.")+'</p><small>'+esc(hierarchy)+'</small></div></aside></div></article>';
}
function waitCards(ms){
 const out=[];
 for(const m of ms)for(const h of m.horizons||[]){
  const action=String(h.decision_action||h.decision||"").toUpperCase();if(action==="LONG"||action==="SHORT"||action==="READY")continue;
  const c=new Set(h.supported_concepts||[]),checks=[["Liquidity",c.has("liquidity.sweep")],["Market Structure",c.has("market_structure.bos")||c.has("market_structure.choch")],["OB",c.has("order_block.bullish")||c.has("order_block.bearish")],["FVG",c.has("imbalance.fvg")],["Zone Reaction",c.has("price_action.rejection")],["Volume",c.has("volume.evidence")||c.has("volume.confirmation")]];
  out.push({asset:m.asset,mode:h.mode,action:action||"WAIT",checks,why:(h.setup_reasons||h.decision_reasons||["structural setup is incomplete"])[0]});
 }
 return out;
}
function historyCard(x){
 const s=x.setup||{},side=dir(s),selected=x.key===ui.selected;
 return '<button class="history-item '+side.toLowerCase()+(selected?" selected":"")+'" data-setup-key="'+esc(x.key)+'"><span class="history-dot"></span><span class="history-main"><b>'+esc(x.asset)+'</b><small>'+esc(hor(x.mode))+' · '+esc(s.scenario||"SETUP")+'</small></span><strong>'+esc(side)+'</strong><em>'+esc(x.status||"ACTIVE")+'</em><time>'+esc(tm(x.seenAt))+'</time></button>';
}function renderHistory(){
 const visible=ui.history.filter(x=>state.filter==="ALL"||hor(x.mode)===state.filter);
 if(visible.length&&!visible.some(x=>x.key===ui.selected))ui.selected=visible[0].key;
 $("#historyCount").textContent=visible.length;
 $("#setupHistory").innerHTML=visible.length?visible.map(historyCard).join(""):'<div class="rail-empty">NO SETUPS YET</div>';
}
function renderCenter(){
 const root=$("#setups");
 if(ui.centerEmpty){
  root.dataset.signature="";
  $("#workspaceTitle").textContent=(ui.centerEmptyMarket||"MARKET")+" · NO SETUP";
  root.innerHTML='<div class="workspace-empty"><b>NO ACTIVE SETUP</b><span>This market was analyzed by the same AICFA scanner pipeline. No actionable setup was found.</span></div>';
  return;
 }
 const x=ui.history.find(h=>h.key===ui.centerKey);
 if(!x){
  root.dataset.signature="";
  $("#workspaceTitle").textContent="Waiting for setup";
  root.innerHTML='<div class="workspace-empty"><b>NO ACTIVE SETUP</b><span>The scanner is working. A new actionable setup will open here automatically.</span></div>';
  return;
 }
 const sig=x.key+JSON.stringify(x.setup);
 if(root.dataset.signature===sig)return;
 root.dataset.signature=sig;$("#workspaceTitle").textContent=x.asset+" · "+hor(x.mode);
 root.innerHTML=setupCard(x);hydrateCharts();
}
function renderRails(ms,rows){
 const waits=waitCards(ms).filter(s=>state.filter==="ALL"||String(s.mode).toUpperCase()===state.filter);
 
 $("#waits").innerHTML=waits.length?waits.map(w=>'<article class="wait"><div><b>'+esc(w.asset)+'</b><span>'+esc(w.mode)+'</span></div><strong>'+esc(w.action)+'</strong><div class="checks">'+w.checks.map(c=>'<span class="'+(c[1]?"ok":"missing")+'">'+(c[1]?"✓":"—")+" "+esc(c[0])+'</span>').join("")+'</div><p>'+esc(w.why)+'</p></article>').join(""):'<div class="rail-empty">NO WAIT ANALYSIS</div>';
 const recent=rows.slice(0,80);
 $("#activity").innerHTML=recent.map(e=>{const p=e.payload||{},m=p.markets?.[0],d=m?.diagnostics||{};return '<div class="row"><time>'+tm(e.timestamp_ms)+'</time><b>'+esc(m?.asset)+'</b><span class="'+String(d.status||"").toLowerCase()+'">'+esc(String(d.status||"—").toUpperCase())+'</span><small>'+(m?.setups||[]).length+' setups</small></div>'}).join("");
}
function render(rows,registry){
 const p=rows[0]?.payload||{},ms=latest(rows),u=Number(p.universe_size||0),pos=Number(p.queue_position||0),pct=u?Math.min(100,pos/u*100):0;
 syncRegistry(registry);
 renderMarkets();
 $("#universe").textContent=u||"—";$("#scanned").textContent=u?pos+"/"+u:"—";$("#rotation").textContent=p.rotation_id?"#"+p.rotation_id:"—";$("#currentMarket").textContent=p.markets?.[0]?.asset||"—";
 const m=p.markets?.[0];$("#currentStatus").textContent=String(m?.diagnostics?.status||"—").toUpperCase()+" · "+(m?.setups||[]).length+" SETUPS";$("#lastScan").textContent=p.scan_number?"#"+p.scan_number:"—";$("#progress").style.width=pct+"%";$("#rotationMeta").textContent=u?pos+" of "+u+" markets · "+Math.round(pct)+"%":"waiting";
 $("#active").textContent=registryItems(registry).filter(x=>x.status==="ACTIVE").length;renderRails(ms,rows);renderHistory();renderCenter();
}let refreshInFlight=false,lastEventSignature="";
async function getJson(path,fallback){
 try{
  const response=await fetch(API_BASE+path+(path.includes("?")?"&":"?")+"t="+Date.now(),{cache:"no-store"});
  const data=await response.json();
  return response.ok?data:fallback;
 }catch(_){return fallback}
}
async function refresh(){
 if(refreshInFlight)return;refreshInFlight=true;
 try{
  const [h,d,r,mk,prices]=await Promise.all([
   getJson("/health",{}),
   getJson("/journal/scans?limit=500",{events:[]}),
   getJson("/journal/registry",{setups:[]}),
   getJson("/markets",{markets:[]}),
   getJson("/market-prices",{prices:{}})
  ]);
  state.events=d.events||[];const registry=r.setups||[];state.registry=registry;state.markets=mk.markets||[];const previous=state.prices;state.prices=prices.prices||{};state.previousPrices=previous;const sig=JSON.stringify([state.events,registry,state.markets]);
  if(sig!==lastEventSignature){lastEventSignature=sig;render(scans(),registry)}else{renderMarkets()}
  $("#statusText").textContent=h.ok?"LIVE":(state.markets.length||state.events.length?"DEGRADED":"OFFLINE");$("#updated").textContent=tm(Date.now());
 }catch(e){$("#statusText").textContent="DEGRADED";$("#updated").textContent=tm(Date.now())}finally{refreshInFlight=false}
}
function formatMarketPrice(value){
 const n=Number(value);
 if(!Number.isFinite(n))return "—";
 if(n>=1000)return n.toLocaleString(undefined,{maximumFractionDigits:2});
 if(n>=1)return n.toLocaleString(undefined,{maximumFractionDigits:4});
 if(n>=0.01)return n.toLocaleString(undefined,{maximumFractionDigits:6});
 return n.toLocaleString(undefined,{maximumFractionDigits:8});
}
function renderMarkets(){
 const root=$("#marketWatch"),visible=state.markets||[];
 root.innerHTML=visible.length?visible.map(m=>{
  const key=String(m.index),price=state.prices[key],prev=state.previousPrices?.[key];
  const move=Number.isFinite(Number(price))&&Number.isFinite(Number(prev))?(Number(price)>Number(prev)?"up":Number(price)<Number(prev)?"down":"flat"):"flat";
  return '<button class="market-item '+(Number(m.index)===Number(ui.marketIndex)?"selected":"")+'" data-market-index="'+esc(m.index)+'"><span class="market-symbol">'+esc(m.asset)+'</span><span class="market-price '+move+'">'+esc(formatMarketPrice(price))+'</span><span class="market-type">'+esc(m.market_type==="futures"?"FUT":"SPOT")+'</span></button>';
 }).join(""):'<div class="rail-empty">NO MARKETS</div>';
}
async function scanMarket(index){
 const market=state.markets.find(x=>Number(x.index)===Number(index));
 if(!market)return;
 ui.marketIndex=Number(index);
 ui.marketBusy=true;
 ui.centerEmpty=false;
 ui.centerKey=null;
 ui.centerEmptyMarket=market.asset;
 $("#workspaceTitle").textContent=market.asset+" · ANALYZING";
 $("#setups").dataset.signature="";
 $("#setups").innerHTML='<div class="workspace-empty"><b>ANALYZING MARKET</b><span>Running the same AICFA scanner pipeline used by the autonomous queue.</span></div>';
 renderMarkets();
 try{
  const response=await fetch(API_BASE+"/market-scan",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({market_index:Number(index)})});
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||"scan_failed");
  const items=registryItems(data.setups||[]);
  if(items.length){
   const keys=new Set(items.map(x=>x.key));
   ui.history=[...ui.history.filter(x=>!keys.has(x.key)),...items].sort((a,b)=>(a.status==="ACTIVE"?0:1)-(b.status==="ACTIVE"?0:1)||Number(b.lastConfirmedAt||b.seenAt)-Number(a.lastConfirmedAt||a.seenAt));
   const item=items[0];
   ui.centerKey=item.key;
   ui.selected=item.key;
   ui.centerEmpty=false;
   ui.centerEmptyMarket="";
   renderHistory();
   renderCenter();
  }else{
   ui.centerKey=null;
   ui.selected=null;
   ui.centerEmpty=true;
   ui.centerEmptyMarket=market.asset;
   renderCenter();
  }
 }catch(error){
  ui.centerKey=null;
  ui.selected=null;
  ui.centerEmpty=true;
  ui.centerEmptyMarket=market.asset;
  const detail=error&&error.message?String(error.message):"unknown scanner error";
  $("#workspaceTitle").textContent=market.asset+" · SCAN ERROR";
  $("#setups").innerHTML='<div class="workspace-empty"><b>MARKET SCAN UNAVAILABLE</b><span>'+esc(detail)+'</span></div>';
 }finally{
  ui.marketBusy=false;
  renderMarkets();
 }
}
$("#filters").addEventListener("click",e=>{const f=e.target.dataset.filter;if(!f)return;document.querySelectorAll("#filters button").forEach(b=>b.classList.remove("active"));e.target.classList.add("active");state.filter=f;render(scans(),state.registry)});
$("#marketWatch").addEventListener("click",e=>{const b=e.target.closest("[data-market-index]");if(!b)return;scanMarket(Number(b.dataset.marketIndex))});
$("#setupHistory").addEventListener("click",e=>{const b=e.target.closest("[data-setup-key]");if(!b)return;ui.selected=b.dataset.setupKey;ui.centerKey=b.dataset.setupKey;ui.centerEmpty=false;ui.centerEmptyMarket="";renderHistory();renderCenter()});
$(".left-rail").addEventListener("click",e=>{const head=e.target.closest(".rail-head");if(!head)return;const panel=head.parentElement;if(!panel.matches(".market-watch,.rail-panel"))return;panel.classList.toggle("collapsed")});
refresh();setInterval(refresh,3000);