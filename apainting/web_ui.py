from __future__ import annotations

from pathlib import Path


EDITOR_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>APainting Studio</title>
<style>
:root{--paper:#f5f1e9;--panel:#fffdf8;--ink:#222;--muted:#746f66;--line:#ddd6ca;--accent:#202020;--ok:#2f6e4f;--warn:#a66100}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{height:62px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 22px;background:#fbf8f2;position:sticky;top:0;z-index:5}
.brand{font-weight:750;letter-spacing:.02em}.sub{font-size:12px;color:var(--muted);margin-left:10px}.status{font-size:13px;color:var(--muted)}
.layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(340px,420px);gap:18px;padding:18px;max-width:1900px;margin:0 auto}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 30px #5b4f3c0c}.viewer{padding:14px}.side{padding:14px;min-height:650px}
.video-wrap{background:#ede8de;border-radius:10px;display:grid;place-items:center;height:min(80vh,1100px);min-height:620px;overflow:hidden}video{width:100%;height:100%;display:block;object-fit:contain;background:white}
.controls{display:grid;grid-template-columns:auto minmax(140px,1fr) auto auto auto auto;gap:10px;align-items:center;margin-top:12px}.btn,select{border:1px solid var(--line);background:#fffdf9;border-radius:8px;padding:8px 11px;font:inherit;cursor:pointer}.btn:hover{background:#f5f0e7}.btn.primary{background:#222;color:white;border-color:#222}.btn:disabled{opacity:.5;cursor:wait}
input[type=range]{width:100%}.time{font-variant-numeric:tabular-nums;font-size:12px;color:var(--muted);white-space:nowrap}
h2{font-size:16px;margin:0 0 6px}.hint{font-size:12px;color:var(--muted);line-height:1.55;margin-bottom:12px}.order-list{display:flex;flex-direction:column;gap:7px;min-height:100px}.unit{display:grid;grid-template-columns:26px 1fr auto;align-items:center;gap:8px;border:1px solid var(--line);border-radius:10px;padding:9px;background:#fff;user-select:none}.unit.dragging{opacity:.35}.unit.over{outline:2px solid #222}.handle{cursor:grab;color:#aaa;font-size:18px}.unit-title{font-size:13px;font-weight:650}.unit-meta{font-size:11px;color:var(--muted);margin-top:2px}.move{display:flex;gap:4px}.icon{border:0;background:transparent;cursor:pointer;padding:3px 5px;color:#666}.icon:hover{color:#111}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.section{border-top:1px solid var(--line);margin-top:16px;padding-top:16px}.warn{color:var(--warn);font-size:12px;margin-top:8px;white-space:pre-wrap}.ok{color:var(--ok)}
.export-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.history{max-height:150px;overflow:auto;border:1px solid var(--line);border-radius:8px}.history-item{padding:8px;border-bottom:1px solid #eee8dc;display:flex;justify-content:space-between;gap:8px;font-size:11px}.history-item:last-child{border-bottom:0}
.small{font-size:11px;color:var(--muted)}
@media(max-width:900px){.layout{grid-template-columns:1fr}.video-wrap{height:70vh;min-height:420px}.controls{grid-template-columns:auto 1fr auto}.speed,.loop{grid-row:2}.side{min-height:0}}
</style>
</head>
<body>
<header><div><span class="brand">APainting Studio</span><span class="sub">V4 · Macro Unit Order Editor</span></div><div id="status" class="status">加载项目…</div></header>
<main class="layout">
<section class="card viewer">
  <div class="video-wrap"><video id="video" preload="metadata" playsinline></video></div>
  <div class="controls">
    <button class="btn" id="playBtn">▶ 播放</button>
    <input id="seek" type="range" min="0" max="1000" value="0">
    <span class="time" id="time">00:00 / 00:00</span>
    <select id="speed" class="speed" title="播放速度"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="0.75">0.75×</option><option value="1" selected>1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select>
    <label class="small loop"><input id="loop" type="checkbox"> 循环</label>
    <button class="btn" id="fullscreenBtn">全屏</button>
  </div>
  <div class="section"><div class="small">当前预览只改变<strong>大主体播放顺序</strong>。主体内部的 V3 structure / focus session 顺序保持不变。</div></div>
</section>
<aside class="card side">
  <h2>大主体播放顺序</h2>
  <div class="hint">拖动主体，或用 ↑ ↓ 调整。比如可以把「远山 → 溪流 → 左松树 → 右松树」改成「远山 → 左松树 → 右松树 → 溪流」。这不会改变主体 ownership。</div>
  <div id="orderList" class="order-list"></div>
  <div class="actions">
    <button class="btn primary" id="applyBtn">应用顺序并生成预览</button>
    <button class="btn" id="resetBtn">恢复 AI 顺序</button>
  </div>
  <div id="warnings" class="warn"></div>

  <div class="section">
    <h2>高清视频导出</h2>
    <div class="hint">预览可用 720p；最终导出可选 1080p 或原图分辨率。导出不会改变当前顺序。</div>
    <div class="export-row">
      <select id="exportProfile"><option value="1080p">1080p</option><option value="source">原图分辨率</option></select>
      <button class="btn" id="exportBtn">导出 MP4</button>
      <a id="exportLink" class="small" target="_blank"></a>
    </div>
  </div>

  <div class="section">
    <h2>顺序历史</h2>
    <div class="hint">每次应用顺序都会自动保存一个顺序快照，可一键恢复。后续可以在这个接口上扩展完整项目历史存档。</div>
    <div id="history" class="history"></div>
  </div>
</aside>
</main>
<script>
const $=s=>document.querySelector(s);let project=null;let order=[];let dragId=null;
const video=$('#video'),seek=$('#seek'),playBtn=$('#playBtn'),statusEl=$('#status');
function fmt(t){if(!isFinite(t))return '00:00';const m=Math.floor(t/60),s=Math.floor(t%60);return String(m).padStart(2,'0')+':'+String(s).padStart(2,'0')}
function syncPlayer(){seek.value=video.duration?Math.round(video.currentTime/video.duration*1000):0;$('#time').textContent=`${fmt(video.currentTime)} / ${fmt(video.duration)}`;playBtn.textContent=video.paused?'▶ 播放':'⏸ 暂停'}
playBtn.onclick=async()=>{try{video.paused?await video.play():video.pause()}catch(e){statusEl.textContent='播放失败：'+e.message}};video.addEventListener('timeupdate',syncPlayer);video.addEventListener('loadedmetadata',syncPlayer);video.addEventListener('play',syncPlayer);video.addEventListener('pause',syncPlayer);video.addEventListener('error',()=>statusEl.textContent='预览视频无法解码或加载');seek.oninput=()=>{if(video.duration)video.currentTime=Number(seek.value)/1000*video.duration};$('#speed').onchange=e=>video.playbackRate=Number(e.target.value);$('#loop').onchange=e=>video.loop=e.target.checked;$('#fullscreenBtn').onclick=()=>video.requestFullscreen?.();
function unitById(id){return project.units.find(u=>u.id===id)}
function renderOrder(){const box=$('#orderList');box.innerHTML='';order.forEach((id,idx)=>{const u=unitById(id);const el=document.createElement('div');el.className='unit';el.draggable=true;el.dataset.id=id;el.innerHTML=`<div class="handle">⋮⋮</div><div><div class="unit-title">${idx+1}. ${u.label||u.id}</div><div class="unit-meta">${u.id} · ${u.kind} · ${u.direction}${u.share_percent!=null?' · '+u.share_percent.toFixed(1)+'%':''}</div></div><div class="move"><button class="icon up" title="上移">↑</button><button class="icon down" title="下移">↓</button></div>`;
 el.addEventListener('dragstart',()=>{dragId=id;el.classList.add('dragging')});el.addEventListener('dragend',()=>{dragId=null;el.classList.remove('dragging');document.querySelectorAll('.unit').forEach(x=>x.classList.remove('over'))});el.addEventListener('dragover',e=>{e.preventDefault();el.classList.add('over')});el.addEventListener('dragleave',()=>el.classList.remove('over'));el.addEventListener('drop',e=>{e.preventDefault();el.classList.remove('over');if(!dragId||dragId===id)return;const from=order.indexOf(dragId),to=order.indexOf(id);order.splice(from,1);order.splice(to,0,dragId);renderOrder()});
 el.querySelector('.up').onclick=()=>{if(idx>0){[order[idx-1],order[idx]]=[order[idx],order[idx-1]];renderOrder()}};el.querySelector('.down').onclick=()=>{if(idx<order.length-1){[order[idx+1],order[idx]]=[order[idx],order[idx+1]];renderOrder()}};box.appendChild(el)});renderWarnings()}
function renderWarnings(){if(!project)return;const pos=Object.fromEntries(order.map((x,i)=>[x,i]));const bad=(project.dependencies||[]).filter(d=>pos[d.before]>pos[d.after]);$('#warnings').textContent=bad.length?'当前手动顺序反转了 AI 依赖建议：\n'+bad.map(d=>`${d.before} → ${d.after}${d.reason?' · '+d.reason:''}`).join('\n'):''}
async function api(path,opt){const r=await fetch(path,opt);const data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(data.detail||data.error||r.statusText);return data}
async function loadProject(){project=await api('/api/project');order=[...project.current_order];renderOrder();renderHistory(project.history||[]);reloadVideo();statusEl.textContent=`${project.units.length} 个主体 · ${project.event_count||0} events`;}
function reloadVideo(){const t=video.currentTime||0;video.src=project.video_url+'?v='+Date.now();video.load();video.addEventListener('loadedmetadata',()=>{video.currentTime=Math.min(t,video.duration||0)}, {once:true})}
$('#applyBtn').onclick=async()=>{const b=$('#applyBtn');b.disabled=true;statusEl.textContent='正在重编译并生成预览…';try{const r=await api('/api/unit-order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({unit_order:order,render_preview:true})});project=await api('/api/project');order=[...project.current_order];renderOrder();renderHistory(project.history||[]);reloadVideo();statusEl.innerHTML='<span class="ok">顺序已应用</span>'}catch(e){statusEl.textContent='失败：'+e.message}finally{b.disabled=false}}
$('#resetBtn').onclick=async()=>{order=[...project.ai_order];renderOrder()};
$('#exportBtn').onclick=async()=>{const b=$('#exportBtn');b.disabled=true;$('#exportLink').textContent='';statusEl.textContent='正在导出高清视频…';try{const r=await api('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile:$('#exportProfile').value})});$('#exportLink').href=r.url;$('#exportLink').textContent='下载 '+r.filename;statusEl.innerHTML='<span class="ok">导出完成</span>'}catch(e){statusEl.textContent='导出失败：'+e.message}finally{b.disabled=false}}
function renderHistory(items){const box=$('#history');box.innerHTML='';if(!items.length){box.innerHTML='<div class="history-item"><span>暂无历史快照</span></div>';return}items.slice(0,20).forEach(h=>{const el=document.createElement('div');el.className='history-item';const time=(h.updated_at||'').replace('T',' ').replace(/\+.*/,'');el.innerHTML=`<span>${time}<br><span class="small">${(h.unit_order||[]).slice(0,4).join(' → ')}${h.unit_order&&h.unit_order.length>4?' …':''}</span></span><button class="icon">恢复</button>`;el.querySelector('button').onclick=async()=>{statusEl.textContent='恢复历史顺序…';await api('/api/history/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({history_id:h.id,render_preview:true})});await loadProject();reloadVideo();statusEl.innerHTML='<span class="ok">已恢复历史顺序</span>'};box.appendChild(el)})}
loadProject().catch(e=>statusEl.textContent='加载失败：'+e.message);
</script>
</body></html>'''


def write_web_ui(run_dir: Path) -> Path:
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    path = outputs / "index.html"
    path.write_text(EDITOR_HTML, encoding="utf-8")
    return path
