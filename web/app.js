const API_BASE = window.AICFA_FEED_URL || "/api";
const state = { setups: [], events: [], markets: [], filter: "ALL", known: new Set() };

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "—").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const pick = (o,...keys) => { for (const k of keys) if (o && o[k] !== undefined && o[k] !== null) return o[k]; };
function fmtTime(ms){ if(!ms) return "—"; return new Date(Number(ms)).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}); }
function age(ms){ if(!ms) return "—"; const n=Math.max(0,Date.now()-Number(ms)); if(n<60000)return "NOW"; if(n<3600000)return Math.floor(n/60000)+"M"; if(n<86400000)return Math.floor(n/3600000)+"H"; return Math.floor(n/86400000)+"D"; }

async function get(path){
  const r = await fetch(API_BASE + path, {cache:"no-store"});
  if(!r.ok) throw new Error("HTTP "+r.status);
  return r.json();
}

function setupId(asset, s){
  return JSON.stringify([asset, pick(s,"mode","horizon","profile"), pick(s,"entry","entry_price","entry_zone"), pick(s,"invalidation","sl","stop_loss"), pick(s,"tp","tp1","target")]);
}

function latestMarketState(scans){
  const latest = new Map();
  for(const event of scans){
    for(const market of (event.payload?.markets || [])){
      const asset = market.asset || "UNKNOWN";
      const current = latest.get(asset);
      if(!current || Number(event.timestamp_ms || 0) > Number(current.timestamp_ms || 0)){
        latest.set(asset, {asset, timestamp_ms:event.timestamp_ms, market});
      }
    }
  }
  return [...latest.values()];
}

function buildCurrentSetups(scanData){
  const markets = latestMarketState(scanData.events || []);
  const setups = [];
  for(const item of markets){
    for(const s of (item.market?.setups || [])){
      const direction = String(pick(s,"direction","side","signal") || "").toUpperCase();
      const lifecycle = String(pick(s,"lifecycle","status") || "ACTIVE").toUpperCase();
      if(!["LONG","SHORT"].includes(direction)) continue;
      if(lifecycle !== "ACTIVE") continue;
      setups.push({
        raw:s,
        asset:item.asset,
        direction,
        horizon:String(pick(s,"horizon","mode","profile") || "—").toUpperCase(),
        entry:pick(s,"entry","entry_price","entry_zone"),
        sl:pick(s,"sl","stop_loss","invalidation"),
        tp:pick(s,"tp","tp1","target"),
        rr:pick(s,"rr","risk_reward"),
        lifecycle,
        evidence:pick(s,"evidence","reasons","confluence") || [],
        timestamp:item.timestamp_ms
      });
    }
  }
  return {markets, setups};
}

function evidenceTags(s){
  const out=[]; const raw=s.evidence;
  if(Array.isArray(raw)) raw.forEach(x=>out.push(typeof x==="string" ? x : pick(x,"type","name","label")));
  else if(raw && typeof raw==="object") Object.keys(raw).forEach(k=>{if(raw[k]) out.push(k)});
  ["market_structure","liquidity","order_block","ob","fvg","volume"].forEach(k=>{if(s.raw?.[k] && !out.includes(k)) out.push(k)});
  return [...new Set(out.filter(Boolean))].slice(0,6);
}

function renderStats(){
  const active = state.setups.length;
  const scanned = state.markets.length;
  const wait = Math.max(0, scanned - active);
  $("#marketCount").textContent = scanned;
  $("#setupCount").textContent = active;
  $("#waitCount").textContent = wait;
}

function renderSetups(){
  const root=$("#setups");
  const rows=state.setups.filter(s=>state.filter==="ALL" || s.horizon===state.filter);
  if(!rows.length){
    root.innerHTML='<div class="empty"><strong>NO ACTIVE SETUPS</strong><span>AICFA is scanning. WAIT is a market state, not a trade.</span></div>';
    return;
  }
  root.innerHTML=rows.map(s=>{
    const d=s.direction.toLowerCase(), tags=evidenceTags(s);
    return '<article class="card '+d+'">'+
      '<div class="card-head"><div><div class="asset">'+esc(s.asset)+'</div><div class="horizon">'+esc(s.horizon)+'</div></div><div class="dir '+d+'">'+esc(s.direction)+'</div></div>'+
      '<div class="levels">'+
        '<div><span>ENTRY</span><b>'+esc(s.entry)+'</b></div>'+
        '<div><span>INVALIDATION</span><b>'+esc(s.sl)+'</b></div>'+
        '<div><span>TARGET</span><b>'+esc(s.tp)+'</b></div>'+
        '<div><span>RR</span><b>'+esc(s.rr)+'</b></div>'+
      '</div>'+
      '<div class="card-foot">'+tags.map(t=>'<span class="tag">'+esc(String(t).replaceAll("_"," ").toUpperCase())+'</span>').join("")+'<span class="fresh">'+age(s.timestamp)+'</span></div>'+
    '</article>';
  }).join("");
}

function renderEvents(){
  const root=$("#events");
  const useful=state.events.filter(e=>e.event_type!=="scan");
  $("#eventCount").textContent=useful.length+" EVENTS";
  if(!useful.length){
    root.innerHTML='<div class="empty compact"><strong>JOURNAL QUIET</strong><span>Scanner heartbeats are hidden from the public event stream.</span></div>';
    return;
  }
  root.innerHTML=useful.slice(0,20).map(e=>{
    const p=e.payload||{}, asset=pick(p,"asset","symbol","market")||pick(e,"asset")||"MARKET";
    const type=String(e.event_type||"EVENT").replaceAll("_"," ").toUpperCase();
    return '<div class="event"><time>'+esc(fmtTime(e.timestamp_ms))+'</time><span class="event-type">'+esc(type)+'</span><span class="event-main"><b>'+esc(asset)+'</b> '+esc(p.message||p.status||p.action||"journal event")+'</span><span class="event-life">'+esc(p.lifecycle||"")+'</span></div>';
  }).join("");
}

async function refresh(){
  try{
    const [health,scanData,eventData]=await Promise.all([
      get("/health"),
      get("/journal/scans?limit=500"),
      get("/journal/events?limit=100")
    ]);
    const built=buildCurrentSetups(scanData);
    state.markets=built.markets;
    state.setups=built.setups;
    state.events=eventData.events||[];
    $("#statusDot").parentElement.className="status live";
    $("#statusText").textContent="LIVE";
    $("#updated").textContent="UPDATED "+new Date().toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});
    $("#dataState").textContent=health.ok?"HEALTHY":"DEGRADED";
    renderStats(); renderSetups(); renderEvents();
  }catch(err){
    $("#statusDot").parentElement.className="status bad";
    $("#statusText").textContent="OFFLINE";
    $("#dataState").textContent="UNAVAILABLE";
  }
}

$("#filters").addEventListener("click",e=>{
  if(!e.target.dataset.filter) return;
  document.querySelectorAll("#filters button").forEach(b=>b.classList.remove("active"));
  e.target.classList.add("active");
  state.filter=e.target.dataset.filter;
  renderSetups();
});

refresh();
setInterval(refresh,15000);
