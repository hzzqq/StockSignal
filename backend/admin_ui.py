"""
backend/admin_ui.py
--------------------
Flask 后端（127.0.0.1:5050）的管理界面 UI。

问题：根路径 / 原本是空白页，用户希望有一个「适配前端金融风格」的后端管理界面。
方案：render_admin_ui() 返回一段自包含的 HTML 仪表盘（CSS + 原生 JS，零外部依赖）：
  - 登录面板：用现有 /api/auth/login 拿 JWT，存于浏览器 localStorage（ss_admin_token）
  - 登录后展示：系统概览 / 用户管理 / 系统配置 / 操作日志 / 股票统计
  - 用户管理：新建 / 改密 / 停用·启用 / 删除 / 改角色（走 /api/admin/users）
  - 系统配置：编辑值 / 新增 / 删除（走 /api/admin/config）
  - 调用现有后端 API（同源，无需 CORS）；任何渲染失败都只影响该卡片，不白屏
  - 亮/暗双主题（与前端 ui_theme 一致的金色 #B8860B 点缀），默认暗色

安全约定：
  - 这是「有意」的静态可信 HTML 页，渲染时所有用户数据均经 esc() 转义，无 XSS 风险。
  - 全局 errorhandler 仍对异常返回 JSON；本路由仅成功路径返回 text/html。
  - 所有写操作走既有鉴权接口（admin_required），无越权；敏感动作前端二次确认。
"""

from __future__ import annotations

from flask import Response


def render_admin_ui() -> Response:
    """返回适配前端金融风格的后端管理界面 HTML。"""
    html = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>StockSignal · 后端管理</title>
<style>
  :root{
    --gold:#B8860B; --gold2:#D4A02A; --gold-soft:rgba(184,134,11,.14);
    --ok:#2ecc71; --bad:#e74c3c; --warn:#f1c40f;
    --radius:14px; --shadow:0 6px 24px rgba(0,0,0,.18);
  }
  html[data-theme="dark"]{
    --bg:#0E1117; --panel:#161B26; --panel2:#1B2230; --border:#2A3344;
    --text:#E6EAF2; --muted:#8B97A8; --input:#0F141E;
  }
  html[data-theme="light"]{
    --bg:#DFE1E6; --panel:#FFFFFF; --panel2:#F7F8FA; --border:#D0CED8;
    --text:#1A2332; --muted:#6B7280; --input:#FFFFFF;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:'Inter',-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
       background:var(--bg);color:var(--text);min-height:100vh;}
  a{color:var(--gold2);text-decoration:none}
  .wrap{max-width:1180px;margin:0 auto;padding:28px 22px 60px}
  header.top{display:flex;align-items:center;justify-content:space-between;gap:16px;
       padding:18px 22px;background:var(--panel);border:1px solid var(--border);
       border-radius:var(--radius);box-shadow:var(--shadow);margin-bottom:22px}
  .brand{display:flex;align-items:center;gap:12px;font-weight:700;font-size:19px}
  .brand .logo{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;
       background:linear-gradient(135deg,var(--gold2),var(--gold));color:#fff;font-size:18px}
  .brand small{display:block;font-weight:400;color:var(--muted);font-size:12px}
  .top-actions{display:flex;align-items:center;gap:10px}
  button,input,select{font-family:inherit}
  .btn{border:1px solid var(--border);background:var(--panel2);color:var(--text);
       padding:9px 15px;border-radius:9px;cursor:pointer;font-size:14px;transition:.15s}
  .btn:hover{border-color:var(--gold)}
  .btn.primary{background:linear-gradient(135deg,var(--gold2),var(--gold));border:none;color:#fff;font-weight:600}
  .btn.primary:hover{filter:brightness(1.06)}
  .btn.ghost{background:transparent}
  .btn.danger{border-color:var(--bad);color:var(--bad)}
  .btn.danger:hover{background:rgba(231,76,60,.12)}
  .toggle{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:13px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);
        box-shadow:var(--shadow);padding:20px 22px;margin-bottom:20px}
  .card h2{margin:0 0 4px;font-size:17px;display:flex;align-items:center;gap:8px}
  .card h2 .bar{width:4px;height:18px;background:var(--gold);border-radius:2px;display:inline-block}
  .card .sub{color:var(--muted);font-size:12.5px;margin-bottom:14px}
  .grid{display:grid;gap:14px}
  .grid.kpi{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}
  .kpi{background:var(--panel2);border:1px solid var(--border);border-radius:12px;padding:16px 18px;
       border-left:3px solid var(--gold)}
  .kpi .v{font-size:26px;font-weight:700;line-height:1.1}
  .kpi .l{color:var(--muted);font-size:13px;margin-top:4px}
  table{width:100%;border-collapse:collapse;font-size:13.5px}
  th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--border)}
  th{color:var(--gold2);font-weight:600;background:var(--panel2);position:sticky;top:0}
  tr:hover td{background:var(--panel2)}
  .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}
  .pill.admin{background:rgba(184,134,11,.18);color:var(--gold2)}
  .pill.user{background:rgba(52,152,219,.16);color:#5dade2}
  .pill.ok{background:rgba(46,204,113,.16);color:var(--ok)}
  .pill.bad{background:rgba(231,76,60,.16);color:var(--bad)}
  .pill.warn{background:rgba(241,196,15,.16);color:var(--warn)}
  .empty{color:var(--muted);font-style:italic;padding:14px 2px}
  .err{color:var(--bad);font-size:13px;padding:8px 0}
  /* login */
  .login{max-width:400px;margin:8vh auto 0;background:var(--panel);border:1px solid var(--border);
        border-radius:var(--radius);box-shadow:var(--shadow);padding:30px 28px}
  .login h1{margin:0 0 4px;font-size:21px;display:flex;align-items:center;gap:10px}
  .login p{color:var(--muted);margin:0 0 18px;font-size:13px}
  .field{margin-bottom:13px}
  .field label{display:block;font-size:13px;color:var(--muted);margin-bottom:6px}
  .field input{width:100%;padding:11px 13px;border-radius:9px;border:1px solid var(--border);
        background:var(--input);color:var(--text);font-size:14px}
  .field input:focus{outline:none;border-color:var(--gold);box-shadow:0 0 0 3px var(--gold-soft)}
  .login .msg{font-size:13px;margin-top:10px;min-height:18px}
  .login .msg.err{color:var(--bad)} .login .msg.ok{color:var(--ok)}
  .hint{color:var(--muted);font-size:12px;margin-top:14px;line-height:1.6}
  .badge-user{font-size:13px;color:var(--muted)}
  pre.raw{background:var(--input);border:1px solid var(--border);border-radius:10px;padding:12px;
        max-height:240px;overflow:auto;font-size:12px;color:var(--muted)}
  .row-actions{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
  .mini-form{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px;
        background:var(--panel2);border:1px solid var(--border);border-radius:10px;padding:12px}
  .mini-form input,.mini-form select{padding:9px 11px;border-radius:8px;border:1px solid var(--border);
        background:var(--input);color:var(--text);font-size:14px;min-width:170px}
  .cfg-input{padding:6px 9px;border-radius:7px;border:1px solid var(--gold);background:var(--input);
        color:var(--text);font-size:13px;width:90%}
  .role-sel{padding:5px 8px;border-radius:7px;border:1px solid var(--border);background:var(--input);
        color:var(--text);font-size:13px}
</style>
</head>
<body>
<div class="wrap" id="app"><!-- 由 JS 渲染 --></div>

<script>
const $ = (s,r=document)=>r.querySelector(s);
const $$ = (s,r=document)=>Array.from(r.querySelectorAll(s));
const el = (tag,cls,html)=>{const e=document.createElement(tag); if(cls)e.className=cls; if(html!=null)e.innerHTML=html; return e;};
const api = (path,opts={}) => {
  const token = localStorage.getItem('ss_admin_token');
  const h = {'Content-Type':'application/json'};
  if(token) h['Authorization'] = 'Bearer '+token;
  return fetch(path,{...opts,headers:{...h,...(opts.headers||{})}}).then(r=>r.json().then(b=>({ok:r.ok,code:r.status,body:b})));
};
function fmt(n){ return (n==null?'—':Number(n).toLocaleString('zh-CN')); }
function pill(text,cls){ return `<span class="pill ${cls}">${text}</span>`; }
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function msgOf(res){ return (res.body&&res.body.message) || ('HTTP '+res.code); }

function renderLogin(msg, isErr){
  const app = $('#app'); app.innerHTML='';
  const box = el('div','login');
  box.innerHTML = `
    <h1><span class="logo">📡</span> StockSignal 后端</h1>
    <p>管理控制台 · 请使用管理员账号登录</p>
    <div class="field"><label>用户名</label><input id="u" placeholder="admin" autocomplete="username"/></div>
    <div class="field"><label>密码</label><input id="p" type="password" placeholder="Admin@123" autocomplete="current-password"/></div>
    <button class="btn primary" style="width:100%" id="loginBtn">🔐 登录</button>
    <div class="msg ${isErr?'err':''}" id="msg">${msg||''}</div>
    <div class="hint">默认管理员：<code>admin</code> / <code>Admin@123</code><br/>所有数据接口均走 JWT 鉴权，与前端共用同一后端。</div>
  `;
  app.appendChild(box);
  const doLogin = ()=>{
    const u=$('#u').value.trim(), p=$('#p').value;
    $('#msg').textContent='登录中…'; $('#msg').className='msg';
    api('/api/auth/login',{method:'POST',body:JSON.stringify({username:u,password:p})}).then(res=>{
      if(res.ok && res.body.status==='ok'){
        localStorage.setItem('ss_admin_token', res.body.data.token);
        renderDashboard(res.body.data.user);
      } else {
        renderLogin('登录失败：'+msgOf(res), true);
      }
    }).catch(e=>renderLogin('网络错误：'+e, true));
  };
  $('#loginBtn').onclick = doLogin;
  $('#p').addEventListener('keydown',e=>{ if(e.key==='Enter') doLogin(); });
}

function topbar(user){
  const bar = el('header','top');
  bar.innerHTML = `
    <div class="brand"><span class="logo">📡</span>
      <div>StockSignal 后端管理<small>A股事件驱动分析平台 · 管理控制台</small></div></div>
    <div class="top-actions">
      <span class="badge-user">👤 ${esc(user&&user.username||'')} · ${esc(user&&user.role||'')}</span>
      <span class="toggle"><button class="btn ghost" id="themeBtn">🌗 主题</button></span>
      <button class="btn" id="logoutBtn">🚪 退出</button>
    </div>`;
  return bar;
}

function renderDashboard(user){
  const app = $('#app'); app.innerHTML='';
  app.appendChild(topbar(user));

  // 欢迎提示（降低新用户门槛）
  const welcome = el('section','card');
  welcome.style.borderLeft = '3px solid var(--ok)';
  welcome.innerHTML = `<div class="sub" style="margin-bottom:0">
    👋 <b>欢迎使用 StockSignal 管理控制台</b>。左侧为导航分区，下方为实时监控与常用管理功能。
    所有操作均走 JWT 鉴权，与前端共用同一后端。鼠标悬停「?」可查看说明。
  </div>`;
  app.appendChild(welcome);

  // ══ 实时监控（默认展开，自动刷新）══
  const mon = el('section','card');
  mon.innerHTML = `<h2><span class="bar"></span>📡 实时监控
      <span class="pill ok" id="monLive" style="margin-left:8px">● 实时</span>
      <button class="btn ghost" id="monRefresh" style="margin-left:auto;font-size:12px">🔄 刷新</button></h2>
    <div class="sub">后端运行指标实时刷新（每 10 秒自动更新）。
      <span title="请求量：累计 API 调用次数；错误率：4xx/5xx 占比；延迟：平均响应毫秒">❓ 指标含义</span></div>
    <div class="grid kpi" id="monKpis">
      <div class="kpi"><div class="v">…</div><div class="l">加载中</div></div>
    </div>
    <h3 style="font-size:14px;margin:18px 0 8px">🔥 热点接口（按请求量排序）</h3>
    <div id="monEndpoints"><div class="empty">加载中…</div></div>`;
  app.appendChild(mon);

  // 概览卡片
  const ov = el('section','card');
  ov.innerHTML = `<h2><span class="bar"></span>系统概览</h2>
    <div class="sub">后端关键指标一览（配置变更后自动刷新）</div>
    <div class="grid kpi" id="kpis"><div class="kpi"><div class="v">…</div><div class="l">加载中</div></div></div>`;
  app.appendChild(ov);

  // 用户管理
  const users = el('section','card');
  users.innerHTML = `<h2><span class="bar"></span>用户管理</h2>
    <div class="sub">来自 /api/admin/users（仅管理员可见）· 可新建 / 改密 / 停用 / 删除 / 改角色</div>
    <div class="row-actions">
      <button class="btn primary" id="newUserBtn">➕ 新建用户</button>
      <button class="btn" id="refreshUsersBtn">🔄 刷新</button>
    </div>
    <div id="userForm" style="display:none" class="mini-form">
      <input id="uf_user" placeholder="用户名（2-32位，字母数字下划线中文）"/>
      <input id="uf_pwd" type="password" placeholder="密码（至少6位）"/>
      <select id="uf_role"><option value="user">user</option><option value="admin">admin</option></select>
      <button class="btn primary" id="uf_submit">提交</button>
      <button class="btn" id="uf_cancel">取消</button>
    </div>
    <div id="usersBody"><div class="empty">加载中…</div></div>`;
  app.appendChild(users);

  // 系统配置
  const cfg = el('section','card');
  cfg.innerHTML = `<h2><span class="bar"></span>系统配置</h2>
    <div class="sub">来自 /api/admin/config · 可编辑值 / 新增 / 删除</div>
    <div class="row-actions">
      <button class="btn primary" id="newCfgBtn">➕ 新增配置</button>
      <button class="btn" id="refreshCfgBtn">🔄 刷新</button>
    </div>
    <div id="cfgForm" style="display:none" class="mini-form">
      <input id="cf_key" placeholder="配置键（如 cache_days）"/>
      <input id="cf_val" placeholder="值"/>
      <input id="cf_desc" placeholder="说明（可选）"/>
      <button class="btn primary" id="cf_submit">提交</button>
      <button class="btn" id="cf_cancel">取消</button>
    </div>
    <div id="cfgBody"><div class="empty">加载中…</div></div>`;
  app.appendChild(cfg);

  // 操作日志
  const logs = el('section','card');
  logs.innerHTML = `<h2><span class="bar"></span>操作日志</h2>
    <div class="sub">来自 /api/admin/logs（最近 50 条，只读）</div>
    <div id="logsBody"><div class="empty">加载中…</div></div>`;
  app.appendChild(logs);

  // 股票统计
  const stk = el('section','card');
  stk.innerHTML = `<h2><span class="bar"></span>股票数据统计</h2>
    <div class="sub">来自 /api/stocks/stats（全市场 A 股）</div>
    <div id="stkBody"><div class="empty">加载中…</div></div>`;
  app.appendChild(stk);

  $('#logoutBtn').onclick = ()=>{ if(window.__monTimer) clearInterval(window.__monTimer); localStorage.removeItem('ss_admin_token'); renderLogin('已退出登录'); };
  $('#themeBtn').onclick = ()=>{
    const cur = document.documentElement.getAttribute('data-theme');
    document.documentElement.setAttribute('data-theme', cur==='dark'?'light':'dark');
  };
  $('#newUserBtn').onclick = ()=>toggleUserForm(true);
  $('#refreshUsersBtn').onclick = ()=>loadUsers();
  $('#uf_submit').onclick = submitUser;
  $('#uf_cancel').onclick = ()=>toggleUserForm(false);
  $('#newCfgBtn').onclick = ()=>toggleCfgForm(true);
  $('#refreshCfgBtn').onclick = ()=>loadConfig();
  $('#cf_submit').onclick = submitCfg;
  $('#cf_cancel').onclick = ()=>toggleCfgForm(false);
  $('#monRefresh').onclick = ()=>loadMonitor();

  loadAll();
  // 实时监控自动刷新（每 10 秒）
  window.__monTimer = setInterval(loadMonitor, 10000);
}

async function loadMonitor(){
  const kpiBox = $('#monKpis'); if(!kpiBox) return;
  const res = await api('/api/admin/monitor');
  if(!res.ok){ kpiBox.innerHTML = `<div class="err">监控数据加载失败：${esc(msgOf(res))}</div>`; return; }
  const d = res.body.data || {};
  const biz = d.business || {};
  const errCls = (d.error_rate_pct||0) > 5 ? 'bad' : ((d.error_rate_pct||0) > 1 ? 'warn' : 'ok');
  const latCls = (d.avg_latency_ms||0) > 500 ? 'bad' : ((d.avg_latency_ms||0) > 200 ? 'warn' : 'ok');
  const cards = [
    {v: fmt(d.total_requests), l:'总请求数', c:''},
    {v: fmt(d.active_users_5m), l:'活跃用户(5分)', c:'ok'},
    {v: `<span class="pill ${errCls}">${d.error_rate_pct}%</span>`, l:'错误率', c:''},
    {v: `<span class="pill ${latCls}">${d.avg_latency_ms}ms</span>`, l:'平均延迟', c:''},
    {v: fmt(d.uptime_text), l:'运行时长', c:''},
    {v: fmt(biz.users), l:'注册用户', c:''},
    {v: fmt(biz.forum_posts), l:'股吧帖子', c:''},
    {v: fmt(biz.price_alerts), l:'价格预警', c:''},
  ];
  kpiBox.innerHTML = cards.map(c=>`<div class="kpi" style="${c.c==='ok'?'border-left-color:var(--ok)':''}"><div class="v">${c.v}</div><div class="l">${c.l}</div></div>`).join('');
  // 热点接口表
  const epBox = $('#monEndpoints');
  const eps = d.endpoints || [];
  if(!eps.length){ epBox.innerHTML = '<div class="empty">暂无请求记录</div>'; return; }
  const rows = eps.map(e=>{
    const er = e.error_rate > 1 ? 'bad' : (e.error_rate>0?'warn':'ok');
    return `<tr>
      <td><code>${esc(e.endpoint)}</code></td>
      <td>${fmt(e.count)}</td>
      <td>${e.avg_ms}ms</td>
      <td>${e.max_ms}ms</td>
      <td><span class="pill ${er}">${e.error_rate}%</span></td>
    </tr>`;
  }).join('');
  epBox.innerHTML = `<table><thead><tr><th>接口</th><th>请求数</th><th>平均</th><th>峰值</th><th>错误率</th></tr></thead><tbody>${rows}</tbody></table>`;
}

async function loadAll(){
  loadKPIs(); loadUsers(); loadConfig(); loadLogs(); loadStocks();
}

async function loadKPIs(){
  const box = $('#kpis'); if(!box) return;
  const [u,logs,stk,cfg] = await Promise.all([
    api('/api/admin/users?per_page=1'), api('/api/admin/logs?per_page=1'),
    api('/api/stocks/stats'), api('/api/admin/config')
  ]);
  const uc = (u.ok && u.body.data)? u.body.data.total : null;
  const lc = (logs.ok && logs.body.data)? logs.body.data.total : null;
  const sc = (stk.ok && stk.body.data)? stk.body.data : null;
  const cc = (cfg.ok && Array.isArray(cfg.body.data))? cfg.body.data.length : null;
  const cards = [
    {v: fmt(uc), l:'用户总数'},
    {v: fmt(cc), l:'系统配置项'},
    {v: fmt(lc), l:'操作日志条数'},
    {v: fmt(sc&&sc.total), l:'A股总数'},
    {v: fmt(sc&&sc.sh), l:'沪市 SH'},
    {v: fmt(sc&&sc.sz), l:'深市 SZ'},
  ];
  box.innerHTML = cards.map(c=>`<div class="kpi"><div class="v">${c.v}</div><div class="l">${c.l}</div></div>`).join('');
}

/* ============================== 用户管理 CRUD ============================== */
function toggleUserForm(show){
  const f = $('#userForm'); if(!f) return;
  f.style.display = show ? 'flex':'none';
  if(show) $('#uf_user').focus();
}
async function submitUser(){
  const username = $('#uf_user').value.trim();
  const password = $('#uf_pwd').value;
  const role = $('#uf_role').value;
  if(!username){ alert('用户名不能为空'); return; }
  if(password.length<6){ alert('密码至少6位'); return; }
  const res = await api('/api/admin/users', {method:'POST', body:JSON.stringify({username,password,role})});
  if(res.ok){ alert('创建成功'); $('#uf_user').value=''; $('#uf_pwd').value=''; toggleUserForm(false); loadUsers(); }
  else { alert('失败：'+msgOf(res)); }
}
async function loadUsers(){
  const box = $('#usersBody'); if(!box) return;
  const res = await api('/api/admin/users?per_page=200');
  if(!res.ok){ box.innerHTML = `<div class="err">加载失败：${esc(msgOf(res))}</div>`; return; }
  const items = (res.body.data && res.body.data.items) || [];
  if(!items.length){ box.innerHTML='<div class="empty">暂无用户</div>'; return; }
  const rows = items.map(u=>{
    const roleSel = `<select class="role-sel" data-id="${u.id}">
        <option value="user" ${u.role==='user'?'selected':''}>user</option>
        <option value="admin" ${u.role==='admin'?'selected':''}>admin</option></select>`;
    const activeBtn = u.is_active===false
        ? `<button class="btn" data-act="enable" data-id="${u.id}">启用</button>`
        : `<button class="btn" data-act="disable" data-id="${u.id}">停用</button>`;
    return `<tr>
      <td>${esc(u.id)}</td><td>${esc(u.username)}</td>
      <td>${roleSel}</td>
      <td>${u.is_active===false?pill('已停用','bad'):pill('正常','ok')}</td>
      <td>${esc(u.created_at||'')}</td>
      <td>
        <button class="btn" data-act="pwd" data-id="${u.id}" data-name="${esc(u.username)}">改密</button>
        ${activeBtn}
        <button class="btn danger" data-act="del" data-id="${u.id}" data-name="${esc(u.username)}">删除</button>
      </td></tr>`;
  }).join('');
  box.innerHTML = `<table><thead><tr><th>ID</th><th>用户名</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table>`;
  $$('#usersBody [data-act]').forEach(btn=>{
    btn.onclick = ()=>handleUserAction(btn.getAttribute('data-act'), btn.getAttribute('data-id'), btn.getAttribute('data-name'));
  });
  $$('#usersBody .role-sel').forEach(sel=>{ sel.onchange = ()=>changeRole(sel.getAttribute('data-id'), sel.value); });
}
async function handleUserAction(act, id, name){
  if(act==='del'){
    if(!confirm(`确定删除用户「${name}」？此操作不可恢复。`)) return;
    const res = await api('/api/admin/users/'+id, {method:'DELETE'});
    alert(res.ok?'删除成功':('失败：'+msgOf(res))); loadUsers(); loadKPIs();
  } else if(act==='disable'){
    if(!confirm(`确定停用用户「${name}」？`)) return;
    const res = await api('/api/admin/users/'+id, {method:'PUT', body:JSON.stringify({is_active:false})});
    alert(res.ok?'已停用':('失败：'+msgOf(res))); loadUsers();
  } else if(act==='enable'){
    const res = await api('/api/admin/users/'+id, {method:'PUT', body:JSON.stringify({is_active:true})});
    alert(res.ok?'已启用':('失败：'+msgOf(res))); loadUsers();
  } else if(act==='pwd'){
    const np = prompt(`为「${name}」设置新密码（至少6位）：`);
    if(np==null) return;
    if(np.length<6){ alert('密码至少6位'); return; }
    const res = await api('/api/admin/users/'+id, {method:'PUT', body:JSON.stringify({password:np})});
    alert(res.ok?'密码已更新':('失败：'+msgOf(res)));
  }
}
async function changeRole(id, role){
  const res = await api('/api/admin/users/'+id, {method:'PUT', body:JSON.stringify({role})});
  alert(res.ok?'角色已更新':('失败：'+msgOf(res))); loadUsers();
}

/* ============================== 系统配置 CRUD ============================== */
function toggleCfgForm(show){
  const f = $('#cfgForm'); if(!f) return;
  f.style.display = show ? 'flex':'none';
  if(show) $('#cf_key').focus();
}
async function submitCfg(){
  const key = $('#cf_key').value.trim();
  const value = $('#cf_val').value;
  const description = $('#cf_desc').value;
  if(!key){ alert('配置键不能为空'); return; }
  const res = await api('/api/admin/config', {method:'POST', body:JSON.stringify({key,value,description})});
  if(res.ok){ alert('创建成功'); $('#cf_key').value=''; $('#cf_val').value=''; $('#cf_desc').value=''; toggleCfgForm(false); loadConfig(); loadKPIs(); }
  else { alert('失败：'+msgOf(res)); }
}
async function loadConfig(){
  const box = $('#cfgBody'); if(!box) return;
  const res = await api('/api/admin/config');
  if(!res.ok){ box.innerHTML = `<div class="err">加载失败：${esc(msgOf(res))}</div>`; return; }
  const items = res.body.data || [];
  if(!items.length){ box.innerHTML='<div class="empty">暂无配置</div>'; return; }
  const rows = items.map(c=>`<tr data-key="${esc(c.key)}">
    <td>${esc(c.key)}</td>
    <td class="cfg-val">${esc(c.value)}</td>
    <td>${esc(c.description||'')}</td>
    <td>
      <button class="btn" data-act="edit" data-key="${esc(c.key)}">编辑</button>
      <button class="btn danger" data-act="del" data-key="${esc(c.key)}">删除</button>
    </td></tr>`).join('');
  box.innerHTML = `<table><thead><tr><th>键</th><th>值</th><th>说明</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table>`;
  $$('#cfgBody [data-act]').forEach(btn=>{
    btn.onclick = ()=>handleCfgAction(btn.getAttribute('data-act'), btn.getAttribute('data-key'));
  });
}
async function handleCfgAction(act, key){
  if(act==='del'){
    if(!confirm(`确定删除配置「${key}」？`)) return;
    const res = await api('/api/admin/config/'+encodeURIComponent(key), {method:'DELETE'});
    alert(res.ok?'删除成功':('失败：'+msgOf(res))); loadConfig(); loadKPIs();
  } else if(act==='edit'){
    const rows = $$('#cfgBody tr');
    let tr = null;
    for(const r of rows){ if(r.getAttribute('data-key')===key){ tr=r; break; } }
    if(!tr) return;
    const valCell = tr.querySelector('.cfg-val');
    const actCell = tr.querySelector('td:last-child');
    valCell.innerHTML = `<input class="cfg-input" value="${esc(valCell.textContent)}"/>`;
    actCell.innerHTML = `<button class="btn primary" data-save="1">保存</button> <button class="btn" data-cancel="1">取消</button>`;
    actCell.querySelector('[data-cancel]').onclick = ()=>loadConfig();
    actCell.querySelector('[data-save]').onclick = async ()=>{
      const nv = tr.querySelector('.cfg-input').value;
      const res = await api('/api/admin/config/'+encodeURIComponent(key), {method:'PUT', body:JSON.stringify({value:nv})});
      alert(res.ok?'更新成功':('失败：'+msgOf(res))); loadConfig(); loadKPIs();
    };
  }
}

/* ============================== 只读模块 ============================== */
async function loadLogs(){
  const box = $('#logsBody'); if(!box) return;
  const res = await api('/api/admin/logs?per_page=50');
  if(!res.ok){ box.innerHTML = `<div class="err">加载失败：${esc(msgOf(res))}</div>`; return; }
  const items = (res.body.data && res.body.data.items) || [];
  if(!items.length){ box.innerHTML='<div class="empty">暂无日志</div>'; return; }
  const rows = items.map(l=>`<tr>
    <td>${esc(l.id)}</td><td>${esc(l.username)}</td>
    <td>${esc(l.action)}</td><td>${esc(l.target||'')}</td>
    <td>${esc(l.detail||'')}</td><td>${esc(l.created_at||'')}</td></tr>`).join('');
  box.innerHTML = `<table><thead><tr><th>ID</th><th>操作人</th><th>动作</th><th>对象</th><th>详情</th><th>时间</th></tr></thead><tbody>${rows}</tbody></table>`;
}

async function loadStocks(){
  const box = $('#stkBody'); if(!box) return;
  const res = await api('/api/stocks/stats');
  if(!res.ok){ box.innerHTML = `<div class="err">加载失败：${esc(msgOf(res))}</div>`; return; }
  const d = res.body.data || {};
  box.innerHTML = `<div class="grid kpi">
    <div class="kpi"><div class="v">${fmt(d.total)}</div><div class="l">A股总数</div></div>
    <div class="kpi"><div class="v">${fmt(d.sh)}</div><div class="l">沪市 SH</div></div>
    <div class="kpi"><div class="v">${fmt(d.sz)}</div><div class="l">深市 SZ</div></div>
  </div>`;
}

// 启动：有 token 先试 /api/auth/me，否则登录
(async ()=>{
  const token = localStorage.getItem('ss_admin_token');
  if(!token){ renderLogin(); return; }
  const me = await api('/api/auth/me');
  if(me.ok && me.body.status==='ok'){ renderDashboard(me.body.data.user); }
  else { localStorage.removeItem('ss_admin_token'); renderLogin(); }
})();
</script>
</body>
</html>
"""
    return Response(html, mimetype="text/html")
