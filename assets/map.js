/* Source-backed SVG route viewer. No dependencies, keys, cookies or telemetry. */
"use strict";
(() => {
  const root = document.documentElement.dataset.root || "./";
  const route = document.documentElement.dataset.route;
  const $ = id => document.getElementById(id);
  const el = (tag, text, cls) => { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; };
  const link = (url, text) => { const a=el("a",text); a.href=url; if(/^https?:/.test(url)){a.target="_blank";a.rel="noopener noreferrer";} return a; };
  const get = async url => { const r=await fetch(url); if(!r.ok)throw Error(`${r.status} loading ${url}`); return r.json(); };
  const badgeText = s => ({current:"In latest capture",discontinued:"Historical",special:"Special service",uncertain:"Evidence limited"}[s] || s);
  const fail = error => { const target=$("app-status"); target.className="error"; target.textContent=`The archive could not load: ${error.message}. To open a local checkout, run python -m http.server 8000 from the repository and visit http://localhost:8000. All histories, CSV stop lists, GeoJSON and SVG maps can also be read directly from their route folders.`; target.hidden=false; };

  async function catalog() {
    const data = await get(root + "data/catalog.json");
    $("family-count").textContent = data.routes.length;
    $("pattern-count").textContent = data.pattern_count.toLocaleString();
    $("document-count").textContent = data.archive_document_count.toLocaleString();
    const initial = new URLSearchParams(location.search);
    $("search").value = initial.get("q") || "";
    if (["current", "discontinued", "special"].includes(initial.get("status"))) {
      $("status-filter").value = initial.get("status");
    }
    function draw() {
      const q = $("search").value.toLowerCase().trim();
      const status = $("status-filter").value;
      const selected = data.routes.filter(r => {
        const words = (`route ${r.route} ${r.name} ${(r.aliases || []).join(" ")}`).toLowerCase();
        return (!status || r.status === status) && q.split(/\s+/).every(word => words.includes(word));
      }).sort((a, b) => Number(a.route) - Number(b.route));
      $("cards").replaceChildren();
      selected.forEach(r => {
        const page = `routes/${r.folder}/index.html`;
        const pdf = `routes/${r.folder}/route-${r.folder}-history.pdf`;
        const card = el("article", undefined, "card");
        const top = el("div", undefined, "card-top");
        const badgeClass = r.status === "discontinued" ? "retired" : r.status === "special" ? "special" : "";
        top.append(el("span", r.route, "number"), el("span", badgeText(r.status), "badge " + badgeClass));
        const title = el("h3");
        const titleLink = link(page, r.name);
        titleLink.className = "card-title";
        title.append(titleLink);
        const meta = el("p", `${r.pattern_count} documented patterns · ${r.history_events} history entries`, "card-meta");
        const evidence = el("p", r.snapshot_dates.length
          ? `Original captures: ${r.snapshot_dates.map(d => d.slice(0, 4)).join(" / ")}`
          : "Original timetables & historical records", "card-evidence");
        const actions = el("div", undefined, "card-actions");
        const mapLink = link(page, "Explore map ↗");
        mapLink.setAttribute("aria-label", `Explore route ${r.route} maps and history`);
        const pdfLink = link(pdf, "PDF ↓");
        pdfLink.className = "card-pdf";
        pdfLink.setAttribute("aria-label", `Open route ${r.route} history PDF`);
        actions.append(mapLink, pdfLink);
        card.append(top, title, meta, evidence, actions);
        $("cards").append(card);
      });
      if (!selected.length) {
        const empty = el("div", undefined, "empty-state");
        empty.append(el("h3", "No routes found."), el("p", "Try a route number, a city, or a different service filter."));
        const reset = el("button", "Show all routes");
        reset.type = "button";
        reset.addEventListener("click", () => {
          $("search").value = "";
          $("status-filter").value = "";
          draw();
          $("search").focus();
        });
        empty.append(reset);
        $("cards").append(empty);
      }
      $("result-count").textContent = `${selected.length} of ${data.routes.length} route families`;
      const params = new URLSearchParams();
      if (q) params.set("q", $("search").value.trim());
      if (status) params.set("status", status);
      history.replaceState(null, "", `${location.pathname}${params.size ? "?" + params : ""}${location.hash}`);
    }
    $("search").addEventListener("input", draw);
    $("status-filter").addEventListener("change", draw);
    document.addEventListener("keydown", event => {
      if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey &&
          !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) &&
          !document.activeElement.isContentEditable) {
        event.preventDefault();
        $("search").focus();
      }
    });
    draw();
    $("app-status").hidden = true;
  }

  const NS="http://www.w3.org/2000/svg";
  function svg(tag,attrs={},text){const n=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;}
  let map, viewport, fitBox=[0,0,1000,570], view=[...fitBox], drag=null, suppressClick=false, currentRender=null;
  function updateView(){map.setAttribute("viewBox",view.join(" "));}
  function zoom(factor){const [x,y,w,h]=view,nw=w*factor,nh=h*factor;view=[x+(w-nw)/2,y+(h-nh)/2,nw,nh];updateView();}
  function initMap(){
    map=$("map");
    let resizeTimer;
    window.addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(currentRender){const previous=[...view];renderMap(currentRender.pattern,currentRender.land);view=previous;updateView();}},120);});
    $("zoom-in").onclick=()=>zoom(.72);$("zoom-out").onclick=()=>zoom(1.4);$("fit-map").onclick=()=>{view=[...fitBox];updateView();};
    map.addEventListener("pointerdown",e=>{drag={x:e.clientX,y:e.clientY,view:[...view],pointerId:e.pointerId};suppressClick=false;});
    map.addEventListener("pointermove",e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>5){suppressClick=true;if(!map.hasPointerCapture(e.pointerId))map.setPointerCapture(e.pointerId);}const rect=map.getBoundingClientRect();view=[drag.view[0]-dx/rect.width*drag.view[2],drag.view[1]-dy/rect.height*drag.view[3],drag.view[2],drag.view[3]];updateView();});
    map.addEventListener("pointerup",()=>{drag=null;});map.addEventListener("pointercancel",()=>{drag=null;});
    map.addEventListener("keydown",e=>{if(e.key==="+"||e.key==="="){zoom(.8);e.preventDefault();}if(e.key==="-"){zoom(1.25);e.preventDefault();}if(e.key==="0"){view=[...fitBox];updateView();}});
  }
  function geometryRings(g){if(g.type==="Polygon")return g.coordinates;if(g.type==="MultiPolygon")return g.coordinates.flat();return [];}
  function renderMap(pattern,land){
    currentRender={pattern,land};
    const mapScale=Math.min(3,Math.max(1,1000/Math.max(1,map.getBoundingClientRect().width)));
    const located=pattern.stops.filter(s=>Number.isFinite(s.lon)&&Number.isFinite(s.lat));
    const coordinates=pattern.geometry?.coordinates||located.map(s=>[s.lon,s.lat]);
    map.replaceChildren(svg("title",{},`${pattern.branch||route}: ${pattern.label||pattern.headsign||"route pattern"}`));
    if(!located.length){map.append(svg("text",{x:35,y:60,fill:"#183a32"},"The original stop sequence is preserved; locations are not yet established."));return;}
    const merc=p=>[p[0]*Math.PI/180,Math.log(Math.tan(Math.PI/4+p[1]*Math.PI/360))];
    const coords=[...coordinates,...located.map(s=>[s.lon,s.lat])].map(merc);
    let minx=Math.min(...coords.map(p=>p[0])),maxx=Math.max(...coords.map(p=>p[0])),miny=Math.min(...coords.map(p=>p[1])),maxy=Math.max(...coords.map(p=>p[1]));
    let width=Math.max(maxx-minx,.0012),height=Math.max(maxy-miny,.0008),scale=Math.min(880/width,450/height),cx=(minx+maxx)/2,cy=(miny+maxy)/2;
    const project=p=>{const v=merc(p);return [500+(v[0]-cx)*scale,285-(v[1]-cy)*scale];};
    const path=pts=>pts.map((p,i)=>{const q=project(p);return `${i?"L":"M"}${q[0].toFixed(2)},${q[1].toFixed(2)}`;}).join(" ");
    viewport=svg("g");map.append(viewport);
    (land.features||[]).forEach(f=>{const d=geometryRings(f.geometry).map(r=>path(r)+"Z").join(" ");viewport.append(svg("path",{d,class:"land","fill-rule":"evenodd"}));});
    if(coordinates.length>1)viewport.append(svg("path",{d:path(coordinates),class:"route-line "+((pattern.geometry_kind||"").includes("connections")||pattern.geometry_kind==="schematic"?"schematic":"")}));
    const labelBoxes=[];
    pattern.stops.forEach((s,i)=>{
      if(!Number.isFinite(s.lon)||!Number.isFinite(s.lat))return;
      const [x,y]=project([s.lon,s.lat]);const group=svg("g");
      group.append(svg("circle",{cx:x,cy:y,r:(i===0||i===pattern.stops.length-1?5.5:3.8)*mapScale,class:"stop-dot"}));
      const show=pattern.stops.length<35||i%Math.ceil(pattern.stops.length/28)===0||i===pattern.stops.length-1;
      const box={x:x+6*mapScale,y:y-20*mapScale,w:(String(i+1).length*7+3)*mapScale,h:15*mapScale};
      const overlaps=labelBoxes.some(b=>box.x<b.x+b.w&&box.x+box.w>b.x&&box.y<b.y+b.h&&box.y+box.h>b.y);
      if(show&&!overlaps){group.append(svg("text",{x:x+7*mapScale,y:y-8*mapScale,class:"stop-label",style:`font-size:${11*mapScale}px;stroke-width:${3*mapScale}px`},String(i+1)));labelBoxes.push(box);}
      group.append(svg("title",{},`${i+1}. ${s.name}`));const hit=svg("circle",{cx:x,cy:y,r:12*mapScale,class:"stop-hit",tabindex:0,role:"button","aria-label":`${i+1}. ${s.name}`});
      function activate(){if(suppressClick)return;document.querySelectorAll(".stop-list .active").forEach(n=>n.classList.remove("active"));const row=$("stop-"+i);row.classList.add("active");row.scrollIntoView({block:"nearest",behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"instant":"smooth"});}
      hit.addEventListener("click",activate);hit.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();activate();}});group.append(hit);viewport.append(group);
    });
    view=[...fitBox];updateView();
  }
  function renderStops(pattern){
    $("stop-count").textContent=`${pattern.stops.length} ${pattern.stop_scope==="major-stops"?"documented major stops":"scheduled stops"}`;
    $("stops").replaceChildren();
    pattern.stops.forEach((s,i)=>{
      const row=el("li");row.id="stop-"+i;row.append(el("span",i+1,"stop-n"));const body=el("div",s.name);
      let note=[];if(s.stop_id)note.push(`Stop ${s.stop_id}`);if(s.pickup_type==="1")note.push("No pickup");if(s.drop_off_type==="1")note.push("No drop-off");if(s.pickup_type==="2"||s.drop_off_type==="2")note.push("Advance arrangement required");
      if(!Number.isFinite(s.lat)||!Number.isFinite(s.lon)){note.push("Location not established");row.className="unlocated";}else if(s.accuracy&&s.accuracy!=="original-gtfs")note.push(s.accuracy);
      if(note.length)body.append(el("small",note.join(" · ")));row.append(body);$("stops").append(row);
    });
  }

  async function detail(){
    const [data,land]=await Promise.all([get("data.json"),get(root+"assets/ontario-mainland.geojson")]);
    $("route-number").textContent=/^\d+$/.test(data.route)?data.route:"LOCAL";$("route-title").textContent=data.name;document.title=`GO ${data.route} · ${data.name} · GO Bus History Maps`;
    $("route-description").textContent=data.description;$("route-status").textContent=badgeText(data.status);
    $("route-status").className="badge "+(data.status==="discontinued"?"retired":data.status==="special"?"special":"");
    const patternTotal=data.historic_patterns.length+(data.snapshots||[]).reduce((sum,s)=>sum+s.pattern_count,0);
    $("detail-pattern-count").textContent=patternTotal;
    $("detail-evidence-count").textContent=(data.snapshots||[]).length||data.historic_patterns.length;
    $("detail-evidence-label").textContent=(data.snapshots||[]).length?"original feed captures":"timetable versions";
    $("detail-history-count").textContent=data.timeline.length;
    data.timeline.forEach(e=>{const li=el("li");li.append(el("time",e.date),el("div",e.event));const refs=el("div",undefined,"source-links");(e.sources||[]).forEach((u,i)=>refs.append(link(u,`Source ${i+1}`)));li.append(refs);$("timeline").append(li);});
    data.sources.forEach(s=>{const li=el("li");li.append(link(s.url,s.title||s.url));if(s.type)li.append(el("div",s.type));$("sources").append(li);});
    data.gaps.forEach(g=>$("gaps").append(el("li",g)));
    if(!data.gaps.length)$("gaps").append(el("li","Dates between the documented snapshots remain subject to further archival research."));
    const versions=[];
    (data.snapshots||[]).slice().reverse().forEach(s=>versions.push({id:s.id,label:`${s.id} · original GO feed · ${s.pattern_count} patterns`,url:`snapshots/${s.id}.json`}));
    if(data.historic_patterns.length)versions.push({id:"historical",label:`Original timetables · ${data.historic_patterns.length} reconstructed versions`,patterns:data.historic_patterns});
    const versionSelect=$("version");versions.forEach(v=>versionSelect.append(new Option(v.label,v.id)));
    const params=new URLSearchParams(location.search);if(versions.some(v=>v.id===params.get("version")))versionSelect.value=params.get("version");
    let currentPatterns=[], currentVersion=null, revision=0;
    const datasetCache=new Map();
    function selectPattern(){
      const p=currentPatterns.find(p=>p.id===$("pattern").value)||currentPatterns[0];if(!p)return;
      $("pattern-heading").textContent=p.label||p.headsign||`${p.branch} pattern`;
      const reconstructed=versionSelect.value==="historical";
      $("map-evidence").textContent=reconstructed?"Historical reconstruction":"Original GO feed";
      $("map-evidence").className="map-evidence"+(reconstructed?" reconstructed":"");
      $("pattern-dates").textContent=(p.first_service_date?`Scheduled dates in this feed: ${p.first_service_date} to ${p.last_service_date}`:`Documented date: ${p.date||"See source"}`)+(p.direction?` · ${p.direction}`:p.direction_id!==undefined?` · Direction ${p.direction_id} (source label)`:"");
      $("map-note").textContent=[p.geometry_note||p.notes||"",p.stop_scope==="major-stops"?"This reconstruction shows timetable timing points / major stops; it is not an exhaustive roadside stop list.":"Stop order and boarding restrictions are retained from the source feed."].filter(Boolean).join(" ");
      $("pattern-source").replaceChildren();const urls=p.sources||[currentVersion?.snapshot?.url].filter(Boolean);urls.forEach((url,i)=>$("pattern-source").append(link(url,`Original source ${i+1} ↗`)));
      const service=$("service-dates");service.replaceChildren();if(p.service_dates?.length){service.textContent=p.service_dates.join(", ");$("service-detail").hidden=false;}else $("service-detail").hidden=true;
      renderMap(p,land);renderStops(p);
      const query=new URLSearchParams({version:versionSelect.value,pattern:p.id});history.replaceState(null,"",`?${query}`);
    }
    async function selectVersion(){
      const generation=++revision,v=versions.find(v=>v.id===versionSelect.value);if(!v)return;
      if(v.patterns)currentVersion={patterns:v.patterns};else{if(!datasetCache.has(v.id))datasetCache.set(v.id,await get(v.url));if(generation!==revision)return;currentVersion=datasetCache.get(v.id);}
      currentPatterns=currentVersion.patterns;$("pattern").replaceChildren();currentPatterns.forEach(p=>$("pattern").append(new Option(`${p.branch||data.route}${p.date?` · ${p.date}`:""} · ${p.label||(p.headsign||"").replace(/^\S+\s*[-–]\s*/,"")||p.id}${p.direction?` · ${p.direction}`:""} · ${p.stops.length} stops`,p.id)));
      if(currentPatterns.some(p=>p.id===params.get("pattern"))){$("pattern").value=params.get("pattern");params.delete("pattern");}
      selectPattern();
    }
    initMap();versionSelect.addEventListener("change",()=>selectVersion().catch(fail));$("pattern").addEventListener("change",selectPattern);await selectVersion();$("app-status").hidden=true;
  }
  (route?detail():catalog()).catch(fail);
})();
