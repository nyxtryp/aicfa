const API_BASE="/api";
const state={events:[],registry:[],monitorRecords:[],markets:[],prices:{},filter:"ALL"};
const ui={history:[],manualItems:[],manualView:null,autoWatchItems:[],selected:null,centerKey:null,centerEmpty:false,centerEmptyMarket:"",marketIndex:null,marketBusy:false,lastSelectedSignature:"",monitorMode:"SCALPING",monitorView:"ACTIVE"};
const $=s=>document.querySelector(s);
const esc=v=>String(v==null?"—":v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
const pick=(o,...k)=>{for(const x of k)if(o&&o[x]!=null)return o[x]};
const dir=s=>String(pick(s,"direction","side","signal")||"").toUpperCase();
const hor=s=>String((typeof s==="string"?s:pick(s,"horizon","mode","profile"))||"—").toUpperCase();
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
function allHistory(){return [...ui.manualItems,...ui.autoWatchItems.filter(x=>!ui.manualItems.some(m=>m.key===x.key)),...ui.history.filter(x=>!ui.manualItems.some(m=>m.key===x.key)&&!ui.autoWatchItems.some(w=>w.key===x.key))]}
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
function automaticWatchItems(markets){
 const latestByKey=new Map();
 for(const m of markets||[])for(const item of m.setups||[]){
  const c=item.candidate||item,d=dir(c),mode=hor(item.mode);
  if(d!=="LONG"&&d!=="SHORT")continue;
  const status=life(item.lifecycle_result);
  // A setup that has already missed its POI or gone stale is terminal for
  // the watch queue. It must not be resurrected as a fresh WATCH on every scan.
  if(["ACTIVE","TP1_HIT","INVALIDATED","COMPLETED","EXPIRED","MISSED_BY_PRICE","MISSED_ENTRY","STALE"].includes(status))continue;
  if(String(item.decision_action||"wait").trim().toUpperCase()!==d)continue;
  const entry=(c.entry_zone||[]).map(v=>Number(v.value));
  const stop=Number(c.invalidation_level?.value),target=Number(c.target_levels?.[0]?.value);
  if(entry.length<2||entry.some(v=>!Number.isFinite(v)||v<=0)||!Number.isFinite(stop)||!Number.isFinite(target))continue;
  const low=Math.min(...entry),high=Math.max(...entry);
  const valid=d==="LONG"?(stop<low&&target>high):(stop>high&&target<low);
  if(!valid)continue;
  const risk=d==="LONG"?low-stop:stop-high;
  const reward=d==="LONG"?target-high:low-target;
  // A candidate with no actionable first-target RR is analysis-only, not a
  // setup worth surfacing in the live queue.
  if(risk<=0||reward<=0||reward/risk<2.0)continue;
  // Entry coordinates can move a few ticks as the same OB/FVG is refreshed.
  // They are not a new signal identity; update the latest candidate in place.
  const key="auto-watch|"+[m.asset,mode,c.scenario,d].join("|");
  const seenAt=Number(m.timestamp_ms||0);
  const existing=latestByKey.get(key);
  if(existing&&Number(existing.seenAt||0)>seenAt)continue;
  latestByKey.set(key,{asset:m.asset,mode,setup:c,lifecycle:"WATCH",status:"WATCH",key,seenAt,market_type:m.market_type||"futures",evidence_concepts:item.evidence_concepts||[],decision_action:item.decision_action||"",suppressMarketVisual:false});
 }
 return [...latestByKey.values()].sort((a,b)=>Number(b.seenAt||0)-Number(a.seenAt||0));
}
function registryItems(records){
 const latestById=new Map();
 for(const r of records||[]){
  // STALE records remain durable lifecycle/history bookkeeping, but only
  // ACTIVE records are actionable in the terminal.
  if(String(r.status||"").toUpperCase()!=="ACTIVE")continue;
  const key=String(r.setup_id||"");
  if(!key)continue;
  const seenAt=Number(r.last_seen_at_ms||r.created_at_ms||0);
  const lastConfirmedAt=Number(r.last_confirmed_at_ms||0);
  const existing=latestById.get(key);
  // The journal can contain repeated ACTIVE snapshots for one setup_id.
  // Collapse them here so Market Watch/history can never render duplicates.
  if(existing && Math.max(existing.lastConfirmedAt,existing.seenAt)>=Math.max(lastConfirmedAt,seenAt))continue;
  const wrapper=r.setup||{},base=wrapper.candidate||wrapper,candidate={...base,chart:wrapper.chart||base.chart};
  latestById.set(key,{asset:r.asset,market_type:r.market_type||"futures",mode:r.mode,setup:candidate,lifecycle:r.lifecycle_status||"active",status:"ACTIVE",key,seenAt,lastConfirmedAt,setupTimeframe:r.structural_timeframe||"",evidence_concepts:wrapper.evidence_concepts||[],decision_action:wrapper.decision_action||""});
 }
 const semantic=new Map();
 for(const item of latestById.values()){
  const s=item.setup||{},entry=(s.entry_zone||[]).map(v=>Number(v.value).toFixed(4)).sort().join(",");
  const stop=Number(s.invalidation_level?.value);
  // Different source labels or TP lists do not make a second trade when
  // asset, mode, scenario, side, entry zone and invalidation are identical.
  const identity=[item.asset,item.market_type,item.mode,s.scenario,dir(s),entry,Number.isFinite(stop)?stop.toFixed(4):"—"].join("|");
  const old=semantic.get(identity);
  if(!old||Math.max(item.lastConfirmedAt,item.seenAt)>Math.max(old.lastConfirmedAt,old.seenAt))semantic.set(identity,item);
 }
 return [...semantic.values()].sort((a,b)=>Math.max(b.lastConfirmedAt,b.seenAt)-Math.max(a.lastConfirmedAt,a.seenAt));
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
 const c=conceptSet(s,x),side=dir(s),directional=new Set(side==="SHORT"?["order_block.bearish"]:side==="LONG"?["order_block.bullish"]:[]),rows=[
  ["Market Structure",c.has("market_structure.bos")||c.has("market_structure.choch"),c.has("market_structure.bos")?"BOS confirmed":c.has("market_structure.choch")?"CHoCH observed":"Not confirmed"],
  ["Liquidity",c.has("liquidity.sweep"),c.has("liquidity.sweep")?"Sweep observed":"No confirmed sweep"],
  ["BOS",c.has("market_structure.bos"),c.has("market_structure.bos")?"Confirmed":"Not confirmed"],
  ["CHoCH / MSS",c.has("market_structure.choch")||c.has("market_structure.mss"),c.has("market_structure.mss")?"MSS confirmed":c.has("market_structure.choch")?"CHoCH confirmed":"Not confirmed"],
  ["Order Block",directional.size?([...directional].some(v=>c.has(v))):false,side==="LONG"&&c.has("order_block.bullish")?"Bullish OB":side==="SHORT"&&c.has("order_block.bearish")?"Bearish OB":"No directionally valid OB"],
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
function chartTf(mode,setup){
 const entry=Array.isArray(setup?.entry_zone)?setup.entry_zone[0]:null;
 if(entry?.timeframe)return String(entry.timeframe).toLowerCase();
 const m=String(mode||"").toUpperCase();
 return m==="POSITION"?"1d":m==="SWING"?"4h":"1h";
}
function mergeVisualCharts(base,extra){
 const a=base||{},b=extra||{};
 return {
  zones:[...(a.zones||[]),...(b.zones||[])],
  events:[...(a.events||[]),...(b.events||[])],
  liquidity:[...(a.liquidity||[]),...(b.liquidity||[])]
 };
}
function marketVisual(asset,mode){
 const rows=latest(scans());
 const m=rows.find(x=>String(x.asset||"").toUpperCase()===String(asset||"").toUpperCase());
 const horizons=m?.horizons||[];
 const wanted=String(mode||"").toUpperCase();
 const h=horizons.find(x=>String(x.mode||"").toUpperCase()===wanted)||horizons[0];
 return h?.chart||null;
}
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
 const priceLines=[];
 const addPriceLine=(value,title,color,lineStyle=2)=>{const p=price(value);if(!Number.isFinite(p))return;priceLines.push(series.createPriceLine({price:p,color,lineWidth:1,lineStyle,axisLabelVisible:true,title}))};
 // Entry is a zone, not two unrelated signals. Keep its boundaries native to
 // Lightweight Charts so vertical/horizontal zoom and pan always transform them.
 if(Array.isArray(entry)){
   entry.forEach((e,i)=>addPriceLine(e,i===0?"ENTRY LOW":"ENTRY HIGH","#d7ff58",2));
 }else addPriceLine(entry,"ENTRY","#d7ff58",2);
 if(s.stop_loss!=null)addPriceLine(s.stop_loss,"SL","#ff687b",2);else if(s.invalidation_level)addPriceLine(s.invalidation_level,"SL","#ff687b",2);
 (Array.isArray(targets)?targets:[]).forEach((t,i)=>addPriceLine(t,i===0?"TP1":"TP"+(i+1),"#61df9a",2));
 function rangePrice(x){const a=price(x?.priceLow??x?.low??x?.low_price),b=price(x?.priceHigh??x?.high??x?.high_price);return [Math.min(a,b),Math.max(a,b)]}
 const chartTimes=data.map(k=>k.time).sort((a,b)=>a-b);
 function xCoord(t){
  if(!Number.isFinite(t)||!chartTimes.length)return null;
  const target=Math.floor(t>1e12?t/1000:t);
  const exact=chart.timeScale().timeToCoordinate(target);
  if(exact!=null)return exact;
  // Visual objects can originate on a higher timeframe (e.g. 4h OB/FVG)
  // while the chart is rendered on 15m/1h. Those timestamps are not
  // necessarily exact bars on the displayed time scale. Resolve them to the
  // nearest displayed bar instead of falling back to 0/viewport edge.
  let lo=0,hi=chartTimes.length-1;
  while(lo<=hi){
    const mid=(lo+hi)>>1;
    if(chartTimes[mid]===target){lo=mid;break}
    if(chartTimes[mid]<target)lo=mid+1;else hi=mid-1;
  }
  const right=Math.min(chartTimes.length-1,Math.max(0,lo));
  const left=Math.max(0,right-1);
  const nearest=Math.abs(chartTimes[right]-target)<Math.abs(chartTimes[left]-target)?right:left;
  const logical=chart.timeScale().timeToIndex(chartTimes[nearest],true);
  return logical==null?null:chart.timeScale().logicalToCoordinate(logical);
 }
 function drawOverlay(){
  const w=node.clientWidth,h=node.clientHeight;ctx.clearRect(0,0,w,h);
  // Entry / SL / TP are native chart price lines, so their position and labels
  // are transformed by Lightweight Charts itself during zoom, pan and resize.
  const rect=(z,fill,stroke)=>{
   const [lo,hi]=rangePrice(z);
   if(!Number.isFinite(lo)||!Number.isFinite(hi))return;
   const y1=series.priceToCoordinate(hi),y2=series.priceToCoordinate(lo);
   if(y1==null||y2==null)return;
   const ts=time(z.timeStart??z.startTime??z.time_start),te=time(z.timeEnd??z.endTime??z.time_end);
   const x1=xCoord(ts),x2=xCoord(te);
   // Never invent an x position. A zone with no mappable time must not be
   // stretched from 0 to the viewport edge; that was the source of blocks
   // appearing detached from the candles.
   if(x1==null||x2==null)return;
   const left=Math.min(x1,x2),right=Math.max(x1,x2);
   ctx.fillStyle=fill;
   ctx.fillRect(left,Math.min(y1,y2),Math.max(2,right-left),Math.abs(y2-y1));
   ctx.strokeStyle=stroke;
   ctx.strokeRect(left,Math.min(y1,y2),Math.max(2,right-left),Math.abs(y2-y1));
  };
  // Entry zone uses the same price transform as candles/price lines. It is
  // intentionally drawn as a band, not as a second independent coordinate system.
  if(Array.isArray(entry)&&entry.length>=2){
    const vals=entry.map(price).filter(Number.isFinite);
    if(vals.length>=2){
      const y1=series.priceToCoordinate(Math.max(...vals)),y2=series.priceToCoordinate(Math.min(...vals));
      if(y1!=null&&y2!=null){ctx.fillStyle="rgba(215,255,88,.07)";ctx.fillRect(0,Math.min(y1,y2),w,Math.abs(y2-y1));}
    }
  }
  const drawZone=(z,fill,stroke,label)=>{
    const [lo,hi]=rangePrice(z);
    if(!Number.isFinite(lo)||!Number.isFinite(hi))return;
    const y1=series.priceToCoordinate(hi),y2=series.priceToCoordinate(lo);
    if(y1==null||y2==null)return;
    const ts=time(z.timeStart??z.startTime??z.time_start),te=time(z.timeEnd??z.endTime??z.time_end);
    const x1=xCoord(ts),x2=xCoord(te);
    if(x1==null||x2==null)return;
    const top=Math.min(y1,y2),height=Math.max(2,Math.abs(y2-y1)),left=Math.min(x1,x2),width=Math.max(3,Math.abs(x2-x1));
    ctx.save();
    ctx.fillStyle=fill;
    ctx.fillRect(left,top,width,height);
    ctx.strokeStyle=stroke;
    ctx.lineWidth=1;
    ctx.strokeRect(left+.5,top+.5,Math.max(1,width-1),Math.max(1,height-1));
    ctx.font="700 9px system-ui,-apple-system,Segoe UI,sans-serif";
    ctx.fillStyle=stroke;
    ctx.fillText(label,Math.max(3,left+4),Math.max(11,top+12));
    ctx.restore();
  };
  obs.forEach(z=>drawZone(z,"rgba(255,184,77,.24)","rgba(255,184,77,.95)","OB"));
  fvgs.forEach(z=>drawZone(z,"rgba(174,108,255,.24)","rgba(174,108,255,.95)","FVG"));
  (chartData.liquidity||[]).forEach(z=>{const p=price(z);if(!Number.isFinite(p))return;const y=series.priceToCoordinate(p);const x1=xCoord(time(z.timeStart)),x2=xCoord(time(z.timeEnd));if(y==null||x1==null||x2==null)return;ctx.beginPath();ctx.moveTo(x1,y+.5);ctx.lineTo(x2,y+.5);ctx.setLineDash([2,4]);ctx.strokeStyle=z.type==="buy"?"#5bd7ff":"#ff8b9e";ctx.stroke();ctx.setLineDash([]);ctx.font="700 9px system-ui,-apple-system,Segoe UI,sans-serif";ctx.fillStyle=ctx.strokeStyle;ctx.fillText(z.type==="buy"?"BUY LIQ":"SELL LIQ",Math.min(w-55,Math.max(4,x1+4)),Math.max(11,y-4))});
  Object.entries(events).forEach(([name,list])=>{for(const e of list){const p=price(e);if(!Number.isFinite(p))continue;const y=series.priceToCoordinate(p);if(y==null)continue;let x1=xCoord(time(e.timeStart??e.startTime??e.time_start)),x2=xCoord(time(e.timeEnd??e.endTime??e.time_end));if(x1==null||x2==null)continue;ctx.beginPath();ctx.moveTo(x1,y+.5);ctx.lineTo(x2,y+.5);ctx.setLineDash([5,5]);ctx.strokeStyle=name==="BOS"?"#f3c74f":name==="CHoCH"?"#67b7ff":"#ff9d66";ctx.stroke();ctx.setLineDash([]);ctx.font="700 9px system-ui,-apple-system,Segoe UI,sans-serif";ctx.fillStyle=ctx.strokeStyle;ctx.fillText(name,Math.min(w-35,Math.max(4,x1+4)),Math.max(11,y-4))}})}
 function resize(){const w=Math.max(1,node.clientWidth),h=Math.max(1,node.clientHeight);chart.resize(w,h);overlay.width=Math.floor(w*dpr);overlay.height=Math.floor(h*dpr);overlay.style.width=w+"px";overlay.style.height=h+"px";ctx.setTransform(dpr,0,0,dpr,0,0);drawOverlay()}
 chart.timeScale().fitContent();
 chart.timeScale().subscribeVisibleLogicalRangeChange(drawOverlay);
 if(chart.timeScale().subscribeVisibleTimeRangeChange)chart.timeScale().subscribeVisibleTimeRangeChange(drawOverlay);
 // Lightweight Charts owns the actual price scale. The overlay is only a
 // visual layer, so redraw it after every pointer/zoom gesture as well; this
 // covers vertical price-scale zoom where the visible time range is unchanged.
 let raf=0;
 const scheduleOverlay=()=>{if(raf)return;raf=requestAnimationFrame(()=>{raf=0;drawOverlay()})};
 ["pointermove","pointerdown","wheel","touchmove"].forEach(evt=>node.addEventListener(evt,scheduleOverlay,{passive:true}));
 const ro=new ResizeObserver(resize);ro.observe(node);resize();
 node._aicfaChartCleanup=()=>{ro.disconnect();if(raf)cancelAnimationFrame(raf);["pointermove","pointerdown","wheel","touchmove"].forEach(evt=>node.removeEventListener(evt,scheduleOverlay));priceLines.forEach(p=>{try{series.removePriceLine(p)}catch(_){}});chart.remove()};
}
async function hydrateCharts(){
 const nodes=[...document.querySelectorAll(".market-chart[data-symbol]")];
 await Promise.all(nodes.map(async node=>{try{const q=new URLSearchParams({symbol:node.dataset.symbol,market_type:node.dataset.marketType||"futures",timeframe:node.dataset.timeframe,limit:"200"});const response=await fetch(API_BASE+"/chart?"+q.toString()+"&t="+Date.now(),{cache:"no-store"});const data=response.ok?await response.json():null;renderCandleChart(node,data?.candles||[],JSON.parse(node.dataset.setup||"{}"))}catch(_){node.innerHTML='<div class="chart-empty">CHART UNAVAILABLE</div>'}}));
}
function setupCard(x){
 const s=x.setup||{},entry=s.entry_zone||[],targets=s.target_levels||[],ev=entry.length?entry.map(v=>v.value).join(" — "):"—",sl=s.invalidation_level?.value??"—",tp=targets.length?targets.map(v=>String(v.value)+" ("+(v.timeframe||"?")+" · "+(v.source||"unknown source")+")").join(" — "):"—";
 const lifecycleStatus=String(x.status||x.lifecycle||"").toUpperCase(),missed=lifecycleStatus==="MISSED BY PRICE"||lifecycleStatus==="MISSED_BY_PRICE";
 const entryValues=entry.map(v=>Number(v.value)).filter(Number.isFinite),entryLimit=entryValues.length?(dir(s)==="LONG"?Math.max(...entryValues):Math.min(...entryValues)):NaN;
 const fullChart=mergeVisualCharts(x.suppressMarketVisual?null:marketVisual(x.asset,x.mode),s.chart);
 const low=entry.length?Math.min(...entry.map(v=>Number(v.value))):NaN,high=entry.length?Math.max(...entry.map(v=>Number(v.value))):NaN,stop=Number(s.invalidation_level?.value),take=targets.length?Number(targets[0]?.value):NaN;
 const geometryValid=Number.isFinite(low)&&Number.isFinite(high)&&low>0&&high>0&&Number.isFinite(stop)&&stop>0&&Number.isFinite(take)&&take>0;
 const risk=Number.isFinite(low)&&Number.isFinite(high)&&Number.isFinite(stop)?(dir(s)==="LONG"?low-stop:stop-high):NaN;
 const reward=Number.isFinite(low)&&Number.isFinite(high)&&Number.isFinite(take)?(dir(s)==="LONG"?take-high:low-take):NaN;
 const rr=geometryValid&&Number.isFinite(risk)&&Number.isFinite(reward)&&risk>0&&reward>0?reward/risk:NaN;
 const rrText=Number.isFinite(rr)?rr.toFixed(2)+"R":"—";
 const age=Number.isFinite(Number(x.seenAt))&&Number(x.seenAt)>0?Math.max(0,Date.now()-Number(x.seenAt)):NaN;
 const freshness=Number.isFinite(age)?(age<60000?"LIVE":age<3600000?Math.floor(age/60000)+"m ago":Math.floor(age/3600000)+"h ago"):"—";
 const why=[...(s.rationale||[])].filter(v=>!v.startsWith("MTF hierarchy:")&&!/^setup zone observed on /.test(v));
 const hierarchy=[...(s.rationale||[])].filter(v=>v.startsWith("MTF hierarchy:")).map(v=>v.replace(/^MTF hierarchy:\s*/,"")).filter((v,i,a)=>a.indexOf(v)===i).join(" · ");
 const side=dir(s),tf=chartTf(x.mode,s);
 return '<article class="setup '+side.toLowerCase()+'">'+
 '<header class="setup-head"><div class="symbol-block"><b>'+esc(x.asset)+'</b><span>'+esc(hor(x.mode))+' / '+esc(s.scenario||"SETUP")+'</span></div><div class="signal"><i></i><strong>'+esc(missed?"MISSED BY PRICE":side)+'</strong></div></header>'+
 '<div class="setup-grid"><section class="chart-panel"><div class="panel-kicker">MARKET STRUCTURE · '+esc(tf.toUpperCase())+'</div><div class="market-chart" data-symbol="'+esc(x.asset||"")+'" data-market-type="'+esc(x.market_type||"futures")+'" data-timeframe="'+tf+'" data-setup="'+esc(JSON.stringify({entry_zone:entry,invalidation_level:s.invalidation_level,target_levels:targets,zones:s.zones,order_blocks:s.order_blocks,fvgs:s.fvgs,bos:s.bos,choch:s.choch,mss:s.mss,chart:fullChart}))+'"></div><div class="chart-meta"><span>ENTRY <b>'+esc(ev)+'</b></span>'+(missed?'<span>'+(dir(s)==="LONG"?"MAX ENTRY":"MIN ENTRY")+' <b>'+esc(Number.isFinite(entryLimit)?String(Number(entryLimit.toPrecision(8))):"—")+'</b></span>':'')+'<span>SL <b>'+esc(sl)+'</b></span><span>TP1 <b>'+esc(tp)+'</b></span><span>RR / FRESHNESS <b>'+esc(rrText+" · "+freshness)+'</b></span></div></section>'+
 '<aside class="setup-side"><div class="scenario"><span class="panel-kicker">SCENARIO</span><p>'+esc(scenarioText(s))+'</p></div><div class="evidence"><span class="panel-kicker">EVIDENCE</span>'+evidence(s,x)+'</div><div class="decision"><span class="panel-kicker">WHY '+esc(side)+'</span><p>'+esc(why.length?why.join(" · "):"Current structural evidence supports this setup.")+'</p><small>'+esc(hierarchy)+'</small></div></aside></div></article>';
}
function marketVisualCard(asset,mode,visual,marketType="futures"){
 const tf=chartTf(mode,{});
 const payload={chart:visual||{zones:[],events:[],liquidity:[]}};
 return '<article class="setup market-only"><header class="setup-head"><div class="symbol-block"><b>'+esc(asset)+'</b><span>'+esc(hor(mode))+' / MARKET STRUCTURE</span></div><div class="signal"><i></i><strong>ANALYSIS</strong></div></header><div class="setup-grid"><section class="chart-panel"><div class="panel-kicker">MARKET STRUCTURE · '+esc(tf.toUpperCase())+'</div><div class="market-chart" data-symbol="'+esc(asset||"")+'" data-market-type="'+esc(marketType)+'" data-timeframe="'+tf+'" data-setup="'+esc(JSON.stringify(payload))+'"></div><div class="chart-meta"><span>FVG / OB <b>VISIBLE</b></span><span>BOS / CHoCH / MSS <b>VISIBLE</b></span><span>LIQUIDITY <b>VISIBLE</b></span></div></section><aside class="setup-side"><div class="scenario"><span class="panel-kicker">MARKET MAP</span><p>All SMC geometry is taken from the same AICFA feature frames used by the scanner and projected onto the selected candles.</p></div><div class="evidence"><span class="panel-kicker">OBJECTS</span><p>FVG · Order Block · BOS · CHoCH · MSS · Liquidity</p></div></aside></div></article>';
}
function waitCards(ms){
 const out=[];
 for(const m of ms){
  const pendingModes=new Set();
  for(const s of m.setups||[]){
   const c=s.candidate||s,lifeStatus=life(s.lifecycle_result);
   if(!["LONG","SHORT"].includes(dir(c))||["ACTIVE","TP1_HIT","INVALIDATED","COMPLETED","EXPIRED"].includes(lifeStatus))continue;
   const mode=hor(s.mode),entry=(c.entry_zone||[]).map(x=>Number(x.value)).filter(Number.isFinite);
   const sl=Number(c.invalidation_level?.value??c.stop_loss);
   const tp=Number(c.target_levels?.[0]?.value??c.take_profit);
   const fmt=v=>Number.isFinite(v)?String(Number(v.toPrecision(8))):"—";
   const missed=lifeStatus==="MISSED_BY_PRICE";
   const entryLimit=entry.length?(dir(c)==="LONG"?Math.max(...entry):Math.min(...entry)):NaN;
   const lifecycleReason=s.lifecycle_result?.reason||s.lifecycle_result?.message||"";
   out.push({asset:m.asset,mode,action:missed?"MISSED BY PRICE":"WATCH",checks:[],why:missed?(lifecycleReason||"Price moved beyond the permitted entry zone"):(c.rationale||c.invalidation||["Waiting for price to reach the entry zone"])[0],details:(missed?(dir(c)==="LONG"?"MAX ENTRY ":"MIN ENTRY ")+fmt(entryLimit)+" · ":"")+"ENTRY "+(entry.length?entry.map(fmt).join("–"):"—")+" · SL "+fmt(sl)+" · TP1 "+fmt(tp)});
   pendingModes.add(mode);
  }
  for(const h of m.horizons||[]){
   const action=String(h.decision_action||h.decision||"").toUpperCase();if(action==="LONG"||action==="SHORT"||action==="READY"||pendingModes.has(hor(h.mode)))continue;
   const c=new Set(h.supported_concepts||[]),checks=[["Liquidity",c.has("liquidity.sweep")],["Market Structure",c.has("market_structure.bos")||c.has("market_structure.choch")],["OB",c.has("order_block.bullish")||c.has("order_block.bearish")],["FVG",c.has("imbalance.fvg")],["Zone Reaction",c.has("price_action.rejection")],["Volume",c.has("volume.evidence")||c.has("volume.confirmation")]];
   out.push({asset:m.asset,mode:h.mode,action:action||"WAIT",checks,why:(h.setup_reasons||h.decision_reasons||["structural setup is incomplete"])[0]});
  }
 }
 return out;
}
function historyCard(x){
 const s=x.setup||{},side=dir(s),selected=x.key===ui.selected;
 return '<button class="history-item '+side.toLowerCase()+(selected?" selected":"")+'" data-setup-key="'+esc(x.key)+'"><span class="history-dot"></span><span class="history-main"><b>'+esc(x.asset)+'</b><small>'+esc(hor(x.mode))+' · '+esc(s.scenario||"SETUP")+'</small></span><strong>'+esc(side)+'</strong><em>'+esc(x.status||"ACTIVE")+'</em><time>'+esc(tm(x.seenAt))+'</time></button>';
}
function renderCenter(){
 const root=$("#setups");
 if(ui.manualView){
  const view=ui.manualView;
  if(view.state==="analyzing"){
   const sig="manual-analyzing|"+view.asset;
   if(root.dataset.signature!==sig){
    root.dataset.signature=sig;
    $("#workspaceTitle").textContent=view.asset+" · ANALYZING";
    root.innerHTML='<div class="workspace-empty"><b>ANALYZING MARKET</b><span>Running the selected market through AICFA analysis.</span></div>';
   }
   return;
  }
  if(view.state==="result"){
   const sig="manual-result|"+view.asset+"|"+view.scanNumber+"|"+JSON.stringify(view.items||[])+"|"+JSON.stringify(view.visual||{});
   if(root.dataset.signature!==sig){
    root.dataset.signature=sig;
    if(view.items?.length){
     $("#workspaceTitle").textContent=view.asset+" · "+view.items.length+" WATCH";
     root.innerHTML='<div class="workspace-empty"><b>WATCH — НЕ АКТИВНЫЕ СДЕЛКИ</b><span>Кандидаты из текущего ручного сканирования. Они не являются активными сделками.</span></div>'+view.items.map(setupCard).join("");
     hydrateCharts();
    }else{
     $("#workspaceTitle").textContent=view.asset+" · NO SETUP";
     root.innerHTML='<div class="workspace-empty"><b>NO SETUP</b><span>За отведённое время подтверждённый сетап не найден.</span></div>';
    }
   }
   return;
  }
 }
 if(ui.centerEmpty){
  root.dataset.signature="";
  $("#workspaceTitle").textContent=(ui.centerEmptyMarket||"MARKET")+" · NO SETUP";
  root.innerHTML='<div class="workspace-empty"><b>NO ACTIVE SETUP</b><span>This market was analyzed by the same AICFA scanner pipeline. No actionable setup was found.</span></div>';
  return;
 }
 const x=allHistory().find(h=>h.key===ui.centerKey);
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
function renderHistory(){
 const visible=allHistory().filter(x=>state.filter==="ALL"||hor(x.mode)===state.filter);
 if(visible.length&&!visible.some(x=>x.key===ui.selected)){
  ui.selected=visible[0].key;
  if(!ui.manualView&&!ui.centerEmpty&&ui.centerKey===null)ui.centerKey=visible[0].key;
 }
 $("#historyCount").textContent=visible.length;
 $("#setupHistory").innerHTML=visible.length?visible.map(historyCard).join(""):'<div class="rail-empty">NO SETUPS YET</div>';
}
function renderRails(ms,rows){
 const waits=waitCards(ms).filter(s=>state.filter==="ALL"||String(s.mode).toUpperCase()===state.filter);
 
 $("#waits").innerHTML=waits.length?waits.map(w=>'<article class="wait"><div><b>'+esc(w.asset)+'</b><span>'+esc(w.mode)+'</span></div><strong>'+esc(w.action)+'</strong><div class="checks">'+w.checks.map(c=>'<span class="'+(c[1]?"ok":"missing")+'">'+(c[1]?"✓":"—")+" "+esc(c[0])+'</span>').join("")+'</div>'+(w.details?'<small class="wait-levels">'+esc(w.details)+'</small>':'')+'<p>'+esc(w.why)+'</p></article>').join(""):'<div class="rail-empty">NO WAIT ANALYSIS</div>';
 const recent=rows.slice(0,80);
 $("#activity").innerHTML=recent.map(e=>{const p=e.payload||{},m=p.markets?.[0],d=m?.diagnostics||{};return '<div class="row"><time>'+tm(e.timestamp_ms)+'</time><b>'+esc(m?.asset)+'</b><span class="'+String(d.status||"").toLowerCase()+'">'+esc(String(d.status||"—").toUpperCase())+'</span><small>'+(m?.setups||[]).length+' setups</small></div>'}).join("");
}
function render(rows,registry){
 const p=rows[0]?.payload||{},ms=latest(rows),u=Number(p.universe_size||0),pos=Number(p.queue_position||0),pct=u?Math.min(100,pos/u*100):0;
 // Keep directional, risk-valid candidates from autonomous scans visible as
 // WATCH items even before lifecycle activation. They must never masquerade
 // as ACTIVE registry setups.
 ui.autoWatchItems=automaticWatchItems(ms);
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
function monitorStatusLabel(status){
 const labels={ACTIVE:"ACTIVE",TP1_HIT:"TP1 HIT",COMPLETED:"TP2 HIT",INVALIDATED:"INVALIDATED",EXPIRED:"EXPIRED",MISSED_BY_PRICE:"MISSED ENTRY"};
 return labels[String(status||"").toUpperCase()]||String(status||"").replaceAll("_"," ").toUpperCase();
}
function renderTradeMonitor(){
 const all=state.monitorRecords||[],mode=ui.monitorMode;
 const modeRows=all.filter(r=>hor(r.mode)===mode);
 const activeRows=modeRows.filter(r=>["ACTIVE","TP1_HIT"].includes(String(r.status||"").toUpperCase()));
 const completedRows=modeRows.filter(r=>["COMPLETED","INVALIDATED","EXPIRED","MISSED_BY_PRICE"].includes(String(r.status||"").toUpperCase()));
 $("#monitorCount").textContent=String(modeRows.length);
 $("#monitorActiveCount").textContent=String(activeRows.length);
 $("#monitorCompletedCount").textContent=String(completedRows.length);
 document.querySelectorAll("[data-monitor-mode]").forEach(b=>b.classList.toggle("active",b.dataset.monitorMode===ui.monitorMode));
 document.querySelectorAll("[data-monitor-view]").forEach(b=>b.classList.toggle("active",b.dataset.monitorView===ui.monitorView));
 const rows=ui.monitorView==="ACTIVE"?activeRows:completedRows;
 const root=$("#tradeMonitor");
 root.innerHTML=rows.length?rows.map(r=>{
  const wrapper=r.setup||{},s=wrapper.candidate||wrapper,entry=(s.entry_zone||[]).map(x=>Number(x.value)).filter(Number.isFinite);
  const entryText=entry.length?entry.map(v=>formatMarketPrice(v)).join(" – "):"—";
  const stop=Number(s.invalidation_level?.value),targets=(s.target_levels||[]).map(x=>Number(x.value)).filter(Number.isFinite);
  const terminal=String(r.status||"").toUpperCase();
  const when=ui.monitorView==="ACTIVE"?(r.last_seen_at_ms||r.created_at_ms):(r.closed_at_ms||r.last_seen_at_ms);
  const reason=r.outcome_reason||"";
  return '<article class="monitor-item '+(terminal==="INVALIDATED"?"monitor-loss":terminal==="COMPLETED"?"monitor-win":"")+'"><div class="monitor-item-head"><b>'+esc(r.asset)+'</b><span>'+esc(monitorStatusLabel(terminal))+'</span></div><div class="monitor-meta"><b class="'+(String(r.direction||s.direction).toUpperCase()==="SHORT"?"short-text":"long-text")+'">'+esc(r.direction||s.direction||"—")+'</b><span>'+esc(String(s.scenario||"").replaceAll("_"," ").toUpperCase())+'</span><time>'+esc(tm(when))+'</time></div><div class="monitor-prices"><span>ENTRY <b>'+esc(entryText)+'</b></span><span>SL <b>'+esc(Number.isFinite(stop)?formatMarketPrice(stop):"—")+'</b></span><span>TP <b>'+esc(targets.length?targets.map(formatMarketPrice).join(" / "):"—")+'</b></span></div>'+(reason?'<p>'+esc(reason)+'</p>':"")+'</article>';
 }).join(""):'<div class="rail-empty">'+(ui.monitorView==="ACTIVE"?"NO ACTIVE SETUPS FOR THIS STRATEGY":"NO COMPLETED SETUPS FOR THIS STRATEGY")+'</div>';
}
async function refresh(){
 if(refreshInFlight)return;refreshInFlight=true;
 try{
  const [h,d,r,tmr,mk,prices]=await Promise.all([
   getJson("/health",{}),
   getJson("/journal/scans?limit=500",{events:[]}),
   getJson("/journal/registry",{setups:[]}),
   getJson("/journal/trade-monitor",{setups:[]}),
   getJson("/markets",{markets:[]}),
   getJson("/market-prices",{prices:{}})
  ]);
  state.events=d.events||[];const registry=r.setups||[];state.registry=registry;state.monitorRecords=tmr.setups||[];state.markets=mk.markets||[];const previous=state.prices;state.prices=prices.prices||{};state.previousPrices=previous;const sig=JSON.stringify([state.events,registry,state.markets]);
  if(sig!==lastEventSignature){lastEventSignature=sig;render(scans(),registry)}else{renderMarkets()}renderTradeMonitor();
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
 if(!market||ui.marketBusy)return;
 ui.marketIndex=Number(index);
 ui.marketBusy=true;
 ui.manualItems=[];
 ui.manualView={state:"analyzing",asset:market.asset};
 ui.centerEmpty=false;ui.centerKey=null;ui.centerEmptyMarket=market.asset;
 $("#setups").dataset.signature="";
 renderMarkets();renderHistory();renderCenter();
 try{
  const response=await fetch(API_BASE+"/market-scan",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({market_index:Number(index)})});
  const data=await response.json();
  if(!response.ok)throw new Error(data.detail||data.error||"scan_failed");
  const items=registryItems(data.setups||[]);
  if(items.length){
   const keys=new Set(items.map(x=>x.key));
   ui.history=[...ui.history.filter(x=>!keys.has(x.key)),...items].sort((a,b)=>Number(b.lastConfirmedAt||b.seenAt)-Number(a.lastConfirmedAt||a.seenAt));
   ui.manualView=null;ui.manualItems=[];
   const item=items[0];ui.centerKey=item.key;ui.selected=item.key;ui.centerEmpty=false;ui.centerEmptyMarket="";
  }else{
   const pendingItems=(data.watch_candidates||[]).map((pending,index)=>{
    const candidate=pending.candidate||{},mode=hor(pending.mode),asset=pending.asset||market.asset;
    const lifeStatus=String(pending.lifecycle_status||"").toLowerCase();const missed=lifeStatus==="missed_by_price";return {asset,mode,setup:candidate,lifecycle:missed?"MISSED_BY_PRICE":"WATCH",status:missed?"MISSED BY PRICE":"WATCH",key:"watch|"+asset+"|"+mode+"|"+String(candidate.scenario||"")+"|"+String(candidate.direction||"")+"|"+index,seenAt:Number(data.scanned_at_ms||Date.now()),market_type:market.market_type||"futures",suppressMarketVisual:true};
   });
   ui.manualItems=pendingItems;
   ui.manualView={state:"result",asset:market.asset,scanNumber:data.scan_number,items:pendingItems,visual:data.market_visual||{zones:[],events:[],liquidity:[]},mode:"INTRADAY",marketType:market.market_type||"futures"};
   ui.centerKey=null;ui.selected=null;ui.centerEmpty=false;ui.centerEmptyMarket="";
  }
  renderHistory();renderCenter();
 }catch(error){
  ui.manualView=null;ui.manualItems=[];
  ui.centerKey=null;ui.selected=null;ui.centerEmpty=true;ui.centerEmptyMarket=market.asset;
  const detail=error&&error.message?String(error.message):"unknown scanner error";
  $("#workspaceTitle").textContent=market.asset+" · SCAN ERROR";
  $("#setups").dataset.signature="";
  $("#setups").innerHTML='<div class="workspace-empty"><b>MARKET SCAN UNAVAILABLE</b><span>'+esc(detail)+'</span></div>';
 }finally{
  ui.marketBusy=false;renderMarkets();
 }
}
$("#filters").addEventListener("click",e=>{const f=e.target.dataset.filter;if(!f)return;document.querySelectorAll("#filters button").forEach(b=>b.classList.remove("active"));e.target.classList.add("active");state.filter=f;render(scans(),state.registry)});
$("#marketWatch").addEventListener("click",e=>{const b=e.target.closest("[data-market-index]");if(!b)return;scanMarket(Number(b.dataset.marketIndex))});
$("#setupHistory").addEventListener("click",e=>{const b=e.target.closest("[data-setup-key]");if(!b)return;const key=b.dataset.setupKey;ui.selected=key;ui.centerKey=key;ui.manualView=null;ui.centerEmpty=false;ui.centerEmptyMarket="";renderHistory();renderCenter()});
$("#monitorModes").addEventListener("click",e=>{const b=e.target.closest("[data-monitor-mode]");if(!b)return;ui.monitorMode=b.dataset.monitorMode;renderTradeMonitor()});
$("#monitorViews").addEventListener("click",e=>{const b=e.target.closest("[data-monitor-view]");if(!b)return;ui.monitorView=b.dataset.monitorView;renderTradeMonitor()});
$(".left-rail").addEventListener("click",e=>{const head=e.target.closest(".rail-head");if(!head)return;const panel=head.parentElement;if(!panel.matches(".market-watch,.rail-panel"))return;panel.classList.toggle("collapsed")});
refresh();setInterval(refresh,3000);