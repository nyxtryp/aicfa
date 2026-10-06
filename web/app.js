const API_BASE = window.AICFA_FEED_URL || "/api";
const state = { setups: [], events: [], filter: "ALL", known: new Set(), sound: false };

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "—").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));

function fmtTime(ms){ if(!ms) return "—"; const d=new Date(Number(ms)); return d.toLocaleString([], {month:"short",day:"2-digit",hour:"2-digit",minute:"2-digit"}); }
function age(ms){ if(!ms) return "—"; const n=Math.max(0,Date.now()-Number(ms)); if(n<60000)return "NOW"; if(n<3600000)return Math.floor(n/60000)+"M AGO"; if(n<86400000)return Math.floor(n/3600000)+"H AGO"; return Math.floor(n/86400000)+"D AGO"; }
function pick(o,...keys){ for(const k of keys){ if(o && o[k]!==undefined && o[k]!==null) return o[k]; } return undefined; }

async function get(path){
  const r=await fetch(API_BASE+path,{cache:"no-store"});
  if(!r.ok) throw new Error("HTTP "+r.status);
  return r.json();
}

function normalizeSetup(item){
  const s=item.setup||item;
  const asset=pick(item,"asset")||pick(s,"asset","symbol","market")||"UNKNOWN";
  const direction=String(pick(s,"direction","side","signal")||"WAIT").toUpperCase();
  const horizon=String(pick(s,"horizon","profile")||"—").toUpperCase();
  const entry=pick(s,"entry","entry_price","entry_zone");
  const sl=pick(s,"sl","stop_loss","invalidation");
  const tp=pick(s,"tp","tp1","target");
  const rr=pick(s,"rr","risk_reward");
  const lifecycle=String(pick(s,"lifecycle","status")||"ACTIVE").toUpperCase();
  const evidence=pick(s,"evidence","reasons","confluence")||[];
  return {raw:s,asset,direction,horizon,entry,sl,tp,rr,lifecycle,evidence,timestamp:item.timestamp_ms||pick(s,"timestamp_ms","created_at")};
}

function evidenceTags(s){
  const out=[];
  const raw=s.evidence;
  if(Array.isArray(raw)) raw.forEach(x=>out.push(typeof x==="string"?x:pick(x,"type","name","label")));
  else if(raw && typeof raw==="object") Object.keys(raw).forEach(k=>{if(raw[k])out.push(k)});
  ["market_structure","liquidity","order_block","ob","fvg","volume"].forEach(k=>{if(s.raw?.[k] && !out.includes(k))out.push(k)});
  return [...new Set(out.filter(Boolean))].slice(0,6);
}

function renderSetups(){
  const root=$("#setups");
  const rows=state.setups.filter(s=>state.filter==="ALL" || s.horizon===state.filter);
  if(!rows.length){ root.innerHTML='<div class="empty"><p>No matching setup is currently in the central feed.</p><p style="color:#596474">WAIT / NO TRADE is a valid AICFA state.</p></div>'; return; }
  root.innerHTML=rows.slice(0,30).map((s,i)=>{
    const d=s.direction.toLowerCase();
    const tags=evidenceTags(s);
    return '<article class="card '+d+(i<3?' new':'')+'"><div class="card-top"><div class="asset">'+esc(s.asset)+'</div><div class="dir '+d+'">'+esc(s.direction)+'</div></div>'+
      '<div class="meta"><span>'+esc(s.horizon)+'</span><span class="life">'+esc(s.lifecycle)+'</span></div>'+
      '<div class="levels"><div><span>ENTRY</span><b>'+esc(s.entry)+'</b></div><div><span>SL</span><b>'+esc(s.sl)+'</b></div><div><span>TP</span><b>'+esc(s.tp)+'</b></div><div><span>RR</span><b>'+esc(s.rr)+'</b></div></div>'+
      '<div class="evidence">'+tags.map(t=>'<span class="tag">'+esc(String(t).replaceAll("_"," ").toUpperCase())+'</span>').join("")+'<span class="fresh">'+age(s.timestamp)+'</span></div></article>';
  }).join("");
}

function renderEvents(){
  const root=$("#events"); $("#eventCount").textContent=state.events.length+" EVENTS";
  if(!state.events.length){root.innerHTML='<div class="empty"><p>No journal events received yet.</p></div>';return;}
  root.innerHTML=state.events.slice(0,30).map(e=>{
    const p=e.payload||{}; const asset=pick(p,"asset","symbol","market")||pick(e,"asset")||"MARKET";
    const type=String(e.event_type||"EVENT").replaceAll("_"," ").toUpperCase();
    return '<div class="event"><time>'+esc(fmtTime(e.timestamp_ms))+'</time><span class="event-type">'+esc(type)+'</span><span class="event-main"><b>'+esc(asset)+'</b> '+esc(p.message||p.status||"journal update")+'</span><span class="event-life">'+esc(p.lifecycle||"")+'</span></div>';
  }).join("");
}

async function refresh(){
  try{
    const [health,setupData,eventData]=await Promise.all([
      get("/health"), get("/journal/setups?limit=100"), get("/journal/events?limit=100")
    ]);
    const setups=(setupData.setups||[]).map(normalizeSetup);
    const freshIds=new Set(setups.map(s=>JSON.stringify([s.asset,s.direction,s.horizon,s.entry,s.timestamp])));
    let hasNew=false;
    freshIds.forEach(id=>{if(!state.known.has(id)&&state.known.size)hasNew=true;});
    state.known=freshIds; state.setups=setups; state.events=eventData.events||[];
    $("#statusDot").parentElement.className="status live";
    $("#statusText").textContent="LIVE";
    $("#updated").textContent="UPDATED "+new Date().toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});
    $("#dataState").textContent=health.ok?"HEALTHY":"DEGRADED";
    renderSetups(); renderEvents();
    if(hasNew && state.sound) beep();
  }catch(err){
    $("#statusDot").parentElement.className="status bad";
    $("#statusText").textContent="OFFLINE";
    $("#dataState").textContent="UNAVAILABLE";
  }
}

function beep(){
  try{ const C=window.AudioContext||window.webkitAudioContext; const c=new C(),o=c.createOscillator(),g=c.createGain(); o.frequency.value=880;o.type="sine";g.gain.setValueAtTime(.0001,c.currentTime);g.gain.exponentialRampToValueAtTime(.05,c.currentTime+.02);g.gain.exponentialRampToValueAtTime(.0001,c.currentTime+.22);o.connect(g).connect(c.destination);o.start();o.stop(c.currentTime+.24); }catch(_){}
}

$("#filters").addEventListener("click",e=>{if(e.target.dataset.filter){document.querySelectorAll("#filters button").forEach(b=>b.classList.remove("active"));e.target.classList.add("active");state.filter=e.target.dataset.filter;renderSetups();}});
$("#soundBtn").addEventListener("click",()=>{state.sound=!state.sound;$("#soundBtn").classList.toggle("on",state.sound);$("#soundBtn").textContent=state.sound?"SOUND ON":"SOUND OFF";$("#soundBtn").setAttribute("aria-pressed",String(state.sound));if(state.sound)beep();});
refresh(); setInterval(refresh,15000);
