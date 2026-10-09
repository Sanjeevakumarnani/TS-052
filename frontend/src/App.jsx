import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { Activity, AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, BarChart3, Check, ChevronDown, CircleHelp, ClipboardList, Download, ExternalLink, FileText, Filter, Gauge, GitCompareArrows, Layers3, LogIn, LogOut, Map as MapIcon, MapPinned, Menu, RefreshCw, Route, Search, Settings2, Shield, ShieldCheck, SlidersHorizontal, Target, Upload, User, Users, X, Zap } from 'lucide-react';
import {
  AuthPage,
  LocationVerifyPage,
  ResidentDashboard,
  AdminImportConsole,
  AdminReviewConsole,
  VerificationSummaryPage,
} from './VerificationWorkflow.jsx';

const API = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const DIMENSIONS = [
  {key:'digital', label:'Digital connectivity', short:'Digital', weight:25},
  {key:'electricity', label:'Electricity reliability', short:'Electricity', weight:20},
  {key:'roads', label:'Road accessibility', short:'Roads', weight:20},
  {key:'public_digital', label:'Public digital infrastructure', short:'Public digital', weight:15},
  {key:'essential_services', label:'Essential-service access', short:'Essential services', weight:20},
];

async function api(path, options={}) {
  const res = await fetch(`${API}${path}`, options);
  const type = res.headers.get('content-type') || '';
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { const d = type.includes('json') ? await res.json() : await res.text(); msg = d.detail || d.message || msg; } catch {}
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return type.includes('json') ? res.json() : res;
}
function scoreClass(score){ if(score==null) return 'unknown'; if(score>=80) return 'excellent'; if(score>=60) return 'good'; if(score>=40) return 'warning'; return 'critical'; }
function fmt(n, digits=0){ return n==null || Number.isNaN(Number(n)) ? '—' : Number(n).toFixed(digits); }
function rankClass(label){return String(label||'').toLowerCase();}
function BrandLogo(){
 return <div className="brand-logo" aria-hidden="true">
  <svg viewBox="0 0 44 44" role="presentation">
   <defs><linearGradient id="brand-gradient" x1="4" y1="40" x2="40" y2="4" gradientUnits="userSpaceOnUse"><stop stopColor="#244735"/><stop offset="1" stopColor="#70a47d"/></linearGradient></defs>
   <rect x="1" y="1" width="42" height="42" rx="12" fill="url(#brand-gradient)"/>
   <path d="M9 33h26" fill="none" stroke="#d9f1dd" strokeWidth="2" strokeLinecap="round"/>
   <path d="M11 32V22l5-4 5 4v10M21 32V17l5-4 5 4v15" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"/>
   <path d="M9 27h4M18 24h4M28 22h5" fill="none" stroke="#d9f1dd" strokeWidth="1.8" strokeLinecap="round"/>
   <path d="M27 9v7M23.5 12.5h7" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round"/>
   <path d="m9 36 5-3 5 2 6-5 4 1 6-6" fill="none" stroke="#b7e7c2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
 </div>
}
function useVillageData(){
  const [villages,setVillages]=useState([]), [summary,setSummary]=useState(null), [methodology,setMethodology]=useState(null), [sources,setSources]=useState([]), [loading,setLoading]=useState(true), [error,setError]=useState('');
  const refresh=useCallback(async()=>{
    setLoading(true); setError('');
    try { const [v,s,m,src]=await Promise.all([api('/api/v1/villages?limit=1000&sort=priority&order=desc'),api('/api/v1/summary'),api('/api/v1/methodology'),api('/api/v1/sources')]);
      setVillages(v.items||[]); setSummary(s); setMethodology(m); setSources(src.sources||[]);
    } catch(e){setError(`${e.message}. Start the API server using the instructions in README.md.`)} finally {setLoading(false)}
  },[]);
  useEffect(()=>{refresh()},[refresh]);
  return {villages,summary,methodology,sources,loading,error,refresh};
}
function Sidebar({page,setPage,open,setOpen,user,onLogout}){
 const isAdmin = user?.role === 'admin';
 const isResident = user && user.role !== 'admin';

 // Navigation visible strictly by role:
 // - Admin sees full suite: Overview, Map explorer, Rankings, Scenario lab, Methodology, Dev Import, Review queue, Verification summary
 // - Non-admin logged in user (Resident/Citizen) sees ONLY their feedback portal: My Feedback, Verify Location
 // - Unauthenticated sees Public analytics + Login button
 const adminNav = [
   {id:'overview',label:'Overview',icon:BarChart3},
   {id:'map',label:'Map explorer',icon:MapPinned},
   {id:'rankings',label:'Priority ranking',icon:Target},
   {id:'scenario',label:'Scenario lab',icon:GitCompareArrows},
   {id:'methodology',label:'Methodology & data',icon:FileText},
   {id:'admin-review',label:'Review queue',icon:Shield},
   {id:'admin-import',label:'Dev. import',icon:Upload},
   {id:'admin-summary',label:'Verification summary',icon:BarChart3},
 ];

 const residentNav = [
   {id:'my-dashboard',label:'Submit Feedback',icon:ClipboardList},
   {id:'my-village',label:'Verify Location',icon:MapPinned},
 ];

 // No options until admin logs in
 const unauthNav = [
   {id:'auth',label:'Admin Sign In',icon:LogIn},
 ];

 const nav = isAdmin ? adminNav : isResident ? residentNav : unauthNav;

 return <aside className={`sidebar ${open?'sidebar-open':''}`}>
  <div className="brand"><BrandLogo/><div><div className="brand-name">InfraPulse</div><div className="brand-sub">{isAdmin ? "ADMIN CONSOLE" : "RELIABILITY INTELLIGENCE"}</div></div><button className="icon-btn sidebar-close" onClick={()=>setOpen(false)} aria-label="Close menu"><X size={18}/></button></div>
  <div className="workspace-label">{isAdmin ? "ADMIN WORKSPACE" : !user ? "AUTHENTICATION" : "WORKSPACE"}</div>
  <nav>{nav.map(n=><button key={n.id} className={`nav-item ${page===n.id?'active':''}`} onClick={()=>{setPage(n.id);setOpen(false)}}><n.icon size={18}/><span>{n.label}</span>{n.id==='rankings'&&<span className="nav-count">!</span>}</button>)}</nav>
  {user && <div style={{padding:'8px 16px',borderTop:'1px solid #eee',marginTop:'auto'}}>
    <div style={{display:'flex',alignItems:'center',gap:8,padding:'8px 0'}}>
      <User size={15}/><span style={{fontSize:13,flex:1}}><b>{user.display_name||user.username}</b><br/><small style={{opacity:0.65}}>{user.role}</small></span>
      <button className="icon-btn" onClick={onLogout} aria-label="Log out" title="Log out"><LogOut size={15}/></button>
    </div>
  </div>}
  <div className="sidebar-bottom"><div className="version-icon"><ShieldCheck size={18}/></div><div><b>Prototype environment</b><span>Demo records · v1 methodology</span></div><span className="status-dot"/></div>
 </aside>
}
function Header({title,subtitle,onMenu,onExport,loading,user}){
  const isAdmin = user?.role === 'admin';
  return <header className="topbar">
    <button className="icon-btn mobile-menu" onClick={onMenu} aria-label="Open menu"><Menu size={20}/></button>
    <div>
      <div className="breadcrumbs">INFRAPULSE <span>/</span> {title.toUpperCase()}</div>
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </div>
    <div className="top-actions">
      {isAdmin && <div className="data-pill"><span className="status-dot"/> Synthetic demo data</div>}
      {isAdmin && <button className="btn btn-secondary" onClick={onExport}><Download size={16}/> Export CSV</button>}
      <button className="icon-btn" onClick={loading} aria-label="Refresh data"><RefreshCw size={17}/></button>
    </div>
  </header>;
}
function Notice({children,kind='info'}){return <div className={`notice notice-${kind}`}><AlertTriangle size={16}/><span>{children}</span></div>}
function ScorePill({score,label}){const c=scoreClass(score); return <span className={`score-pill ${c}`}><span className="mini-dot"/>{label|| (score==null?'No score':`${fmt(score)}/100`)}</span>}
function PriorityPill({label}){return <span className={`priority-pill ${rankClass(label)}`}>{label||'Unranked'}</span>}
function StatCard({label,value,sub,icon:Icon,trend}){return <div className="stat-card"><div className="stat-top"><span>{label}</span><div className="stat-icon"><Icon size={17}/></div></div><div className="stat-value">{value}</div><div className="stat-sub">{trend&&<span className="stat-trend"><ArrowUpRight size={13}/></span>}{sub}</div></div>}
function DimensionBars({summary}){return <div className="dimension-bars">{DIMENSIONS.map(d=>{const val=summary?.dimension_averages?.[d.key]?.average;return <div className="dim-row" key={d.key}><div className="dim-row-label">{d.label}<span>{fmt(val)}/100</span></div><div className="bar-track"><div className={`bar-fill ${scoreClass(val)}`} style={{width:`${val||0}%`}}/></div></div>})}</div>}
function VillageMap({villages,onSelect,selectedId,large=false}){
 const center=[17.7,79.1];
 const [mapError, setMapError] = useState(false);
 if (mapError) {
   return <div className={`map-shell ${large?'map-large':''}`}>
     <div className="map-fallback" role="alert">Map tiles unavailable. Use the village table below to browse records.</div>
   </div>;
 }
 return <div className={`map-shell ${large?'map-large':''}`}>
  <MapContainer center={center} zoom={7} scrollWheelZoom={true} style={{height:'100%',width:'100%'}}>
   <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" eventHandlers={{tileerror: () => setMapError(true)}} />
   {villages.filter(v=>Number.isFinite(v.latitude)&&Number.isFinite(v.longitude)).map(v=>{
    const score=v.score?.overall; const c=scoreClass(score); return <CircleMarker key={v.id} center={[v.latitude,v.longitude]} radius={selectedId===v.id?10:7} pathOptions={{color:'#fff',weight:2,fillColor:({critical:'#b63e35',warning:'#c18a30',good:'#64816b',excellent:'#303b36',unknown:'#777'}[c]),fillOpacity:.9}} eventHandlers={{click:()=>onSelect(v)}}>
     <Popup><div className="map-popup"><b>{v.name}</b><span>{v.district} district</span><strong>{fmt(score)}/100 · {v.score?.category?.label}</strong><button onClick={()=>onSelect(v)}>Open profile →</button><small>SIMULATED DEMO RECORD</small></div></Popup>
    </CircleMarker>
   })}
  </MapContainer>
  <div className="map-disclaimer">Illustrative pins · not official village boundaries</div>
 </div>
}
function VillageTable({villages,onSelect,compact=false}){return <div className="table-wrap"><table><thead><tr><th scope="col">Village</th><th scope="col">Reliability</th><th scope="col">Priority</th><th scope="col">Population</th><th scope="col"></th></tr></thead><tbody>{villages.map(v=><tr key={v.id}><td><button className="table-village" onClick={()=>onSelect(v)}><span className="village-avatar">{v.name.replace('Demo Village ','').slice(0,1)}</span><span><b>{v.name}</b><small>{v.district} · {v.id}</small></span></button></td><td><ScorePill score={v.score?.overall}/></td><td><PriorityPill label={v.priority?.label}/></td><td>{Number(v.population?.value||0).toLocaleString('en-IN')}</td><td><button className="row-arrow" onClick={()=>onSelect(v)} aria-label={`Open ${v.name}`}><ArrowRight size={16}/></button></td></tr>)}</tbody></table>{villages.length===0&&<div className="empty-state">No villages match these filters.</div>}</div>}
function FilterBar({query,setQuery,category,setCategory,district,setDistrict,villages}){const districts=useMemo(()=>[...new Set(villages.map(v=>v.district))].sort(),[villages]);return <div className="filter-bar"><div className="searchbox"><Search size={16}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search village or district…" aria-label="Search village or district"/>{query&&<button onClick={()=>setQuery('')} aria-label="Clear search"><X size={14}/></button>}</div><label className="select-wrap"><Filter size={15}/><select value={category} onChange={e=>setCategory(e.target.value)} aria-label="Filter reliability category"><option value="all">All reliability levels</option><option value="critical">Critical</option><option value="vulnerable">Vulnerable</option><option value="adequate">Adequate</option><option value="highly_reliable">Highly reliable</option></select><ChevronDown size={14}/></label><label className="select-wrap"><MapIcon size={15}/><select value={district} onChange={e=>setDistrict(e.target.value)} aria-label="Filter district"><option value="all">All districts</option>{districts.map(d=><option key={d} value={d}>{d}</option>)}</select><ChevronDown size={14}/></label></div>}
function VillageModal({village,onClose}){if(!village)return null;const c=village.score?.components||{};return <div className="modal-backdrop" role="presentation" onClick={onClose}><div className="profile-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" onClick={e=>e.stopPropagation()}><div className="modal-head"><div><div className="eyebrow">VILLAGE PROFILE · {village.id}</div><h2 id="modal-title">{village.name}</h2><p>{village.district}, {village.state}</p></div><button className="icon-btn" onClick={onClose} aria-label="Close profile"><X size={20}/></button></div>
 <Notice>All measurements in this prototype are synthetic demo values. Map pins are illustrative, not verified local observations.</Notice>
 <div className="profile-score-row"><div className="big-score"><strong>{fmt(village.score?.overall,1)}</strong><span>/100 reliability score</span></div><ScorePill score={village.score?.overall} label={village.score?.category?.label}/><PriorityPill label={`${village.priority?.label} priority`}/><span className="coverage-note">{fmt(village.score?.coverage_percent)}% data coverage</span></div>
 <div className="profile-grid"><section className="profile-section"><h3>Dimension scores</h3>{DIMENSIONS.map(d=><div className="profile-dim" key={d.key}><div><span>{d.label}</span><b>{fmt(c[d.key])}</b></div><div className="bar-track"><div className={`bar-fill ${scoreClass(c[d.key])}`} style={{width:`${c[d.key]||0}%`}}/></div></div>)}</section><section className="profile-section"><h3>Priority explanation</h3><p className="muted">Prototype priority score: <b>{fmt(village.priority?.score,1)}/100</b></p>{Object.entries(village.priority?.factors||{}).sort((a,b)=>b[1]-a[1]).map(([k,val])=><div className="factor-row" key={k}><span>{k.replaceAll('_',' ')}</span><b>{fmt(val)}</b></div>)}<p className="tiny-note">Heuristic ranking, not an official allocation rule.</p></section></div>
 {village.gaps?.length>0&&<section className="gap-section"><h3>Availability–reliability gaps</h3>{village.gaps.map(g=><div className="gap-row" key={g.dimension}><span>{g.label}</span><span>Availability <b>{fmt(g.availability)}</b></span><span>Reliability <b>{fmt(g.reliability)}</b></span><strong className={g.gap_points>=20?'gap-high':''}>+{fmt(g.gap_points)} pts</strong></div>)}</section>}
 <div className="modal-foot"><span>Source: {village.source_name||'not supplied'} · {village.source_date||'date not supplied'}</span><button className="btn btn-secondary" onClick={onClose}>Close profile</button></div>
 </div></div>}
function Overview({villages,summary,onSelect,setPage}){const top=[...villages].sort((a,b)=>(b.priority?.score||0)-(a.priority?.score||0)).slice(0,5);return <>
 <div className="stats-grid"><StatCard label="Villages assessed" value={summary?.total_villages??'—'} sub="Illustrative demo records" icon={MapPinned}/><StatCard label="Average reliability" value={summary?.average_reliability==null?'—':`${summary.average_reliability}/100`} sub="Weighted component score" icon={Gauge}/><StatCard label="High priority" value={summary?.high_priority_count??'—'} sub="Ranked for review" icon={Target}/><StatCard label="Large digital gaps" value={summary?.large_gap_count??'—'} sub="Gap ≥ 20 points" icon={Activity}/></div>
 <div className="dashboard-grid"><section className="panel map-panel"><div className="panel-head"><div><div className="eyebrow">GEOSPATIAL OVERVIEW</div><h2>Infrastructure reliability map</h2><p>Explore village-level reliability and underserved areas.</p></div><button className="text-button" onClick={()=>setPage('map')}>Open map <ArrowRight size={15}/></button></div><VillageMap villages={villages} onSelect={onSelect}/><div className="map-legend"><span><i className="legend-dot critical"/> Critical</span><span><i className="legend-dot warning"/> Vulnerable</span><span><i className="legend-dot good"/> Adequate</span><span><i className="legend-dot excellent"/> Highly reliable</span></div></section>
 <section className="panel priority-panel"><div className="panel-head"><div><div className="eyebrow">ACTION PRIORITY</div><h2>Villages to review</h2><p>Ranked with visible decision factors.</p></div><button className="icon-btn" onClick={()=>setPage('rankings')} aria-label="View rankings"><ArrowRight size={17}/></button></div><div className="priority-list">{top.map((v,i)=><button key={v.id} className="priority-item" onClick={()=>onSelect(v)}><span className="priority-number">{String(i+1).padStart(2,'0')}</span><span className="priority-item-main"><b>{v.name}</b><small>{v.district} · {fmt(v.score?.overall)}/100 reliability</small><span className="priority-track"><i style={{width:`${v.priority.score}%`}}/></span></span><PriorityPill label={v.priority.label}/><ArrowRight size={14} className="muted-icon"/></button>)}</div><div className="panel-bottom-note"><CircleHelp size={15}/> Priority scores are transparent prototype heuristics.</div></section></div>
 <div className="panel dimension-panel"><div className="panel-head"><div><div className="eyebrow">SYSTEM-WIDE VIEW</div><h2>Average performance by dimension</h2><p>Weighted averages across the current sample.</p></div><button className="text-button" onClick={()=>setPage('methodology')}>View methodology <ArrowRight size={15}/></button></div><DimensionBars summary={summary}/></div>
 </>}
function MapPage({villages,onSelect,query,setQuery,category,setCategory,district,setDistrict}){return <><FilterBar query={query} setQuery={setQuery} category={category} setCategory={setCategory} district={district} setDistrict={setDistrict} villages={villages}/><div className="panel map-explorer-panel"><div className="panel-head"><div><div className="eyebrow">MAP EXPLORER</div><h2>Village reliability across dimensions</h2><p>{villages.length} villages match current filters.</p></div><div className="map-stat"><span>Visible villages</span><b>{villages.length}</b></div></div><VillageMap villages={villages} onSelect={onSelect} large/><div className="map-legend"><span><i className="legend-dot critical"/> Critical</span><span><i className="legend-dot warning"/> Vulnerable</span><span><i className="legend-dot good"/> Adequate</span><span><i className="legend-dot excellent"/> Highly reliable</span><span className="legend-note">Open a marker for its profile.</span></div></div><section className="panel table-panel"><div className="panel-head"><div><h2>Village records</h2><p>All records carry demo-data provenance labels.</p></div></div><VillageTable villages={villages} onSelect={onSelect}/></section></>}
function RankingsPage({villages,onSelect}){const sorted=[...villages].sort((a,b)=>b.priority.score-a.priority.score);return <><div className="page-intro"><div><div className="eyebrow">DECISION SUPPORT</div><h2>Priority ranking</h2><p>Compare infrastructure deficit, population impact, criticality and alternatives.</p></div><div className="score-explainer"><b>Priority score</b><span>35% deficit · 25% population · 25% criticality · 15% lack of alternatives</span></div></div><div className="panel table-panel"><div className="table-heading"><div><h3>Ranked villages</h3><p>Higher score = higher review priority in this prototype.</p></div><span className="count-pill">{sorted.length} records</span></div><div className="table-wrap"><table><thead><tr><th scope="col">Rank</th><th scope="col">Village</th><th scope="col">Reliability</th><th scope="col">Priority score</th><th scope="col">Top contributing factor</th><th scope="col"></th></tr></thead><tbody>{sorted.map((v,i)=>{const why=Object.entries(v.priority.factors).sort((a,b)=>b[1]-a[1])[0]?.[0]||'—';return <tr key={v.id}><td><span className="rank-num">{String(i+1).padStart(2,'0')}</span></td><td><button className="table-village" onClick={()=>onSelect(v)}><span><b>{v.name}</b><small>{v.district} · {v.id}</small></span></button></td><td><ScorePill score={v.score.overall}/></td><td><div className="priority-score-cell"><b>{fmt(v.priority.score,1)}</b><span className="priority-track"><i style={{width:`${v.priority.score}%`}}/></span></div></td><td className="factor-text">{why.replaceAll('_',' ')}</td><td><button className="row-arrow" onClick={()=>onSelect(v)} aria-label={`Open ${v.name}`}><ArrowRight size={16}/></button></td></tr>})}</tbody></table></div></div><Notice>Priority rankings are an explainable decision-support heuristic, not official government investment decisions. Field validation is required before operational use.</Notice></>}
function ScenarioPage({villages,onSelect}){const [id,setId]=useState(villages[0]?.id||'');const [dimension,setDimension]=useState('roads');const [value,setValue]=useState(70);const [cost,setCost]=useState('');const [assumptions,setAssumptions]=useState('Illustrative intervention; score change is a model calculation, not a measured outcome.');const [result,setResult]=useState(null);const [busy,setBusy]=useState(false);const [error,setError]=useState('');useEffect(()=>{if(!villages.some(v=>v.id===id)&&villages.length)setId(villages[0].id)},[villages,id]);const village=villages.find(v=>v.id===id);useEffect(()=>{if(village){setValue(village.score?.components?.[dimension]??50);setResult(null)}},[id,dimension]);const run=async()=>{setBusy(true);setError('');try{let payload={village_id:id,overrides:{[dimension]:Number(value)},assumptions};if(cost!=='')payload.estimated_cost=Number(cost);const r=await api('/api/v1/scenarios',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});setResult(r)}catch(e){setError(e.message)}finally{setBusy(false)}};return <><div className="page-intro"><div><div className="eyebrow">COMPARE BEFORE ACTING</div><h2>Intervention scenario lab</h2><p>Test a hypothetical improvement and compare it with the current baseline.</p></div><div className="scenario-note"><GitCompareArrows size={18}/><span>Scenario values never overwrite source observations.</span></div></div><div className="scenario-layout"><section className="panel scenario-controls"><div className="panel-head"><div><h3>Configure scenario</h3><p>Set one intervention assumption at a time for a clear comparison.</p></div><Settings2 size={18}/></div><label className="field-label">Village<select className="field-control" value={id} onChange={e=>{setId(e.target.value);setResult(null)}}>{villages.map(v=><option key={v.id} value={v.id}>{v.name} — {v.district}</option>)}</select></label><label className="field-label">Infrastructure dimension<select className="field-control" value={dimension} onChange={e=>setDimension(e.target.value)}>{DIMENSIONS.map(d=><option key={d.key} value={d.key}>{d.label}</option>)}</select></label><div className="range-head"><label className="field-label" htmlFor="scenario-score">Assumed post-intervention score</label><strong>{value}/100</strong></div><input id="scenario-score" className="range" type="range" min="0" max="100" value={value} onChange={e=>{setValue(Number(e.target.value));setResult(null)}}/><div className="range-labels"><span>0 · critical</span><span>100 · reliable</span></div><label className="field-label">Estimated cost (optional)<div className="input-prefix"><span>₹</span><input className="field-control" type="number" min="0" value={cost} onChange={e=>{setCost(e.target.value);setResult(null)}} placeholder="Enter hypothetical budget"/></div></label><label className="field-label">Assumptions<textarea className="field-control text-control" value={assumptions} onChange={e=>{setAssumptions(e.target.value);setResult(null)}} maxLength={1000}/></label><button className="btn btn-primary btn-wide" onClick={run} disabled={!village||busy}><GitCompareArrows size={16}/>{busy?'Calculating…':'Calculate scenario'}</button>{error&&<div className="inline-error">{error}</div>}<p className="tiny-note">This estimates the effect of changing a score in the weighting model. It does not estimate causal real-world impact.</p></section>
 <section className="panel scenario-results"><div className="panel-head"><div><div className="eyebrow">SCENARIO OUTPUT</div><h3>{village?.name||'Select a village'}</h3><p>{village?.district||''} · Baseline vs user-defined scenario</p></div><span className="simulated-tag">SIMULATED</span></div>{result?<><div className="comparison-cards"><div className="compare-card"><span>Current baseline</span><strong>{fmt(result.baseline.score,1)}<small>/100</small></strong><ScorePill score={result.baseline.score} label={result.baseline.category?.label}/></div><div className="compare-arrow"><ArrowRight size={22}/></div><div className="compare-card scenario-card"><span>Scenario result</span><strong>{fmt(result.scenario.score,1)}<small>/100</small></strong><ScorePill score={result.scenario.score} label={result.scenario.category?.label}/></div></div><div className="delta-box"><div><span>Calculated score change</span><b>{result.delta_points>0?'+':''}{fmt(result.delta_points,1)} points</b></div><div className="delta-bar"><div className="delta-before" style={{width:`${result.baseline.score||0}%`}}/><div className="delta-after" style={{width:`${result.scenario.score||0}%`}}/></div><small>Baseline shown in gray; scenario shown in black.</small></div><div className="result-details"><div><span>Selected change</span><b>{DIMENSIONS.find(d=>d.key===dimension)?.label}: {value}/100</b></div><div><span>Priority score</span><b>{fmt(result.baseline.priority.score,1)} → {fmt(result.scenario.priority.score,1)}</b></div>{cost!==''&&<div><span>Improvement per cost unit</span><b>{result.improvement_per_cost_unit==null?'—':result.improvement_per_cost_unit}</b></div>}</div><Notice>{result.notice}</Notice><button className="btn btn-secondary" onClick={()=>onSelect(village)}>Open village profile <ArrowRight size={15}/></button></>:<div className="scenario-empty"><div className="empty-icon"><GitCompareArrows size={24}/></div><h3>Run a scenario to compare outcomes</h3><p>Choose a village, set a potential post-intervention dimension score, then calculate how the weighted reliability score changes.</p><div className="mini-preview"><div><span>Baseline</span><i style={{width:`${village?.score?.overall||0}%`}}/></div><div><span>Assumed dimension</span><i style={{width:`${value}%`}}/></div></div></div>}</section></div></>}
function MethodologyPage({methodology,sources}){const weights=methodology?.weights||{};return <><div className="page-intro"><div><div className="eyebrow">TRANSPARENCY BY DESIGN</div><h2>Methodology & data</h2><p>Review how the prototype calculates results and where its evidence comes from.</p></div><span className="version-pill">Methodology {methodology?.version||'v1'}</span></div><Notice>All seeded village metrics are synthetic demonstration values. They do not indicate actual conditions in the named districts.</Notice><div className="method-grid"><section className="panel"><div className="panel-head"><div><h3>Reliability score</h3><p>Weighted average of available component scores.</p></div><Gauge size={18}/></div><div className="formula-block">Overall score = Σ (component score × dimension weight) ÷ sum of valid weights</div>{DIMENSIONS.map(d=><div className="weight-row" key={d.key}><span>{d.label}</span><b>{Math.round((weights[d.key]||0)*100)}%</b></div>)}<p className="tiny-note">At least 60% weighted-dimension coverage is required for an overall score. Missing dimensions are not silently treated as zero.</p></section><section className="panel"><div className="panel-head"><div><h3>Prototype categories</h3><p>Configurable thresholds, not official standards.</p></div><Layers3 size={18}/></div>{[{s:'80–100',l:'Highly reliable',c:'excellent'},{s:'60–79',l:'Adequate',c:'good'},{s:'40–59',l:'Vulnerable',c:'warning'},{s:'0–39',l:'Critical',c:'critical'}].map(x=><div className="category-row" key={x.l}><ScorePill score={{excellent:90,good:70,warning:50,critical:20}[x.c]} label={x.l}/><b>{x.s}</b></div>)}<div className="divider"/><h3>Data evidence types</h3><div className="evidence-list"><span><i className="evidence-dot sim"/> Simulated — seeded demo values</span><span><i className="evidence-dot upload"/> Uploaded — not independently verified</span><span><i className="evidence-dot verified"/> Verified — reserved for reviewed evidence</span></div></section></div><section className="panel limitations-panel"><h3>Limitations and responsible use</h3><ul>{(methodology?.limitations||[]).map(x=><li key={x}>{x}</li>)}</ul><ul><li>Availability/reliability gaps only make sense when indicators are comparable in scope, unit and time period.</li><li>Priority rankings support human review; they do not allocate public funds automatically.</li><li>Before operational use, replace demo values with verified data and calibrate scoring rules with infrastructure experts and local stakeholders.</li></ul></section></>}

function ReportStatusPage() {
  const [code, setCode] = useState('');
  const [statusData, setStatusData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLookup = async () => {
    if (!code.trim()) return;
    setLoading(true);
    setError('');
    setStatusData(null);
    try {
      const res = await api(`/api/v1/field-reports/status/${code.trim()}`);
      setStatusData(res);
    } catch (e) {
      setError(e.message || 'Report not found or error occurred.');
    } finally {
      setLoading(false);
    }
  };

  return <div className="report-lookup">
    <div className="panel">
      <div className="panel-head">
        <div>
          <div className="eyebrow">FIELD REPORTS</div>
          <h2>Lookup report status</h2>
          <p>Check the verification status of your submitted observation.</p>
        </div>
      </div>
      <label className="field-label" htmlFor="ref-code">Reference code</label>
      <input id="ref-code" type="text" value={code} onChange={e => setCode(e.target.value)} placeholder="Enter your opaque reference code" aria-label="Reference code" />
      <button className="btn btn-primary" onClick={handleLookup} disabled={loading || !code.trim()} style={{marginTop: '12px'}} aria-label="Look up status">
        <Search size={16} /> {loading ? 'Looking up...' : 'Look up status'}
      </button>
      {error && <div className="inline-error">{error}</div>}
      
      {statusData && (() => {
        const rep = statusData.report || statusData;
        return (
          <div className="report-status-card">
            <h3>Report details</h3>
            <p className="muted">Village ID: {rep.village_id} · Dimension: {DIMENSIONS.find(d => d.key === rep.dimension)?.label || rep.dimension} · Submitted: {rep.created_at ? new Date(rep.created_at).toLocaleString() : '—'}</p>
            <div style={{marginTop: '16px'}}>
              <PriorityPill label={rep.verification_status} />
            </div>
            <div style={{marginTop: '20px'}}>
              <h4>Status history</h4>
              {(rep.history || []).map((entry, i) => (
                <div key={i} className="report-history-row">
                  <div style={{minWidth: '120px'}}><span className="version-pill">{entry.changed_at ? new Date(entry.changed_at).toLocaleString() : '—'}</span></div>
                  <div>
                    <strong>{entry.status}</strong>
                    {entry.note && <div className="muted" style={{marginTop: '4px'}}>{entry.note}</div>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}
      <Notice>This lookup is private. Do not share your reference code.</Notice>
    </div>
  </div>;
}

function ImportPanel({onImported}){
  const [file,setFile]=useState(null);
  const [preview,setPreview]=useState(null);
  const [history,setHistory]=useState([]);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [historyLoading,setHistoryLoading]=useState(false);

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await api('/api/v1/imports/history');
      setHistory(res.items || res.imports || []);
    } catch(e) {}
    finally { setHistoryLoading(false); }
  }, []);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  const handlePreview = async () => {
    setBusy(true);setError('');setPreview(null);
    try{
      const form=new FormData();form.append('file',file);
      const r=await api('/api/v1/imports/csv/preview',{method:'POST',body:form});
      setPreview(r);
    }catch(e){setError(e.message)}finally{setBusy(false)}
  };

  const handleConfirm = async () => {
    setBusy(true);setError('');
    try{
      await api(`/api/v1/imports/csv/confirm?preview_token=${preview.preview_token}`,{method:'POST'});
      setPreview(null);
      setFile(null);
      await onImported();
      fetchHistory();
    }catch(e){setError(e.message)}finally{setBusy(false)}
  };

  const previewRows = preview?.preview || preview?.preview_rows || [];
  const rejectedCount = preview?.rejected_count ?? preview?.rejected?.length ?? 0;

  return <div className="import-panel" style={{flexDirection: 'column', alignItems: 'stretch'}}>
    <div style={{display: 'flex', alignItems: 'center', gap: '15px', flexWrap: 'wrap'}}>
      <div style={{flex:1, minWidth: '220px'}}>
        <h3><Upload size={17}/> Import a verified dataset</h3>
        <p>CSV must follow the schema documented in README.</p>
      </div>
      <input type="file" accept=".csv,text/csv" aria-label="Upload CSV file" onChange={e=>{setFile(e.target.files?.[0]||null);setPreview(null);setError('')}}/>
      <button className="btn btn-secondary" aria-label="Preview CSV" disabled={!file||busy} onClick={handlePreview}>{busy?'Loading…':'Preview CSV'}</button>
    </div>
    
    {error&&<span className="inline-error">{error}</span>}
    
    {preview&&<div className="preview-section" style={{marginTop: '15px'}}>
      <div className="import-result"><Check size={15}/> Preview ready: {preview.accepted_count} row(s) accepted, {rejectedCount} rejected.</div>
      {previewRows.length > 0 && (
        <table className="preview-table">
          <thead><tr><th scope="col">ID</th><th scope="col">Name</th><th scope="col">District</th><th scope="col">Overall Score</th></tr></thead>
          <tbody>
            {previewRows.map((r,i) => <tr key={i}><td>{r.id}</td><td>{r.name}</td><td>{r.district}</td><td>{fmt(r.overall_score ?? r.score?.overall, 1)}</td></tr>)}
          </tbody>
        </table>
      )}
      <button className="btn btn-primary" aria-label="Confirm import" onClick={handleConfirm} disabled={busy} style={{marginTop: '12px'}}>Confirm import</button>
    </div>}
    
    <div className="import-history">
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px'}}>
        <h4 style={{margin:0}}>Import history</h4>
        <button className="icon-btn" onClick={fetchHistory} aria-label="Refresh import history"><RefreshCw size={14}/></button>
      </div>
      {historyLoading ? <div className="muted">Loading history...</div> : history.length === 0 ? <div className="muted">No past imports found.</div> : (
        <table>
          <thead><tr><th scope="col">Filename</th><th scope="col">Accepted</th><th scope="col">Confirmed At</th></tr></thead>
          <tbody>
            {history.map(h => <tr key={h.id}><td>{h.filename}</td><td>{h.accepted_count}</td><td>{new Date(h.confirmed_at).toLocaleString()}</td></tr>)}
          </tbody>
        </table>
      )}
    </div>
  </div>
}

export default function App(){
  const {villages,summary,methodology,sources,loading,error,refresh}=useVillageData();
  const getInitialPage = () => {
    const token = localStorage.getItem('infrapulse_token');
    // If no token exists, always show the login screen first
    if (!token) return 'auth';

    const p = window.location.pathname.toLowerCase();
    const h = window.location.hash.toLowerCase();
    const s = new URLSearchParams(window.location.search);
    if (p.includes('/admin') || h.includes('admin') || s.get('page') === 'admin' || s.get('role') === 'admin') {
      return 'overview';
    }
    if (p.includes('/login') || p.includes('/auth') || h.includes('login') || h.includes('auth') || s.get('page') === 'auth') {
      return 'auth';
    }
    return 'overview';
  };
  const [page,setPage]=useState(getInitialPage);
  const [mobileNav,setMobileNav]=useState(false);
  const [selected,setSelected]=useState(null);
  const [query,setQuery]=useState('');
  const [category,setCategory]=useState('all');
  const [district,setDistrict]=useState('all');
  const [user,setUser]=useState(null);

  useEffect(() => {
    const token = localStorage.getItem('infrapulse_token');
    if (token) {
      fetch(`${API}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.user) {
          setUser(data.user);
          // If non-admin user lands on an admin or general page, redirect them straight to their feedback portal
          if (data.user.role !== 'admin') {
            setPage(p => (p === 'my-village' ? 'my-village' : 'my-dashboard'));
          }
        }
      })
      .catch(() => {});
    }
  }, []);

  const handleLogin = (loggedUser) => {
    setUser(loggedUser);
    if (loggedUser.role === 'admin') setPage('overview');
    else setPage('my-dashboard');
  };

  const handleLogout = () => {
    localStorage.removeItem('infrapulse_token');
    setUser(null);
    setPage('auth');
  };

  const filtered=useMemo(()=>villages.filter(v=>{const q=query.toLowerCase().trim();return (!q||`${v.name} ${v.district} ${v.id}`.toLowerCase().includes(q))&&(category==='all'||v.score?.category?.key===category)&&(district==='all'||v.district===district)}),[villages,query,category,district]);
  const exportCsv=async()=>{try{const params=new URLSearchParams();if(district!=='all')params.set('district',district);if(category!=='all')params.set('category',category);if(query)params.set('q',query);const res=await fetch(`${API}/api/v1/export.csv?${params}`);if(!res.ok)throw new Error('CSV export failed');const blob=await res.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='infrapulse-village-reliability.csv';a.click();URL.revokeObjectURL(url)}catch(e){alert(`Unable to export: ${e.message}`)}};
  const pageMeta={
    overview:['Overview','A clearer view of where infrastructure serves people reliably.'],
    map:['Map explorer','Find reliability gaps across the demonstration region.'],
    rankings:['Priority ranking','Compare need, population impact and service criticality.'],
    scenario:['Scenario lab','Explore how hypothetical interventions change the reliability score.'],
    methodology:['Methodology & data','Transparent scoring, source provenance and limitations.'],
    auth:['Account Access','Sign in or register as a resident or administrator.'],
    'my-village':['Village Verification','Verify your location and residency within your village.'],
    'my-dashboard':['Resident Portal','View development projects and submit evidence with photo overlay.'],
    'admin-import':['Admin Dev Import','Import and preview development record datasets.'],
    'admin-review':['Admin Review Console','Review citizen observations and promote trusted evidence.'],
    'admin-summary':['Verification Summary','Review coverage, discrepancy, and agreement metrics.'],
  };

  return <div className="app-shell"><a href="#main-content" className="skip-link">Skip to main content</a>
  <Sidebar page={page} setPage={setPage} open={mobileNav} setOpen={setMobileNav} user={user} onLogout={handleLogout}/>
  <main className="main-shell" role="main">
    <Header title={pageMeta[page]?.[0] || 'InfraPulse'} subtitle={pageMeta[page]?.[1] || ''} onMenu={()=>setMobileNav(true)} onExport={exportCsv} loading={refresh} user={user}/>
    <div className="content-area" id="main-content">
      {error&&<div className="connection-error"><div className="error-icon"><Zap size={19}/></div><div><b>Cannot connect to InfraPulse API</b><p>{error}</p><code>cd backend && uvicorn app.main:app --reload --port 8000</code></div><button className="btn btn-secondary" onClick={refresh}>Retry</button></div>}
      {!error&&<Notice>DEMO ENVIRONMENT: sample scores and map pins are synthetic and must not be presented as official measurements.</Notice>}
      {loading&&!error?<div className="loading-state"><div className="spinner"/><span>Loading infrastructure data…</span></div>:!error&&<>
      {/* Non-admin logged in user (Resident): restricted strictly to feedback & village verification */}
      {user && user.role !== 'admin' && (
        <>
          {page === 'my-dashboard' && <ResidentDashboard onLogout={handleLogout} />}
          {page === 'my-village' && (
            <LocationVerifyPage
              currentUser={user}
              onProceedToRecords={() => setPage('my-dashboard')}
            />
          )}
          {page !== 'my-dashboard' && page !== 'my-village' && <ResidentDashboard onLogout={handleLogout} />}
        </>
      )}

      {/* Unauthenticated: strictly show login screen only, no workspace content */}
      {!user && <AuthPage onLogin={handleLogin}/>}
      {/* Admin user: full suite only after login */}
      {user?.role === 'admin' && (
        <>
          {page==='overview'&&<Overview villages={villages} summary={summary} onSelect={setSelected} setPage={setPage}/>}
          {page==='map'&&<><MapPage villages={filtered} onSelect={setSelected} query={query} setQuery={setQuery} category={category} setCategory={setCategory} district={district} setDistrict={setDistrict}/><ImportPanel onImported={refresh}/></>}
          {page==='rankings'&&<RankingsPage villages={filtered} onSelect={setSelected}/>}
          {page==='scenario'&&<ScenarioPage villages={villages} onSelect={setSelected}/>}
          {page==='methodology'&&<MethodologyPage methodology={methodology} sources={sources}/>}
          {page==='admin-import'&&<AdminImportConsole/>}
          {page==='admin-review'&&<AdminReviewConsole/>}
          {page==='admin-summary'&&<VerificationSummaryPage/>}
        </>
      )}
      </>}
      <footer className="app-footer"><span>INFRAPULSE · PROTOTYPE V1.0</span><span>Evidence first. Decisions with context.</span><button onClick={()=>setPage('methodology')}>Methodology & limitations</button></footer>
    </div>
  </main>
  {mobileNav&&<button className="mobile-scrim" onClick={()=>setMobileNav(false)} aria-label="Close navigation"/>}
  <VillageModal village={selected} onClose={()=>setSelected(null)}/>
  </div>;
}
