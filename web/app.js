const API_BASE = window.AICFA_FEED_URL || "/api";
const state = { setups: [], markets: [], scans: [], filter: "ALL", sound: false };

const $ = s => document.querySelector(s);
const esc = v => String(v ?? "—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
const pick = (o,...keys) => { for(const k of keys) if(o && o[k] !== undefined && o[k] !== null) return o[k]; };
const dirOf = s => String(pick(s,"direction","side","signal")||"").toUpperCase();
const horizonOf = s => String(pick(s,"horizon","mode","profile")||"—").toUpperCase();
const lifeOf = s => String(pick(s,"lifecycle","status")||"ACTIVE").toUpperCase();

async function get(path){ const r=await fetch(API_BASE+path,{cache:"no-store"}); if(!r.ok) throw Error("HTTP "+r.status); return r.json(); }
function fmt(ms){ return ms ? new Date(Number(ms)).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}) : "—"; }
function age(ms){ if(!ms)return "—"; const n=Math.max(0,Date.now()-Number(ms)); if(n<60000)return "NOW"; if(n<3600000)return Math.floor(n/60000)+"M"; return Math.floor(n/3600000)+"H"; }

function latestMarkets(events){
  const map=new Map();
  for(const e of events||[]) for(const m of e.payload?.markets||[]){
    const old=map.get(m.asset);
    if(!old || Number(e.timestamp_ms||0)>Number(old.timestamp_ms||0)) map.set(m.asset,{asset:m.asset,market:m,timestamp_ms:e.timestamp_ms});
  }
  return [...map.values()];
}

function currentState(scanData){
  const markets=latestMarkets(scanData.events);
  const setups=[];
  for(const x of markets) for(const s of x.market?.setups||[]){
    if(!["LONG","SHORT"].includes(dirOf(s)) || lifeOf(s)!=="ACTIVE") continue;
    setups.push({raw:s,asset:x.asset,direction:dirOf(s),horizon:horizonOf(s),
      entry:pick(s,"entry","entry_price","entry_zone"),
      invalidation:pick(s,"invalidation","sl","stop_loss"),
      target:pick(s,"tp","tp1","target"),rr:pick(s,"rr","risk_reward"),
      timestamp:x.timestamp_ms});
  }
  return {markets,setups};
}

function tags(s){
  const out=[], raw=s.raw||{};
  const ev=pick(raw,"evidence","reasons","confluence");
  if(Array.isArray(ev)) ev.forEach(x=>out.push(typeof x==="string"?x:pick(x,"type","name","label")));
  ["market_structure","liquidity","order_block","ob","fvg","volume"].forEach(k=>{if(raw[k])out.push(k)});
  return [...new Set(out.filter(Boolean))].slice(0,5);
}

function renderStats(){
  const active=state.setups.length, total=state.markets.length;
  $("#marketCount").textContent=total;
  $("#setupCount").textContent=active;
  $("#waitCount").textContent=Math.max(0,total-active);
}

function renderSetups(){
  const rows=state.setups.filter(s=>state.filter==="ALL"||s.horizon===state.filter);
  const root=$("#setups");
  if(!rows.length){
    root.innerHTML='<div class="no-setups"><div class="no-icon">∅</div><div><strong>NO ACTIVE SETUPS</strong><p>AICFA has no active LONG or SHORT setup in the latest market states.</p></div></div>';
    return;
  }
  root.innerHTML=rows.map(s=>{
    const d=s.direction.toLowerCase(), t=tags(s);
    return '<article class="setup '+d+'">'+
      '<div class="setup-top"><div><span class="ticker">'+esc(s.asset)+'</span><span class="horizon">'+esc(s.horizon)+'</span></div><span class="direction">'+esc(s.direction)+'</span></div>'+
      '<div class="scenario">ACTIVE MARKET SETUP <span>'+age(s.timestamp)+' AGO</span></div>'+
      '<div class="levels"><div><label>ENTRY</label><b>'+esc(s.entry)+'</b></div><div><label>INVALIDATION</label><b>'+esc(s.invalidation)+'</b></div><div><label>TARGET</label><b>'+esc(s.target)+'</b></div><div><label>RR</label><b>'+esc(s.rr)+'</b></div></div>'+
      '<div class="tags">'+t.map(x=>'<span>'+esc(String(x).replaceAll("_"," ").toUpperCase())+'</span>').join("")+'</div>'+
    '</article>';
  }).join("");
}

function renderActivity(){
  const root=$("#activity");
  const scans=state.scans.slice().reverse().slice(0,12);
  $("#activityCount").textContent=scans.length+" SCANS";
  if(!scans.length){root.innerHTML='<div class="quiet">No scanner activity received.</div>';return;}
  root.innerHTML=scans.map(e=>{
    const ms=e.payload?.markets||[];
    const m=ms[0], setups=m?.setups||[], d=m?.diagnostics||{};
    const status=String(d.status||"completed").toUpperCase();
    return '<div class="activity-row"><time>'+esc(fmt(e.timestamp_ms))+'</time><strong>'+esc(m?.asset||"MARKET")+'</strong><span class="scan-status '+status.toLowerCase()+'">'+esc(status)+'</span><span>'+setups.length+' setup'+(setups.length===1?"":"s")+'</span><small>scan #'+esc(e.payload?.scan_number)+'</small></div>';
  }).join("");
}

async function refresh(){
  try{
    const [health,scanData]=await Promise.all([get("/health"),get("/journal/scans?limit=500")]);
    const current=currentState(scanData);
    state.markets=current.markets; state.setups=current.setups; state.scans=scanData.events||[];
    $("#status").className="live"; $("#statusText").textContent="LIVE";
    $("#updated").textContent="UPDATED "+new Date().toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});
    $("#dataState").textContent=health.ok?"HEALTHY":"DEGRADED";
    renderStats(); renderSetups(); renderActivity();
  }catch(_){
    $("#status").className="bad"; $("#statusText").textContent="OFFLINE"; $("#dataState").textContent="UNAVAILABLE";
  }
}

function beep(){
  try{const C=window.AudioContext||window.webkitAudioContext,c=new C(),o=c.createOscillator(),g=c.createGain();o.frequency.value=760;g.gain.setValueAtTime(.0001,c.currentTime);g.gain.exponentialRampToValueAtTime(.045,c.currentTime+.02);g.gain.exponentialRampToValueAtTime(.0001,c.currentTime+.18);o.connect(g).connect(c.destination);o.start();o.stop(c.currentTime+.2)}catch(_){}
}

$("#filters").addEventListener("click",e=>{const f=e.target.dataset.filter;if(!f)return;document.querySelectorAll("#filters button").forEach(b=>b.classList.remove("active"));e.target.classList.add("active");state.filter=f;renderSetups()});
$("#soundBtn").addEventListener("click",()=>{state.sound=!state.sound;$("#soundBtn").textContent=state.sound?"SOUND ON":"SOUND OFF";$("#soundBtn").classList.toggle("on",state.sound);if(state.sound)beep()});
refresh(); setInterval(refresh,15000);
