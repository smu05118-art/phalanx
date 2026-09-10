// fed.js — Panoptes 「🏛 연준」 탭 렌더러 (의존성 0 · 순수 SVG · ES2018 이하)
// window.renderFed(el, data[, opts]) → {refresh, openProfile(pid[,tab]), closeProfile, setState}
// data 키 = {roster, positions, statements, calendar, reaction, taco} (contracts/*.json 그대로)
// 로드 시 DOM 부작용 0. 전역은 renderFed + __fedLayout(테스트 훅) 둘뿐.
(function () {
  'use strict';

  /* ══════════════════ 1. CSS (1회 주입) ══════════════════ */
  var CSS = [
    '.fd-wrap{display:flex;flex-direction:column;gap:16px;width:100%;max-width:1520px;margin-inline:auto;min-width:0;font-family:var(--sans,-apple-system,sans-serif);color:var(--ink,#e6edf3)}',
    '.fd-wrap *,.fd-modal *{box-sizing:border-box}.fd-card[id]{scroll-margin-top:72px}',
    '.fd-grid{display:grid;grid-template-columns:300px minmax(0,1fr);gap:14px}',
    '.fd-grid2{display:grid;grid-template-columns:minmax(0,2fr) minmax(340px,1fr);gap:14px}',
    '.fd-card{background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:13px;padding:16px 18px;min-width:0}',
    '.fd-card.dark{background:#0b0b0b;border-color:#1a1a1a}',
    '.fd-card.wide{grid-column:1/-1}',
    '.fd-h{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}',
    '.fd-h b{font-size:13.5px}',
    '.fd-foot{font-size:10px;color:var(--dim,#8a93a3);margin-top:12px;border-top:1px solid var(--line,#1f2937);padding-top:8px;line-height:1.55}',
    '.fd-hint{color:var(--dim,#8a93a3);font-size:12.5px;line-height:1.6;padding:10px 2px}',
    '.fd-mono{font-family:var(--mono,ui-monospace,Menlo,monospace)}',
    /* hero */
    '.fd-hero{display:flex;align-items:center;gap:14px;flex-wrap:wrap}',
    '.fd-hero h2{font-size:20px;font-weight:800;letter-spacing:-.01em}',
    '.fd-dcount{font-family:var(--mono,monospace);font-size:15px;font-weight:800;color:var(--accent,#2bc0d4);background:rgba(43,192,212,.12);border:1px solid rgba(43,192,212,.35);border-radius:999px;padding:3px 12px}',
    '.fd-ts{margin-left:auto;font-family:var(--mono,monospace);font-size:9.5px;color:var(--dim,#8a93a3);line-height:1.5;text-align:right}',
    '.fd-bd{display:inline-block;font-size:9.5px;font-family:var(--mono,monospace);padding:2px 8px;border-radius:5px;border:1px solid var(--line,#1f2937);color:var(--dim,#8a93a3)}',
    '.fd-bd.mock{border-color:#ff8a3d;color:#ff8a3d;background:rgba(255,138,61,.1)}',
    '.fd-bd.bo{border-color:#ff4d5e;color:#ff4d5e;background:rgba(255,77,94,.1)}',
    '.fd-bd.vote{border-color:rgba(43,192,212,.45);color:var(--accent,#2bc0d4);background:rgba(43,192,212,.1)}',
    '.fd-bd.dev{border-color:#ff4d5e;color:#ff4d5e;background:rgba(255,77,94,.12);font-weight:700}',
    /* nav / chips */
    '.fd-nav{position:sticky;top:0;z-index:6;display:flex;gap:6px;flex-wrap:wrap;padding:8px 0;background:var(--bg,#0a0e14)}',
    '.fd-chip{font-size:11.5px;min-height:36px;padding:6px 12px;border:1px solid var(--line,#1f2937);border-radius:999px;cursor:pointer;color:var(--dim,#8a93a3);opacity:.85;transition:color .15s,border-color .15s,background-color .15s;white-space:nowrap;background:none;font-family:inherit;touch-action:manipulation}',
    '.fd-chip:hover{border-color:rgba(43,192,212,.4);color:var(--accent,#2bc0d4)}',
    '.fd-chip:focus-visible,.fd-btn:focus-visible,.fd-x:focus-visible,.fd-table-scroll:focus-visible{outline:2px solid var(--accent,#2bc0d4);outline-offset:3px}',
    '.fd-chip.on{opacity:1;color:var(--accent,#2bc0d4);border-color:rgba(43,192,212,.4);background:rgba(43,192,212,.12)}',
    '.fd-chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;align-items:center}',
    '.fd-chips .sep{width:1px;height:14px;background:var(--line,#1f2937);margin:0 3px}',
    '.fd-btn{background:rgba(43,192,212,.12);border:1px solid rgba(43,192,212,.35);color:var(--accent,#2bc0d4);font-size:11px;font-weight:650;padding:3px 10px;border-radius:999px;cursor:pointer;font-family:inherit}',
    /* 분포 */
    '.fd-dist svg.fd-plot{width:100%;height:auto;display:block}',
    '.fd-node{cursor:pointer;outline:none}',
    '.fd-node .fd-scale{transition:transform .13s ease}',
    '.fd-node:hover .fd-scale,.fd-node:focus .fd-scale{transform:scale(1.12)}',
    '.fd-node.chair .fd-ring{filter:drop-shadow(0 0 6px currentColor)}',
    '.fd-node:focus .fd-ring{stroke-dasharray:none}',
    '.fd-legend{font-size:10.5px;color:var(--dim,#8a93a3);line-height:1.6}',
    '.fd-tip{position:fixed;pointer-events:none;opacity:0;z-index:70;background:rgba(8,11,17,.95);border:1px solid var(--line,#1f2937);border-radius:8px;padding:6px 9px;font-family:var(--mono,monospace);font-size:10.5px;color:var(--ink,#e6edf3);line-height:1.55;max-width:280px;transition:opacity .1s}',
    '.fd-tip.on{opacity:1}',
    '.fd-people{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:8px;margin-top:12px}',
    '.fd-person{display:flex;align-items:center;gap:9px;min-width:0;min-height:60px;padding:8px;text-align:left;background:var(--panel2,#0d131c);border:1px solid var(--line,#1f2937);border-radius:10px;color:var(--ink,#e6edf3);font-family:inherit;cursor:pointer;touch-action:manipulation;transition:border-color .15s,background-color .15s}',
    '.fd-person:hover{border-color:var(--accent,#2bc0d4);background:rgba(43,192,212,.07)}.fd-person:focus-visible{outline:2px solid var(--accent,#2bc0d4);outline-offset:2px}',
    '.fd-avatar{position:relative;display:grid;place-items:center;flex:0 0 40px;width:40px;height:40px;border-radius:50%;overflow:hidden;background:#253344;border:2px solid var(--fd-ring,#8a93a3);font-size:12px;font-weight:750}.fd-avatar img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center top}',
    '.fd-person-text{min-width:0}.fd-person b{display:block;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.fd-person small{display:block;font-size:10px;color:var(--dim,#8a93a3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:3px}',
    /* 발언 피드 */
    '.fd-day{font-family:var(--mono,monospace);font-size:10px;color:var(--dim,#8a93a3);letter-spacing:.08em;margin:12px 0 6px;border-bottom:1px solid var(--line,#1f2937);padding-bottom:3px}',
    '.fd-sp{background:var(--panel2,#0d131c);border:1px solid var(--line,#1f2937);border-radius:9px;padding:10px 12px;margin-bottom:7px;transition:.13s}',
    '.fd-sp.fresh{border-left:3px solid var(--accent,#2bc0d4)}',
    '.fd-sp:hover{border-color:rgba(43,192,212,.45)}',
    '.fd-sp .sph{display:flex;align-items:center;gap:7px;flex-wrap:wrap;font-size:11.5px;color:var(--dim,#8a93a3)}',
    '.fd-sp .sph b{color:var(--ink,#e6edf3);font-size:12.5px}',
    '.fd-sp .spt{font-size:12.5px;font-weight:650;line-height:1.4;margin:5px 0 3px}',
    '.fd-sp .spt a{color:var(--ink,#e6edf3);text-decoration:none}',
    '.fd-sp .spt a:hover{color:var(--accent,#2bc0d4)}',
    '.fd-sum{font-size:11.5px;line-height:1.6;color:#cdd6de;margin:3px 0 7px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;cursor:pointer}',
    '.fd-sum.open{-webkit-line-clamp:none;display:block}',
    '.fd-g{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:10.5px}',
    '.fd-g .gl{flex:0 0 26px;color:var(--dim,#8a93a3);font-family:var(--mono,monospace)}',
    '.fd-g .gt{flex:1;position:relative;height:9px;border-radius:5px;min-width:60px}',
    '.fd-g .gv{flex:0 0 auto;font-family:var(--mono,monospace);font-size:11px}',
    '.fd-g .gk{font-size:10.5px;color:var(--dim,#8a93a3)}',
    '.fd-kw{display:inline-block;border:1px solid var(--line,#1f2937);border-radius:999px;padding:1px 8px;font-size:10px;color:var(--dim,#8a93a3);margin:3px 3px 0 0}',
    '.fd-meta{display:flex;gap:8px;flex-wrap:wrap;font-family:var(--mono,monospace);font-size:9.5px;color:var(--dim,#8a93a3);margin-top:6px;align-items:center}',
    '.fd-meta a{color:var(--accent,#2bc0d4);text-decoration:none}',
    '.fd-today{display:flex;gap:14px;align-items:center;flex-wrap:wrap;background:var(--panel2,#0d131c);border:1px solid var(--line,#1f2937);border-radius:9px;padding:9px 12px;margin-bottom:8px}',
    '.fd-today .tn{font-family:var(--mono,monospace);font-size:17px;font-weight:800}',
    '.fd-today .tl{font-size:10.5px;color:var(--dim,#8a93a3);line-height:1.5}',
    /* 캘린더 */
    '.fd-cal .crow{display:flex;gap:8px;align-items:flex-start;padding:6px 4px;border-bottom:1px solid rgba(31,41,55,.5);font-size:12px}',
    '.fd-cal .crow:last-child{border-bottom:none}',
    '.fd-cal .crow.today{background:rgba(43,192,212,.07);border-radius:6px}',
    '.fd-cal .crow.done{opacity:.45}',
    '.fd-cal .crow.cancelled{opacity:.4;text-decoration:line-through}',
    '.fd-cal .cd{flex:0 0 62px;font-family:var(--mono,monospace);font-size:10px;color:var(--dim,#8a93a3);padding-top:2px}',
    '.fd-cal .ci{flex:0 0 16px;text-align:center}',
    '.fd-cal .ct{flex:1;line-height:1.4;min-width:0}',
    '.fd-cal .cs{font-family:var(--mono,monospace);font-size:9.5px;color:#f5c542;flex:0 0 auto}',
    '.fd-cal .cx{font-size:10px;color:var(--dim,#8a93a3);display:block;margin-top:2px}',
    '.fd-wrap .cav{position:relative;display:inline-grid;place-items:center;flex-shrink:0;width:32px;height:32px;padding:0;border:1px solid currentColor;border-radius:50%;overflow:hidden;font-family:inherit;font-size:11px;font-weight:800;vertical-align:middle;cursor:pointer;touch-action:manipulation}',
    '.fd-wrap .cav img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center top}.fd-wrap .cav:focus-visible{outline:2px solid var(--accent,#2bc0d4);outline-offset:3px}',
    '.fd-cal .cav{width:24px;height:24px;font-size:9px;margin-right:5px}',
    '.fd-cal .cblk{background:rgba(138,147,163,.14);border-left:3px solid #8a93a3;border-radius:5px;padding:5px 8px;font-size:11px;color:var(--dim,#8a93a3);margin:6px 0}',
    /* 시장반응 */
    '.fd-sig{display:flex;align-items:center;gap:8px;padding:5px 0;font-size:11.5px}',
    '.fd-sig .sn{flex:0 0 74px;color:#cdd6de}',
    '.fd-sig .sb{flex:1;position:relative;height:16px;min-width:80px}',
    '.fd-sig .sv{flex:0 0 122px;text-align:right;font-family:var(--mono,monospace);font-size:10.5px}',
    '.fd-stack{display:flex;height:20px;border-radius:4px;overflow:hidden;margin:3px 0}',
    '.fd-stack i{display:block;height:100%;font-style:normal;font-size:9px;line-height:20px;text-align:center;color:#0b0b0b;font-family:var(--mono,monospace);font-weight:700;overflow:hidden}',
    '.fd-stack.prev{height:7px;opacity:.45;margin-bottom:1px}',
    '.fd-kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(88px,1fr));gap:8px;margin:8px 0}',
    '.fd-kpi div{background:var(--panel2,#0d131c);border:1px solid var(--line,#1f2937);border-radius:8px;padding:7px 9px}',
    '.fd-kpi span{display:block;font-size:9.5px;color:var(--dim,#8a93a3)}',
    '.fd-kpi b{font-family:var(--mono,monospace);font-size:14px}',
    /* TACO */
    '.fd-taco .tsum{font-size:14.5px;font-weight:700;line-height:1.5;color:#e6edf3;margin:2px 0 12px}',
    '.fd-taco svg.fd-arc{width:100%;height:auto;display:block}',
    '.fd-tcard{border-left:3px solid #8a93a3;background:var(--panel2,#0d131c);border-radius:7px;padding:7px 10px;margin-bottom:6px;font-size:11.5px;line-height:1.5}',
    '.fd-tl{display:flex;gap:0;align-items:center;flex-wrap:wrap;margin:6px 0}',
    '.fd-tl .st{display:flex;align-items:center;gap:5px;font-size:10.5px;color:var(--dim,#8a93a3)}',
    '.fd-tl .sd{width:9px;height:9px;border-radius:50%}',
    '.fd-tl .sl{width:22px;height:1px;background:var(--line,#1f2937)}',
    '.fd-tb{width:100%;border-collapse:collapse;font-size:11px}',
    '.fd-tb th,.fd-tb td{text-align:left;padding:4px 6px;border-bottom:1px solid rgba(31,41,55,.6)}',
    '.fd-tb th{color:var(--dim,#8a93a3);font-weight:600;font-size:10px}',
    '.fd-tb td.n{text-align:right;font-family:var(--mono,monospace)}',
    /* 모달 */
    '.fd-modal{position:fixed;inset:0;background:rgba(3,6,10,.72);-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);z-index:60;overflow:hidden;overscroll-behavior:contain}',
    '.fd-sheet{position:relative;display:flex;flex-direction:column;width:calc(100% - 32px);max-width:760px;height:min(720px,88vh);margin:6vh auto;background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:16px;overflow:hidden;padding:18px 20px;animation:fd-enter .18s ease-out}',
    '.fd-mhead{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px;padding-right:38px;flex-shrink:0}',
    '.fd-mhead>svg{flex-shrink:0}.fd-mhead>div{min-width:0}.fd-mhead h3,.fd-mhead .mt{overflow-wrap:anywhere}',
    '.fd-tabs{flex-shrink:0;gap:6px;flex-wrap:nowrap;overflow-x:auto;padding:3px 0 8px;margin:0 0 6px!important}',
    '.fd-body{min-height:0;overflow:auto;overscroll-behavior:contain;scrollbar-gutter:stable;padding:0 3px 10px}',
    '.fd-mhead h3{font-size:17px;font-weight:800}',
    '.fd-mhead .mt{font-size:11.5px;color:var(--dim,#8a93a3)}',
    '.fd-x{position:absolute;top:14px;right:14px;background:none;border:1px solid var(--line,#1f2937);color:var(--dim,#8a93a3);border-radius:10px;width:40px;height:40px;cursor:pointer;font-size:15px;font-family:inherit;touch-action:manipulation}',
    '.fd-x:hover{color:var(--ink,#e6edf3);border-color:var(--accent,#2bc0d4)}',
    '.fd-pane{display:none}',
    '.fd-pane.on{display:block}',
    '.fd-htb{width:100%;border-collapse:collapse;font-size:11.5px;margin-top:6px}',
    '.fd-htb th,.fd-htb td{text-align:left;padding:5px 7px;border-bottom:1px solid rgba(31,41,55,.6)}',
    '.fd-htb th{color:var(--dim,#8a93a3);font-weight:600;font-size:10px}',
    '.fd-htb td.n{text-align:right;font-family:var(--mono,monospace)}',
    '.fd-table-scroll{max-width:100%;overflow-x:auto;overscroll-behavior-x:contain;margin-top:6px;border-radius:6px}.fd-table-scroll .fd-htb{margin-top:0;min-width:560px}',
    '.fd-htb th{white-space:nowrap}.fd-htb td{overflow-wrap:anywhere}.fd-htb td.n{white-space:nowrap}.fd-kpi b{overflow-wrap:anywhere}',
    '.fd-sec{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--dim,#8a93a3);font-weight:700;margin:14px 0 6px}',
    /* 반응형 */
    '@media(max-width:1100px){.fd-grid{grid-template-columns:1fr}.fd-grid2{grid-template-columns:1fr}}',
    '@media(max-width:700px){',
    '.fd-node .fd-ring{r:16px}.fd-node .fd-bgc{r:14px}.fd-node .fd-img{x:-14px;y:-14px;width:28px;height:28px}',
    '.fd-name{display:none}.fd-sig .sn{flex:0 0 56px}',
    '.fd-card{padding:14px 12px}.fd-sheet{position:absolute;bottom:0;width:100%;margin:0;border-radius:16px 16px 0 0;height:88vh;height:88dvh;padding:16px 12px max(12px,env(safe-area-inset-bottom))}',
    '.fd-chip,.fd-btn{min-height:44px}.fd-x{width:44px;height:44px;top:10px;right:10px}.fd-mhead{gap:8px;padding-right:44px}.fd-mhead h3{font-size:16px}.fd-sig{flex-wrap:wrap}.fd-sig .sv{flex-basis:auto;margin-left:auto}.fd-ts{font-size:9px}',
    '.fd-wrap .cav{min-width:44px;min-height:44px}',
    '.fd-cal .crow{font-size:11.5px}.fd-kpi{grid-template-columns:repeat(2,1fr)}',
    '}',
    '@keyframes fd-enter{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}',
    '@media(prefers-reduced-motion:reduce){.fd-wrap *,.fd-modal *{transition:none!important;animation:none!important;scroll-behavior:auto!important}.fd-node:hover .fd-scale,.fd-node:focus .fd-scale{transform:none}.fd-node.chair .fd-ring{filter:none}}'
  ];

  var cssDone = false;
  function injectCSS() {
    if (cssDone) return;
    if (document.getElementById && document.getElementById('fd-css')) { cssDone = true; return; }
    var st = document.createElement('style');
    st.id = 'fd-css';
    if (st.setAttribute) st.setAttribute('id', 'fd-css');
    st.textContent = CSS.join('\n');
    var host = document.head || document.documentElement || document.body;
    if (host && host.appendChild) host.appendChild(st);
    cssDone = true;
  }

  /* ══════════════════ 2. 상수 ══════════════════ */
  var HAWK = '#f5a623', DOVE = '#3a8dff', NEUT = '#c9d1d9';
  var UP = '#ff5d6c', DOWN = '#4ea1ff', FLAT = '#8a93a3', ACC = '#2bc0d4';
  var VW = 1000, VH = 460, PL = 64, PR = 28, PT = 36, PB = 96;
  var PW = VW - PL - PR;            // 908
  var PH = VH - PT - PB;            // 328
  var R = 22, RPAD = 3;
  var YTOP = PT + R, YBOT = PT + PH - R;   // 58 .. 342
  var DEV_ARROW = 0.15;             // |delta_30d| ≥ 0.15 → 화살표(계약)
  var NEUT_EDGE = 0.15;             // 링 색 ±0.15 경계(계약)
  var KIND_KO = { speech: '연설', testimony: '의회증언', interview: '인터뷰', qna: '질의응답', panel: '패널', statement: '성명', dissent: '반대성명', headline: '헤드라인' };
  var CAL_ICON = { fomc: '🏛', speech: '🎤', testimony: '🏛', treasury: '💵', data: '📊', minutes: '📝', beige: '📖', blackout: '⛔', other: '·' };
  var ORG_KO = { board: '이사회', frb: '지역연은' };
  var CLS_KO = { cash: '현금', money_market: 'MMF', fund_equity_us: '미국주식펀드', fund_equity_intl: '해외주식펀드', fund_bond: '채권펀드', fund_balanced: '혼합형펀드', stock: '개별주식', etf: 'ETF', private_fund: '사모펀드', real_estate: '부동산', retirement_annuity: '연금·연금보험', '529': '529 학자금', loan_receivable: '대여금', crypto: '가상자산', other: '기타' };
  var OWN_KO = { filer: '본인', spouse: '배우자', joint: '공동', dependent: '피부양자' };
  var TXN_KO = { Sale: '매도', Purchase: '매수', Exchange: '교환' };
  var PATH_K = ['-50', '-25', '0', '+25', '+50'];
  var PATH_C = { '-50': '#3a8dff', '-25': '#8fbcff', '0': '#c9d1d9', '+25': '#f5a623', '+50': '#ff8a3d' };
  var ACT_C = { THREAT: '#ff4d5e', RETREAT: '#f5c542', HOLD: '#8a93a3' };
  var PHASE_C = { threat: '#ff4d5e', react: '#2bc0d4', hold: '#8a93a3', retreat: '#f5c542' };

  /* ══════════════════ 3. 헬퍼 ══════════════════ */
  var ENT = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ENT[c]; }); }
  function isN(v) { return typeof v === 'number' && isFinite(v); }
  function nf(v, d) { return isN(v) ? v.toFixed(d == null ? 2 : d) : '—'; }
  function sf(v, d) { return isN(v) ? (v > 0 ? '+' : '') + v.toFixed(d == null ? 2 : d) : '—'; }
  function n2(v) { // 최대 2자리, 뒤 0 제거 (0.708 → 0.71 · 0.5 → 0.5 · 1.0 → 1)
    if (!isN(v)) return '—';
    var s = v.toFixed(2);
    if (s.indexOf('.') >= 0) s = s.replace(/0+$/, '').replace(/\.$/, '');
    return s;
  }
  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function arr(a) { return Array.isArray(a) ? a : []; }
  function obj(o) { return (o && typeof o === 'object') ? o : {}; }
  function str(s) { return (typeof s === 'string' && s.length) ? s : ''; }
  function get(o, k) { return (o && typeof o === 'object' && o[k] != null) ? o[k] : null; }
  function hostOf(u) { var m = /^https?:\/\/([^\/?#]+)/i.exec(String(u || '')); return m ? m[1].replace(/^www\./, '') : ''; }
  function attr(v) { return esc(v == null ? '' : v); }

  /* KST(UTC+9, DST 없음) — Intl 우선, 실패 시 고정오프셋 폴백 */
  var _dtf = null, _dtfTried = false;
  function kstParts(ts) {
    if (!isN(ts)) return null;
    if (!_dtfTried) {
      _dtfTried = true;
      try {
        _dtf = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', weekday: 'short', hour12: false });
      } catch (e) { _dtf = null; }
    }
    if (_dtf && _dtf.formatToParts) {
      try {
        var ps = _dtf.formatToParts(new Date(ts * 1000)), o = {};
        for (var i = 0; i < ps.length; i++) o[ps[i].type] = ps[i].value;
        var H = parseInt(o.hour, 10); if (H === 24) H = 0;
        return { y: +o.year, m: +o.month, d: +o.day, H: H, M: +o.minute, w: String(o.weekday || '').replace(/[^가-힣]/g, '') };
      } catch (e2) { /* 폴백 */ }
    }
    var dd = new Date((Math.round(ts) + 32400) * 1000);
    return { y: dd.getUTCFullYear(), m: dd.getUTCMonth() + 1, d: dd.getUTCDate(), H: dd.getUTCHours(), M: dd.getUTCMinutes(), w: '일월화수목금토'.charAt(dd.getUTCDay()) };
  }
  function p2(n) { return (n < 10 ? '0' : '') + n; }
  function kstHM(ts) { var p = kstParts(ts); return p ? p2(p.H) + ':' + p2(p.M) : '—'; }
  function kstMD(ts) { var p = kstParts(ts); return p ? p2(p.m) + '/' + p2(p.d) : '—'; }
  function kstYMD(ts) { var p = kstParts(ts); return p ? p.y + '-' + p2(p.m) + '-' + p2(p.d) : '—'; }
  function kstFull(ts) { var p = kstParts(ts); return p ? p2(p.m) + '/' + p2(p.d) + ' ' + p2(p.H) + ':' + p2(p.M) : '—'; }
  function kstDayKey(ts) { return kstYMD(ts); }
  /* KST 자정(epoch 초) */
  function kstMidnight(ts) {
    var p = kstParts(ts); if (!p) return null;
    return Math.floor(Date.UTC(p.y, p.m - 1, p.d, 0, 0, 0) / 1000) - 32400;
  }
  function agoKo(ts, now) {
    if (!isN(ts) || !isN(now)) return '';
    var s = now - ts; if (s < 0) return '예정';
    if (s < 60) return '방금';
    if (s < 3600) return Math.floor(s / 60) + '분 전';
    if (s < 86400) return Math.floor(s / 3600) + '시간 전';
    return Math.floor(s / 86400) + '일 전';
  }
  function confDots(c) {
    if (!isN(c)) return '—';
    var n = clamp(Math.round(c / 0.25), 0, 4), s = '', i;
    for (i = 0; i < 4; i++) s += (i < n ? '●' : '○');
    return s;
  }
  function usd(v) {
    if (!isN(v)) return '—';
    if (v >= 1e6) return '$' + n2(v / 1e6) + 'M';
    if (v >= 1e3) return '$' + Math.round(v / 1e3) + 'K';
    return '$' + Math.round(v);
  }
  function rangeUsd(lo, hi) {
    if (!isN(lo) && !isN(hi)) return '—';
    if (isN(lo) && !isN(hi)) return usd(lo) + '+';
    if (!isN(lo)) return '~' + usd(hi);
    return usd(lo) + '–' + usd(hi);
  }
  function unitStr(v, unit, d) {
    if (!isN(v)) return '—';
    return (v > 0 ? '+' : '') + v.toFixed(d == null ? 2 : d) + (unit === 'bp' ? 'bp' : '%');
  }

  /* 성향 색 */
  function scoreColor(s, neutralGray) {
    if (!isN(s)) return NEUT;
    if (neutralGray) return Math.abs(s) < NEUT_EDGE ? NEUT : (s > 0 ? HAWK : DOVE);
    return s >= 0 ? HAWK : DOVE;
  }
  function labelColor(label, s, neutralGray) {
    if (!neutralGray) return isN(s) ? (s >= 0 ? HAWK : DOVE) : NEUT;
    if (label === 'hawk' || label === 'very_hawk') return HAWK;
    if (label === 'dove' || label === 'very_dove') return DOVE;
    if (label === 'neutral') return NEUT;
    return scoreColor(s, true);
  }
  function xOf(s) { return PL + (clamp(isN(s) ? s : 0, -1, 1) + 1) / 2 * PW; }

  /* ══════════════════ 4. 레이아웃 (테스트 훅 __fedLayout) ══════════════════ */
  function hfOf(p, win) {
    var h = p && p.hf;
    return (h && isN(h[win])) ? h[win] : 0;
  }
  function passGroup(r, g) {
    if (!g || g === 'all' || !r) return true;
    if (g === 'voter') return r.voter === true;
    if (g === 'board') return r.org === 'board';
    if (g === 'frb') return r.org === 'frb';
    return true;
  }
  function layoutNodes(people, rosterPeople, opt) {
    opt = obj(opt);
    var win = str(opt.hf) || '30d';
    var logScale = opt.scale === 'log2';
    var group = str(opt.group) || 'all';
    var plist = arr(people), rlist = arr(rosterPeople), i, j;
    var pos = {};
    for (i = 0; i < plist.length; i++) if (plist[i] && plist[i].id != null) pos[plist[i].id] = plist[i];

    var base = [];
    if (rlist.length) {
      for (i = 0; i < rlist.length; i++) {
        var r = rlist[i];
        if (!r || r.plot !== true) continue;
        if (!passGroup(r, group)) continue;
        base.push({ r: r, p: pos[r.id] || null });
      }
    } else {
      for (i = 0; i < plist.length; i++) base.push({ r: null, p: plist[i] });
    }

    var hfMax = isN(opt.hfMax) && opt.hfMax > 0 ? opt.hfMax : 0;
    if (!hfMax) { for (i = 0; i < base.length; i++) { var v = hfOf(base[i].p, win); if (v > hfMax) hfMax = v; } }
    if (!(hfMax > 0)) hfMax = 1;

    function frac(v) {
      var f = logScale ? (Math.log(1 + Math.max(0, v)) / Math.log(1 + hfMax)) : (Math.sqrt(Math.max(0, v)) / Math.sqrt(hfMax));
      return clamp(isN(f) ? f : 0, 0, 1);
    }

    var nodes = [];
    for (i = 0; i < base.length; i++) {
      var b = base[i], p = b.p, ro = b.r;
      var pending = !p;
      var s = p && isN(p.pos) ? p.pos : (ro && ro.seed && isN(ro.seed.value) ? ro.seed.value : 0);
      var hfv = pending ? 0 : hfOf(p, win);
      var x = xOf(s);
      var y = YBOT - (YBOT - YTOP) * frac(hfv);
      nodes.push({
        id: String((ro && ro.id) || (p && p.id) || ('n' + i)),
        x: x, x0: x, y: clamp(y, YTOP, YBOT), y0: clamp(y, YTOP, YBOT),
        s: pending ? null : (isN(s) ? s : null), seed: s, hf: hfv, hfMax: hfMax,
        pending: pending, r: ro, p: p,
        label: (p && str(p.label)) || '', conf: p && isN(p.conf) ? p.conf : null,
        delta: p && isN(p.delta_30d) ? p.delta_30d : null,
        chair: !!(ro && ro.role === 'chair'),
        voter: ro ? ro.voter === true : true,
        nameY: 38, nameSize: 11.5
      });
    }

    /* y-push 완화 60회 — x 는 절대 이동하지 않는다 */
    var MIN = 2 * (R + RPAD);
    for (var it = 0; it < 60; it++) {
      var moved = false;
      for (i = 0; i < nodes.length; i++) {
        for (j = i + 1; j < nodes.length; j++) {
          var a = nodes[i], c = nodes[j];
          var dx = a.x - c.x; if (Math.abs(dx) >= MIN) continue;
          var need = Math.sqrt(Math.max(0, MIN * MIN - dx * dx));
          var dy = a.y - c.y, ady = Math.abs(dy);
          if (ady >= need) continue;
          var push = (need - ady) / 2;
          var dir = dy === 0 ? ((i % 2) ? 1 : -1) : (dy > 0 ? 1 : -1);
          a.y = clamp(a.y + dir * push, YTOP, YBOT);
          c.y = clamp(c.y - dir * push, YTOP, YBOT);
          moved = true;
        }
      }
      if (!moved) break;
    }

    /* 잔여 노드 겹침 집계 */
    var overlaps = [];
    for (i = 0; i < nodes.length; i++) for (j = i + 1; j < nodes.length; j++) {
      var ddx = nodes[i].x - nodes[j].x, ddy = nodes[i].y - nodes[j].y;
      if (Math.sqrt(ddx * ddx + ddy * ddy) < MIN - 0.5) overlaps.push([nodes[i].id, nodes[j].id]);
    }

    /* 라벨 충돌: |dx|<8 쌍은 위/아래 교대 → 사각형 충돌이면 홀수번째 위로 → 그래도 겹치면 font 10 */
    for (i = 0; i < nodes.length; i++) for (j = i + 1; j < nodes.length; j++) {
      if (Math.abs(nodes[i].x - nodes[j].x) < 8 && Math.abs(nodes[i].y - nodes[j].y) < MIN) {
        nodes[j].nameY = nodes[i].nameY === 38 ? -30 : 38;
      }
    }
    function lrect(n) {
      var w = 6.4 * String(nameOf(n)).length, h = 13;
      return { x1: n.x - w / 2, x2: n.x + w / 2, y1: n.y + n.nameY - h, y2: n.y + n.nameY + 3 };
    }
    function hit(A, B) { return !(A.x2 < B.x1 || B.x2 < A.x1 || A.y2 < B.y1 || B.y2 < A.y1); }
    var clash = [];
    for (i = 0; i < nodes.length; i++) for (j = i + 1; j < nodes.length; j++) {
      if (hit(lrect(nodes[i]), lrect(nodes[j]))) { if (j % 2 === 1) nodes[j].nameY = -30; }
    }
    for (i = 0; i < nodes.length; i++) for (j = i + 1; j < nodes.length; j++) {
      if (hit(lrect(nodes[i]), lrect(nodes[j]))) { nodes[i].nameSize = 10; nodes[j].nameSize = 10; clash.push([nodes[i].id, nodes[j].id]); }
    }
    nodes.overlaps = overlaps;
    nodes.labelClashes = clash;
    nodes.hfMax = hfMax;
    return nodes;
  }
  function nameOf(n) {
    var r = n.r;
    return (r && (str(r.short) || str(r.name))) || String(n.id);
  }
  function initialsOf(n) {
    var r = n.r;
    if (r && str(r.initials)) return r.initials;
    var nm = (r && str(r.name)) || String(n.id);
    var ps = nm.split(/\s+/);
    if (ps.length >= 2) return (ps[0].charAt(0) + ps[ps.length - 1].charAt(0)).toUpperCase();
    return nm.slice(0, 2).toUpperCase();
  }

  /* ══════════════════ 5. 사진 정책 · 개별 이미지 폴백 ══════════════════ */
  function photoUsable(r, policyMode) {
    if (!r || !str(r.photo)) return false;
    if (r._fdPortraitVerified === true) return true;
    if (policyMode === 'internal') return true;
    return r.photo_license === 'us_gov_pd_presumed';   // pd_only(기본)
  }
  function bindPhotos(root) {
    each(qa(root, 'image.fd-photo,img.fd-photo'), function (im) {
      im.addEventListener('error', function () {
        // 이니셜을 사진 아래에 항상 두므로 느린 요청도 기다림 없이 개별 복구된다.
        if (im.parentNode) im.parentNode.removeChild(im);
      }, { once: true });
    });
  }
  function withPortraits(data) {
    var D = Object.assign({}, obj(data)), roster = obj(D.roster), photos = obj(obj(D.photos).people);
    if (!D.roster) return D;
    D.roster = Object.assign({}, roster);
    D.roster.people = arr(roster.people).map(function (r) {
      var p = obj(photos[r.id]), copy = Object.assign({}, r);
      copy._fdPortraitVerified = false;
      if (p.name === r.name && p.usage === 'official_attributed' && /^[a-z0-9_-]+$/.test(r.id) &&
          new RegExp('^data/fed/portraits/' + r.id + '\\.(?:jpe?g|png|webp)$').test(str(p.photo)) &&
          /^https:\/\/[a-z0-9.-]+\//i.test(str(p.source_url)) && /^https:\/\/[a-z0-9.-]+\//i.test(str(p.source_page))) {
        copy.photo = p.photo;
        copy.photo_credit = str(p.attribution);
        copy.photo_source_page = p.source_page;
        copy._fdPortraitVerified = true;
        copy.notes = arr(r.notes).filter(function (note) {
          return note !== '사진은 1시간 만료 S3 서명 URL → 매번 페이지에서 재추출' &&
            note !== 'kansascityfed.org 봇게이트(curl 기본 UA)';
        });
      }
      return copy;
    });
    return D;
  }

  function rPeople(ST, D) {
    var people = arr(obj(D.roster).people), mode = obj(obj(D.roster).photo_policy).mode || 'pd_only';
    if (!people.length) return '';
    var h = '<div class="fd-card wide" id="fdPeople"><div class="fd-h"><b>연준 인사</b><span class="fd-legend">' + people.length + '명 · 인물을 선택해 프로필 보기</span></div><div class="fd-people">';
    each(people, function (r) {
      var name = str(r.name) || r.id, short = str(r.short) || name, ring = ringOfPid(D, r.id, ST.neutralRing);
      h += '<button type="button" class="fd-person" data-profile="' + attr(r.id) + '" aria-label="' + attr(name + ' 프로필 열기') + '"><span class="fd-avatar" style="--fd-ring:' + ring + '" aria-hidden="true">' + esc(initialsOf({ r: r, id: r.id }));
      if (photoUsable(r, mode)) h += '<img class="fd-photo" src="' + attr(r.photo) + '" width="40" height="40" loading="lazy" decoding="async" alt="">';
      h += '</span><span class="fd-person-text"><b>' + esc(short) + '</b><small>' + esc(str(r.bank) || ORG_KO[r.org] || str(r.title)) + (r.voter === true ? ' · 투표권' : '') + '</small></span></button>';
    });
    return h + '</div></div>';
  }

  /* ══════════════════ 6. 공통 조각 ══════════════════ */
  function chip(k, v, label, on, title) {
    return '<button type="button" class="fd-chip' + (on ? ' on' : '') + '" data-fk="' + attr(k) + '" data-fv="' + attr(v) + '"' +
      ' aria-pressed="' + (on ? 'true' : 'false') + '"' + (title ? ' title="' + attr(title) + '"' : '') + '>' + esc(label) + '</button>';
  }
  function defsSVG() {
    return '<svg class="fd-defs" width="0" height="0" aria-hidden="true" focusable="false" style="position:absolute">' +
      '<defs><linearGradient id="fdGrad" x1="0" y1="0" x2="1" y2="0">' +
      '<stop offset="0" stop-color="#3a8dff"/><stop offset="0.5" stop-color="#ffffff"/><stop offset="1" stop-color="#f5a623"/>' +
      '</linearGradient>' +
      '<linearGradient id="fdTacoG" x1="0" y1="0" x2="1" y2="0">' +
      '<stop offset="0" stop-color="#7a4a1a"/><stop offset="1" stop-color="#f5c542"/></linearGradient>' +
      '</defs></svg>';
  }
  /* 값 게이지 (ABS/REL 공용) — dom = [-1,1] */
  function gaugeRow(kind, val, valLabel, color, trackFill, baseVal, baseColor) {
    var pctv = isN(val) ? ((clamp(val, -1, 1) + 1) / 2 * 100) : null;
    var pctb = isN(baseVal) ? ((clamp(baseVal, -1, 1) + 1) / 2 * 100) : null;
    var h = '<div class="fd-g"><span class="gl">' + esc(kind) + '</span><span class="gt" style="background:' + trackFill + '">';
    h += '<i style="position:absolute;left:50%;top:-2px;width:1px;height:13px;background:#6b7280;display:block"></i>';
    if (pctb != null) h += '<i style="position:absolute;left:' + nf(pctb, 1) + '%;top:2px;width:5px;height:5px;border-radius:50%;background:' + baseColor + ';transform:translateX(-2.5px);display:block"></i>';
    if (pctv != null) h += '<i style="position:absolute;left:' + nf(pctv, 1) + '%;top:-1.5px;width:12px;height:12px;border-radius:50%;background:' + color + ';border:2px solid #0d131c;transform:translateX(-6px);display:block"></i>';
    h += '</span><span class="gv" style="color:' + color + '">' + (isN(val) ? sf(val, 2) : '—') + '</span>';
    h += '<span class="gk">' + esc(valLabel || '—') + '</span></div>';
    return h;
  }

  /* ══════════════════ 7. fd-dist (성향분포 SVG) ══════════════════ */
  function rDist(ST, D) {
    var positions = D.positions, roster = D.roster;
    var head = '<div class="fd-h"><b>🎯 FOMC 성향 분포</b>' +
      (positions && str(positions.badge) ? '<span class="fd-bd" title="' + attr(validTip(positions)) + '">' + esc(positions.badge) + '</span>' : '') +
      '<span class="fd-legend" style="margin-left:auto">링 <span style="color:' + HAWK + '">주황=매파</span> · <span style="color:' + DOVE + '">파랑=비둘기</span> · 회색=중립 · 점선=비투표 · 세로 점선=FOMC 평균</span></div>';
    if (!positions) {   // 파일 자체가 없으면 카드별 '준비 중'(개별 pid 결측은 '채점 대기' 노드로 그린다)
      return '<div class="fd-card dark fd-dist" id="fdDist">' + head + '<p class="fd-hint">성향 데이터 준비 중…</p></div>';
    }
    var nodes = layoutNodes(positions ? arr(positions.people) : [], roster ? arr(roster.people) : [],
      { hf: ST.hf, scale: ST.scale, group: ST.group, hfMax: positions && obj(positions.hf_max)[ST.hf] });
    ST._nodes = nodes;
    if (!nodes.length) {
      return '<div class="fd-card dark fd-dist" id="fdDist">' + head + '<p class="fd-hint">표시할 인사가 없습니다 — 성향 데이터 준비 중…</p>' + distChips(ST) + '</div>';
    }

    var s = '<svg class="fd-plot" viewBox="0 0 ' + VW + ' ' + VH + '" preserveAspectRatio="xMidYMid meet" role="img" aria-label="FOMC 위원 성향 분포">';
    s += '<rect x="0" y="0" width="' + VW + '" height="' + VH + '" fill="#0b0b0b"/>';
    /* x 눈금 세로 점선 */
    var ticks = [-1, -0.5, 0, 0.5, 1], i;
    for (i = 0; i < ticks.length; i++) {
      if (ticks[i] === 0) continue;
      s += '<line x1="' + nf(xOf(ticks[i]), 1) + '" y1="' + PT + '" x2="' + nf(xOf(ticks[i]), 1) + '" y2="' + (PT + PH) + '" stroke="#3a3a3a" stroke-width="1" stroke-dasharray="2 5"/>';
    }
    /* Neutral 실선 */
    s += '<line x1="' + nf(xOf(0), 1) + '" y1="' + PT + '" x2="' + nf(xOf(0), 1) + '" y2="' + (PT + PH) + '" stroke="#6b7280" stroke-width="1"/>';
    s += '<text x="' + nf(xOf(0), 1) + '" y="' + (PT - 10) + '" text-anchor="middle" font-size="11" fill="#9aa3b2">Neutral</text>';
    /* FOMC Average */
    var avg = obj(positions && positions.fomc_avg);
    var avgV = isN(avg.value) ? avg.value : null;
    if (avgV != null) {
      s += '<line x1="' + nf(xOf(avgV), 1) + '" y1="' + PT + '" x2="' + nf(xOf(avgV), 1) + '" y2="' + (PT + PH + 14) + '" stroke="' + HAWK + '" stroke-width="1.5" stroke-dasharray="6 5"/>';
      s += '<text x="' + nf(xOf(avgV), 1) + '" y="' + (PT + PH + 46) + '" text-anchor="middle" font-size="11" fill="' + HAWK + '">FOMC Average ▲ ' + sf(avgV, 3) + '</text>';
    }
    /* y축 */
    s += '<text x="18" y="' + (PT + PH / 2) + '" text-anchor="middle" font-size="12" fill="#9aa3b2" transform="rotate(-90 18 ' + (PT + PH / 2) + ')">News Headline Frequency</text>';
    var hm = nodes.hfMax;
    var ylab = [0, Math.round(hm / 2), Math.round(hm)];
    for (i = 0; i < 3; i++) {
      var f = ST.scale === 'log2' ? (Math.log(1 + ylab[i]) / Math.log(1 + hm)) : (Math.sqrt(ylab[i]) / Math.sqrt(hm));
      var yy = YBOT - (YBOT - YTOP) * clamp(isN(f) ? f : 0, 0, 1);
      s += '<text x="' + (PL - 10) + '" y="' + nf(yy + 4, 1) + '" text-anchor="end" font-size="10" fill="#6b7280">' + ylab[i] + '</text>';
    }
    /* 그라데이션 바 */
    var by = PT + PH + 14;
    s += '<rect x="' + PL + '" y="' + by + '" width="' + PW + '" height="14" rx="7" fill="url(#fdGrad)"/>';
    s += '<text x="' + PL + '" y="' + (by + 30) + '" font-size="12" fill="' + DOVE + '">🕊 -1  Doves</text>';
    s += '<text x="' + nf(xOf(0), 1) + '" y="' + (by + 30) + '" text-anchor="middle" font-size="12" fill="#cfd6df">Neutral</text>';
    s += '<text x="' + (PL + PW) + '" y="' + (by + 30) + '" text-anchor="end" font-size="12" fill="' + HAWK + '">Hawks  1 🦅</text>';
    for (i = 0; i < ticks.length; i++) {
      s += '<text x="' + nf(xOf(ticks[i]), 1) + '" y="' + (by + 44) + '" text-anchor="middle" font-size="9.5" fill="#5b6474">' + ticks[i] + '</text>';
    }
    /* 노드 */
    var policyMode = (roster && obj(roster.photo_policy).mode) || 'pd_only';
    var stItems = D.statements ? arr(D.statements.items) : [];
    for (i = 0; i < nodes.length; i++) s += nodeSVG(nodes[i], ST, policyMode, stItems);
    s += '</svg>';

    var foot = '<div class="fd-foot">y축 = 최근 헤드라인 빈도(' + esc(ST.hf) + ', ' + (ST.scale === 'log2' ? 'log2' : 'sqrt') + ' 스케일, 상한 ' + nf(hm, 0) + ') · x축 = 성향 점수(백엔드 산출, 겹침회피로 이동하지 않음)' +
      (avgV != null ? ' · FOMC Average ' + sf(avgV, 3) + '(' + esc(str(avg.method) || '가중평균') + ', n=' + (isN(avg.n_voters) ? avg.n_voters : '—') + ')' : '') +
      staleNote(positions) + '</div>';
    return '<div class="fd-card dark fd-dist" id="fdDist">' + head + s + distChips(ST) + foot + '</div>';
  }
  function validTip(positions) {
    var m = obj(obj(positions.validation).measured), ks = Object.keys(m), out = [], i;
    for (i = 0; i < ks.length; i++) out.push(ks[i] + '=' + (m[ks[i]] == null ? '—' : m[ks[i]]));
    return out.length ? ('검증 실측 · ' + out.join(' · ')) : '검증 실측값 없음';
  }
  function staleNote(f) {
    var st = f && arr(f.quality && f.quality.stale);
    return st && st.length ? ' · ⚠ 직전값 보존(stale): ' + esc(st.join(', ')) : '';
  }
  function distChips(ST) {
    return '<div class="fd-chips">' +
      chip('group', 'all', '전체', ST.group === 'all') + chip('group', 'voter', '투표권', ST.group === 'voter') +
      chip('group', 'board', '이사회', ST.group === 'board') + chip('group', 'frb', '지역총재', ST.group === 'frb') +
      '<span class="sep"></span>' +
      chip('hf', '30d', '30d', ST.hf === '30d') + chip('hf', '90d', '90d', ST.hf === '90d') + chip('hf', '1y', '1y', ST.hf === '1y') +
      '<span class="sep"></span>' +
      chip('scale', ST.scale === 'sqrt' ? 'log2' : 'sqrt', ST.scale === 'sqrt' ? 'sqrt' : 'log2', true, 'y축 스케일 전환') +
      chip('arrows', ST.arrows ? '0' : '1', 'Δ화살표', ST.arrows) +
      chip('names', ST.names ? '0' : '1', '이름 표시', ST.names) +
      chip('neutralRing', ST.neutralRing ? '0' : '1', '중립 회색', ST.neutralRing, '끄면 부호로만 2색(첨부 이미지 원안)') +
      '</div>';
  }
  function nodeSVG(n, ST, policyMode, stItems) {
    var r = n.r, id = n.id;
    var ring = n.pending ? NEUT : labelColor(n.label, n.s, ST.neutralRing);
    var dash = (n.pending || !n.voter) ? ' stroke-dasharray="4 3"' : '';
    var sw = n.chair ? 3.5 : 2.5;
    var op = (isN(n.conf) && n.conf < 0.4) ? ' opacity="0.6"' : '';
    var nm = nameOf(n);
    var title = n.pending
      ? nm + ' · 채점 대기(성향 미확정 — 로스터 반영 후 첫 채점 전)'
      : nm + ' · 성향 ' + sf(n.s, 2) + ' · Δ30d ' + sf(n.delta, 2) + ' · 헤드라인 ' + nf(n.hf, 0) + '건/' + ST.hf;
    var g = '<g class="fd-node' + (n.chair ? ' chair' : '') + '" data-id="' + attr(id) + '" transform="translate(' + nf(n.x, 1) + ',' + nf(n.y, 1) + ')" tabindex="0" role="button" aria-label="' + attr(title) + '">';
    g += '<g class="fd-scale" style="color:' + ring + '">';
    g += '<circle class="fd-hit" r="24" fill="transparent"/>';
    g += '<circle class="fd-ring" r="25" fill="none" stroke="' + ring + '" stroke-width="' + sw + '"' + dash + op + '/>';
    g += '<circle class="fd-bgc" r="22" fill="' + ring + '2e"/>';
    var showImg = photoUsable(r, policyMode);
    g += '<text class="fd-init" y="5" text-anchor="middle" font-size="15" font-weight="800" fill="#e6edf3">' + esc(initialsOf(n)) + '</text>';
    if (showImg) {
      g += '<clipPath id="clip-' + attr(id) + '"><circle r="22"/></clipPath>';
      g += '<image class="fd-img fd-photo" href="' + attr(r.photo) + '" xlink:href="' + attr(r.photo) + '" x="-22" y="-22" width="44" height="44" preserveAspectRatio="xMidYMin slice" clip-path="url(#clip-' + attr(id) + ')"/>';
    }
    if (ST.names) g += '<text class="fd-name" y="' + n.nameY + '" text-anchor="middle" font-size="' + n.nameSize + '" fill="#ffffff" font-weight="650">' + esc(nm) + '</text>';
    if (ST.arrows && isN(n.delta) && Math.abs(n.delta) >= DEV_ARROW) {
      g += '<text x="20" y="-16" font-size="8" fill="' + (n.delta > 0 ? HAWK : DOVE) + '">' + (n.delta > 0 ? '▲' : '▼') + '</text>';
    }
    g += '<title>' + esc(title + lastLine(id, stItems)) + '</title>';
    g += '</g></g>';
    return g;
  }
  function lastLine(pid, items) {
    for (var i = 0; i < items.length; i++) if (items[i] && items[i].pid === pid) return ' · 최근: ' + str(items[i].title).slice(0, 46);
    return '';
  }

  /* ══════════════════ 8. fd-hero ══════════════════ */
  function toneOf(t) {   // tone_abs 없으면 S_abs 폴백, 둘 다 null 이면 null
    t = obj(t);
    if (isN(t.tone_abs)) return t.tone_abs;
    if (isN(t.S_abs)) return t.S_abs;
    return null;
  }
  function toneRelOf(t) {
    t = obj(t);
    if (isN(t.tone_rel)) return t.tone_rel;
    if (isN(t.S_rel)) return t.S_rel;
    return null;
  }
  function anyMock(D) {
    var ks = ['roster', 'positions', 'statements', 'calendar', 'reaction', 'taco'], i;
    for (i = 0; i < ks.length; i++) if (D[ks[i]] && D[ks[i]].mock === true) return true;
    return false;
  }
  function briefText(D) {
    var out = [], nf0 = obj(D.calendar).next_fomc, tdy = obj(obj(D.statements).today);
    if (nf0 && isN(nf0.d_days)) out.push('다음 FOMC 까지 ' + nf0.d_days + '일');
    if (nf0 && obj(nf0.blackout).active === true) out.push('현재 블랙아웃 기간');
    var n = isN(tdy.n) ? tdy.n : null, ta = toneOf(tdy);
    if (n != null) out.push('오늘 연준 발언 ' + n + '건' + (ta != null ? ', 평균 절대톤 ' + sf(ta, 2) : ''));
    var ts = str(obj(obj(D.taco).today).summary_ko);
    if (ts) out.push(ts);
    var sp = spyAsset(D.reaction);
    if (sp) out.push('기대 시장반응 ' + str(sp.name || sp.sym) + ' ' + unitStr(sp.exp, sp.unit, 2));
    return out.join('. ') + (out.length ? '.' : '연준 데이터 준비 중.');
  }
  function spyAsset(reaction) {
    var as = arr(obj(reaction).assets), i;
    for (i = 0; i < as.length; i++) if (as[i] && as[i].sym === 'SPY') return as[i];
    return as.length ? as[0] : null;
  }
  function rHero(ST, D) {
    var nf0 = obj(D.calendar).next_fomc;
    var h = '<div class="fd-hero"><h2>🏛 연준</h2>';
    if (nf0 && isN(nf0.d_days)) h += '<span class="fd-dcount" title="' + attr('다음 FOMC 성명 ' + kstFull(nf0.statement_ts) + ' KST') + '">D-' + nf0.d_days + '</span>';
    else h += '<span class="fd-bd">다음 FOMC —</span>';
    if (nf0 && obj(nf0.blackout).active === true) h += '<span class="fd-bd bo" title="' + attr(str(obj(nf0.blackout).start) + ' ~ ' + str(obj(nf0.blackout).end)) + '">⛔ 블랙아웃</span>';
    if (anyMock(D)) h += '<span class="fd-bd mock" title="계약 목데이터(mock:true) — 실배포 시 false">MOCK</span>';
    if (D.positions && str(D.positions.badge)) h += '<span class="fd-bd" title="' + attr(validTip(D.positions)) + '">' + esc(D.positions.badge) + '</span>';
    if (typeof window !== 'undefined' && window.PV && typeof window.PV.speak === 'function') {
      h += '<button type="button" class="fd-btn" data-act="speak" title="요약 읽기">🔊 브리핑</button>';
    }
    h += '<div class="fd-ts">발언 ' + kstHM(obj(D.statements).updated_ts) + ' · 시장 ' + kstHM(obj(D.reaction).updated_ts) + ' · TACO ' + kstHM(obj(D.taco).updated_ts) + ' KST</div>';
    h += '</div>';
    h += '<p class="fd-hint" style="padding:0 2px" data-brief="1">' + esc(briefText(D)) + '</p>';
    return h;
  }
  function rNav(ST) {
    return '<div class="fd-nav">' +
      '<button type="button" class="fd-chip" data-go="fdDist">성향 분포</button>' +
      '<button type="button" class="fd-chip" data-go="fdPeople">연준 인사</button>' +
      '<button type="button" class="fd-chip" data-go="fdFeed">발언</button>' +
      '<button type="button" class="fd-chip" data-go="fdReact">시장반응</button>' +
      '<button type="button" class="fd-chip" data-go="fdCal">캘린더</button>' +
      '<button type="button" class="fd-chip" data-go="fdTaco">TACO</button>' +
      '</div>';
  }

  /* ══════════════════ 9. fd-cal (캘린더) ══════════════════ */
  function rCal(ST, D) {
    var cal = D.calendar;
    var nfc = obj(cal).next_fomc;
    var head = '<div class="fd-h"><b>📅 캘린더</b>' +
      (nfc && isN(nfc.d_days) ? '<span class="fd-bd" title="다음 FOMC">D-' + nfc.d_days + '</span>' : '') + '</div>';
    if (!cal) return '<div class="fd-card fd-cal" id="fdCal">' + head + '<p class="fd-hint">캘린더 데이터 준비 중…</p></div>';

    var items = arr(cal.items).slice();
    items.sort(function (a, b) { return (a && a.ts || 0) - (b && b.ts || 0); });
    var now = ST.now, t0 = kstMidnight(now);
    var span = ST.calRange === '30d' ? 30 : (ST.calRange === 'all' ? 0 : 7);
    var lo = t0, hi = span ? t0 + span * 86400 : null;
    var shown = [], i, it;
    for (i = 0; i < items.length; i++) {
      it = items[i]; if (!it || !isN(it.ts)) continue;
      if (hi != null && (it.ts < lo || it.ts >= hi)) continue;
      if (!passStar(it, ST.calStar)) continue;
      shown.push(it);
    }
    var body = '';
    var bo = obj(nfc).blackout;
    if (bo && bo.active === true) {
      body += '<div class="cblk">⛔ FOMC 블랙아웃 ' + esc(str(bo.start)) + ' ~ ' + esc(str(bo.end)) + ' — 공개 발언 자제 기간</div>';
    }
    if (!shown.length) {
      body += '<p class="fd-hint">해당 구간에 표시할 일정이 없습니다 — 범위 칩을 넓혀 보세요.</p>';
    } else {
      var lastDay = '';
      for (i = 0; i < shown.length; i++) {
        it = shown[i];
        var dk = kstDayKey(it.ts);
        var isToday = (kstMidnight(it.ts) === t0);
        var when;
        if (it.all_day === true) when = kstMD(it.ts);                       // all_day 는 시각을 아예 표시하지 않는다
        else when = kstMD(it.ts) + ' ' + (it.time_confirmed === false ? '~' : '') + kstHM(it.ts);
        var cls = 'crow' + (isToday ? ' today' : '') + (it.status === 'done' ? ' done' : '') + (it.status === 'cancelled' ? ' cancelled' : '');
        body += '<div class="' + cls + '" data-cid="' + attr(it.id) + '" data-star="' + (isN(it.stars) ? it.stars : 0) + '"' + (it.all_day === true ? ' data-allday="1"' : '') + '>';
        body += '<span class="cd">' + esc(when) + '</span>';
        body += '<span class="ci">' + esc(CAL_ICON[it.kind] || '·') + '</span>';
        body += '<span class="ct">' + calAvatar(it, D) + esc(str(it.title) || str(it.title_en) || it.id) + calExtra(it) + '</span>';
        body += '<span class="cs">' + starStr(it.stars) + '</span></div>';
        lastDay = dk;
      }
    }
    var chips = '<div class="fd-chips">' +
      chip('calStar', '3', '★3', ST.calStar === '3') + chip('calStar', '2', '★2+', ST.calStar === '2', '★2 이상 + 연준 인사 전부') + chip('calStar', 'all', '전체', ST.calStar === 'all') +
      '<span class="sep"></span>' +
      chip('calRange', '7d', '7일', ST.calRange === '7d') + chip('calRange', '30d', '30일', ST.calRange === '30d') + chip('calRange', 'all', '전체', ST.calRange === 'all') +
      '</div>';
    var foot = '<div class="fd-foot">KST 표시 · ' + shown.length + '건 / 전체 ' + items.length + '건 · <code>all_day</code> 항목은 날짜만, <code>time_confirmed:false</code>(시각 미공지)는 <code>~</code> 접두' + staleNote(cal) + '</div>';
    return '<div class="fd-card fd-cal" id="fdCal">' + head + body + chips + foot + '</div>';
  }
  function passStar(it, mode) {
    var s = isN(it.stars) ? it.stars : 0;
    if (mode === 'all') return true;
    if (mode === '3') return s >= 3;
    return s >= 2 || !!str(it.pid) || !!(it.speaker && str(it.speaker.pid));   // 기본 ★≥2 + 연준 인사 전부
  }
  function starStr(s) { return isN(s) && s > 0 ? new Array(s + 1).join('★') : ''; }
  function calAvatar(it, D) {
    var pid = str(it.pid) || (it.speaker && str(it.speaker.pid));
    if (!pid) return '';
    return smallAvatar(D, pid, ringOfPid(D, pid, true));
  }
  function smallAvatar(D, pid, col) {
    if (!pid) return '';
    var r = personOf(D, pid);
    var name = (r && str(r.name)) || pid, mode = obj(obj(D.roster).photo_policy).mode || 'pd_only';
    var h = '<button type="button" class="cav" data-pid="' + attr(pid) + '" style="background:' + col + '2e;color:' + col + '" title="' + attr(name) + '" aria-label="' + attr(name + ' 프로필 열기') + '"><span aria-hidden="true">' + esc(r ? initialsOf({ r: r, id: pid }) : pid.slice(0, 2).toUpperCase()) + '</span>';
    if (photoUsable(r, mode)) h += '<img class="fd-photo" src="' + attr(r.photo) + '" width="32" height="32" loading="lazy" decoding="async" alt="">';
    return h + '</button>';
  }
  function calExtra(it) {
    var x = [];
    if (str(it.consensus)) x.push('예상 ' + esc(it.consensus));
    if (str(it.previous)) x.push('직전 ' + esc(it.previous));
    if (isN(it.amount_usd)) x.push(usd(it.amount_usd));
    if (str(it.note)) x.push(esc(it.note));
    if (it.live === true) x.push('LIVE');
    if (it.status === 'cancelled') x.push('취소');
    return x.length ? '<span class="cx">' + x.join(' · ') + '</span>' : '';
  }
  function personOf(D, pid) {
    var ps = arr(obj(D.roster).people), i;
    for (i = 0; i < ps.length; i++) if (ps[i] && ps[i].id === pid) return ps[i];
    return null;
  }
  function posOf(D, pid) {
    var ps = arr(obj(D.positions).people), i;
    for (i = 0; i < ps.length; i++) if (ps[i] && ps[i].id === pid) return ps[i];
    return null;
  }
  function ringOfPid(D, pid, neutralGray) {
    var p = posOf(D, pid);
    return p ? labelColor(str(p.label), p.pos, neutralGray !== false) : NEUT;
  }

  /* ══════════════════ 10. fd-feed (발언 피드) ══════════════════ */
  function rFeed(ST, D) {
    var stm = D.statements;
    var head = '<div class="fd-h"><b>🎤 발언 피드</b>' + (stm && isN(stm.n) ? '<span class="fd-bd">' + stm.n + '건 / ' + (isN(stm.window_days) ? stm.window_days : '—') + '일</span>' : '') + '</div>';
    if (!stm) return '<div class="fd-card fd-feed" id="fdFeed">' + head + '<p class="fd-hint">발언 데이터 준비 중…</p></div>';

    var body = todayStrip(stm, 'fd-today');
    var items = arr(stm.items).filter(function (x) { return x && !str(x.superseded_by); });
    var f = items.filter(function (x) {
      var r = personOf(D, str(x.pid));
      if (!passGroup(r, ST.feedGroup === 'frb' ? 'frb' : ST.feedGroup)) return false;
      if (ST.feedKind !== 'all') {
        var k = str(x.kind);
        if (ST.feedKind === 'etc') { if (k === 'speech' || k === 'interview' || k === 'testimony') return false; }
        else if (k !== ST.feedKind) return false;
      }
      if (ST.feedDev && x.deviation !== true) return false;
      return true;
    });
    if (ST.feedSort === 'dev') f.sort(function (a, b) { return Math.abs(isN(b.rel) ? b.rel : 0) - Math.abs(isN(a.rel) ? a.rel : 0); });
    else f.sort(function (a, b) { return (isN(b.ts) ? b.ts : 0) - (isN(a.ts) ? a.ts : 0); });

    if (!f.length) body += '<p class="fd-hint">조건에 맞는 발언이 없습니다 — 필터를 넓혀 보세요.</p>';
    var lastDay = '', i;
    for (i = 0; i < f.length; i++) {
      var it = f[i], dk = kstDayKey(it.ts);
      if (ST.feedSort === 'recent' && dk !== lastDay) { body += '<div class="fd-day">' + esc(dk) + '</div>'; lastDay = dk; }
      body += spCard(it, D, ST);
    }
    var chips = '<div class="fd-chips">' +
      chip('feedGroup', 'all', '전체', ST.feedGroup === 'all') + chip('feedGroup', 'voter', '투표권', ST.feedGroup === 'voter') +
      chip('feedGroup', 'board', '이사회', ST.feedGroup === 'board') + chip('feedGroup', 'frb', '총재', ST.feedGroup === 'frb') +
      '<span class="sep"></span>' +
      chip('feedKind', 'all', '전부', ST.feedKind === 'all') + chip('feedKind', 'speech', '연설', ST.feedKind === 'speech') +
      chip('feedKind', 'interview', '인터뷰', ST.feedKind === 'interview') + chip('feedKind', 'testimony', '증언', ST.feedKind === 'testimony') +
      chip('feedKind', 'etc', '기타', ST.feedKind === 'etc') +
      '<span class="sep"></span>' +
      chip('feedDev', ST.feedDev ? '0' : '1', '이탈만', ST.feedDev) +
      chip('feedSort', 'recent', '최신', ST.feedSort === 'recent') + chip('feedSort', 'dev', '이탈 크기', ST.feedSort === 'dev') +
      '</div>';
    var foot = '<div class="fd-foot">요약·판정은 자체 작성(원문 복제 없음) · 지역연은 발언은 전문 미저장(제목·헤드라인 기반 채점) · <code>⚡ 성향 이탈</code> 배지는 계약 <code>items[].deviation</code> 필드 그대로' + staleNote(stm) + '</div>';
    return '<div class="fd-card fd-feed" id="fdFeed">' + head + body + chips + foot + '</div>';
  }
  function todayStrip(stm, cls) {
    var t = obj(stm.today), le = obj(stm.last_event);
    var ta = toneOf(t), tr = toneRelOf(t), S = isN(t.S) ? t.S : null;
    var la = toneOf(le);
    var dlt = (isN(ta) && isN(la)) ? (ta - la) : null;
    var col = isN(ta) ? scoreColor(ta, true) : FLAT;
    var h = '<div class="' + cls + '"><div><div class="tl">오늘의 톤 · ' + esc(str(t.date_et) || '—') + ' (ET)</div>' +
      '<div class="tn" style="color:' + col + '">' + (isN(ta) ? sf(ta, 2) : '—') + '</div></div>';
    h += '<div class="tl">발언 <b class="fd-mono">' + (isN(t.n) ? t.n : '—') + '</b>건<br>tone_rel <b class="fd-mono">' + (isN(tr) ? sf(tr, 2) : '—') + '</b><br>S <b class="fd-mono">' + (isN(S) ? sf(S, 3) : '—') + '</b></div>';
    h += '<div class="fd-g" style="flex:1;min-width:120px"><span class="gt" style="background:url(#fdGrad);background-image:linear-gradient(90deg,' + DOVE + ',#fff,' + HAWK + ');opacity:.55"></span></div>';
    h += '<div class="tl">직전 이벤트(' + esc(str(le.date_et) || '—') + ') 대비<br>Δ <b class="fd-mono" style="color:' + (isN(dlt) ? scoreColor(dlt, true) : FLAT) + '">' + (isN(dlt) ? sf(dlt, 2) : '—') + '</b></div>';
    h += '</div>';
    return h;
  }
  function spCard(it, D, ST) {
    var pid = str(it.pid), r = personOf(D, pid), p = posOf(D, pid);
    var ring = ringOfPid(D, pid, ST.neutralRing);
    var fresh = (isN(it.ts) && (ST.now - it.ts) <= 7200);
    var nm = (r && (str(r.short) || str(r.name))) || pid || '—';
    var h = '<div class="fd-sp' + (fresh ? ' fresh' : '') + '" data-sid="' + attr(it.id) + '">';
    h += '<div class="sph">';
    h += smallAvatar(D, pid, ring);
    h += '<b>' + esc(nm) + '</b><span>' + esc((r && str(r.title)) || '') + '</span>';
    if (r && r.voter === true) h += '<span class="fd-bd vote">투표권</span>';
    else if (r && r.alternate === true) h += '<span class="fd-bd">대리</span>';
    h += '<span class="fd-mono">' + esc(kstFull(it.ts)) + ' KST</span><span>' + esc(agoKo(it.ts, ST.now)) + '</span>';
    if (fresh) h += '<span class="fd-bd vote">🆕</span>';
    if (it.deviation === true) h += '<span class="fd-bd dev" style="margin-left:auto">⚡ 성향 이탈</span>';
    h += '</div>';
    h += '<div class="spt">' + (str(it.url) ? '<a href="' + attr(it.url) + '" target="_blank" rel="noopener">' + esc(str(it.title) || it.id) + ' ↗</a>' : esc(str(it.title) || it.id)) + '</div>';
    var sum = arr(it.summary).filter(function (x) { return str(x); });
    if (sum.length) h += '<div class="fd-sum" data-sum="1">' + esc(sum.join(' ')) + '</div>';
    if (str(it.key_line)) h += '<div class="fd-hint" style="padding:2px 0;font-style:italic">“' + esc(it.key_line) + '”</div>';
    /* ABS 게이지 */
    h += gaugeRow('ABS', it.abs, str(it.label_ko) || '—', scoreColor(it.abs, true), 'linear-gradient(90deg,' + DOVE + ',#ffffff,' + HAWK + ');opacity:.85', null, null);
    /* REL 게이지 — 중앙 0 = baseline_before */
    h += gaugeRow('REL', it.rel, str(it.rel_label_ko) || '—', scoreColor(it.rel, true), 'var(--panel2,#0d131c);border:1px solid var(--line,#1f2937)', 0, ring);
    if (isN(it.baseline_before)) h += '<div class="fd-hint" style="padding:0 0 3px;font-size:10px">기준선(발언 전) ' + sf(it.baseline_before, 2) + ' → 갱신 후 ' + (isN(it.pos_after) ? sf(it.pos_after, 2) : '—') + '</div>';
    var mkt = it.mkt;
    if (mkt) {
      h += '<div class="fd-meta">시장반응 ' + esc(str(mkt.window) || '') +
        ' · 2Y ' + (isN(mkt.ust2y_bp) ? sf(mkt.ust2y_bp, 1) + 'bp' : '—') +
        ' · ZQ ' + (isN(mkt.zq_bp) ? sf(mkt.zq_bp, 1) + 'bp' : '—') +
        ' · SPY ' + (isN(mkt.spy_pct) ? sf(mkt.spy_pct, 2) + '%' : '—') +
        ' · VIX ' + (isN(mkt.vix_chg) ? sf(mkt.vix_chg, 2) : '—') +
        ' <span title="' + attr(str(mkt.src) + ' · ' + (isN(mkt.n_bars) ? mkt.n_bars + '봉' : '')) + '">(' + esc(str(mkt.src) || '—') + ')</span></div>';
    }
    var kws = arr(it.keywords).slice(0, 3), i;
    if (kws.length) { h += '<div>'; for (i = 0; i < kws.length; i++) h += '<span class="fd-kw">' + esc(kws[i]) + '</span>'; h += '</div>'; }
    h += '<div class="fd-meta">' + esc(hostOf(it.url) || str(it.src) || '—') +
      ' · ' + esc(KIND_KO[str(it.kind)] || str(it.kind) || '—') +
      ' · 신뢰도 ' + confDots(it.conf) +
      ' · ' + esc(str(it.backend) || '—') +
      (it.disagree === true ? ' · <span style="color:#ff8a3d">사전·LLM 불일치</span>' : '') +
      (it.policy === false ? ' · 비정책(성향 갱신 제외)' : '') +
      (isN(obj(it.headlines).n_24h) ? ' · 헤드라인 24h ' + obj(it.headlines).n_24h + '건' : '') +
      '</div>';
    h += '</div>';
    return h;
  }

  /* ══════════════════ 11. fd-react (시장반응) ══════════════════ */
  function sigmaRow(a) {
    if (!a) return '';
    var sg = isN(a.exp_sigma) ? a.exp_sigma : (isN(a.exp) && isN(a.sigma_1d) && a.sigma_1d ? a.exp / a.sigma_1d : null);
    var col = isN(a.exp) ? (a.exp > 0 ? UP : (a.exp < 0 ? DOWN : FLAT)) : FLAT;
    function px(s) { return clamp((clamp(s, -2, 2) + 2) / 4 * 100, 0, 100); }
    var h = '<div class="fd-sig" title="' + attr('σ(1일) ' + nf(a.sigma_1d, 3) + (a.unit === 'bp' ? 'bp' : '%') + ' · σ출처 ' + (str(a.sigma_src) || '—') + ' · β출처 ' + (str(a.beta_src) || '—')) + '">';
    h += '<span class="sn">' + esc(str(a.name) || str(a.sym) || '—') + '</span><span class="sb">';
    h += '<i style="position:absolute;left:0;right:0;top:7px;height:2px;background:rgba(138,147,163,.22);display:block"></i>';
    h += '<i style="position:absolute;left:50%;top:1px;width:1px;height:14px;background:#6b7280;display:block"></i>';
    if (isN(a.p25) && isN(a.p75) && isN(a.sigma_1d) && a.sigma_1d) {
      var l = px(a.p25 / a.sigma_1d), rr = px(a.p75 / a.sigma_1d);
      h += '<i style="position:absolute;left:' + nf(Math.min(l, rr), 1) + '%;width:' + nf(Math.abs(rr - l), 1) + '%;top:7px;height:2px;background:' + col + ';opacity:.55;display:block"></i>';
    }
    if (sg != null) h += '<i style="position:absolute;left:' + nf(px(sg), 1) + '%;top:3px;width:10px;height:10px;border-radius:50%;background:' + col + ';transform:translateX(-5px);display:block"></i>';
    h += '</span><span class="sv" style="color:' + col + '">' + (sg != null ? sf(sg, 2) + 'σ' : '—') + ' <span style="color:var(--dim,#8a93a3)">(≈ ' + unitStr(a.exp, a.unit, a.unit === 'bp' ? 2 : 2) + ')</span></span></div>';
    return h;
  }
  function densitySVG(a) {
    var d = a && a.density;
    if (!d || !isN(d.x0) || !isN(d.dx) || !arr(d.y).length) {
      return '<p class="fd-hint" style="font-size:11px">밀도 분포 없음 — 상승확률 ' + (isN(a && a.p_up) ? nf(a.p_up * 100, 1) + '%' : '—') + ' · 하락확률 ' + (isN(a && a.p_down) ? nf(a.p_down * 100, 1) + '%' : '—') + '</p>';
    }
    var y = arr(d.y), n = y.length, W = 300, H = 120, i;
    var x0 = d.x0, dx = d.dx, x1 = x0 + dx * (n - 1);
    var ymax = 0; for (i = 0; i < n; i++) if (isN(y[i]) && y[i] > ymax) ymax = y[i];
    if (!(ymax > 0)) ymax = 1;
    function X(v) { return clamp((v - x0) / (x1 - x0), 0, 1) * (W - 20) + 12; }
    function Y(v) { return H - 18 - (isN(v) ? v : 0) / ymax * (H - 30); }
    var pts = '';
    for (i = 0; i < n; i++) pts += (i ? ' L' : 'M') + nf(X(x0 + dx * i), 1) + ',' + nf(Y(y[i]), 1);
    var area = pts + ' L' + nf(X(x1), 1) + ',' + (H - 18) + ' L' + nf(X(x0), 1) + ',' + (H - 18) + ' Z';
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block" role="img" aria-label="옵션 내재 수익률 분포">';
    s += '<path d="' + area + '" fill="rgba(43,192,212,.18)"/><path d="' + pts + '" fill="none" stroke="' + ACC + '" stroke-width="1.4"/>';
    s += '<line x1="' + nf(X(0), 1) + '" y1="8" x2="' + nf(X(0), 1) + '" y2="' + (H - 18) + '" stroke="#6b7280" stroke-width="1" stroke-dasharray="3 4"/>';
    if (isN(a.exp)) {
      var col = a.exp > 0 ? UP : (a.exp < 0 ? DOWN : FLAT);
      s += '<line x1="' + nf(X(a.exp), 1) + '" y1="8" x2="' + nf(X(a.exp), 1) + '" y2="' + (H - 18) + '" stroke="' + col + '" stroke-width="1.4"/>';
      s += '<text x="' + nf(X(a.exp), 1) + '" y="7" text-anchor="middle" font-size="9.5" fill="' + col + '">E[r] ' + esc(unitStr(a.exp, a.unit, 2)) + '</text>';
    }
    var lt = 0, rt = 0;
    for (i = 0; i < n; i++) { var xv = x0 + dx * i; if (xv < -2) lt += (isN(y[i]) ? y[i] : 0); if (xv > 2) rt += (isN(y[i]) ? y[i] : 0); }
    s += '<text x="12" y="' + (H - 5) + '" font-size="9" fill="#6b7280">' + nf(x0, 1) + '%</text>';
    s += '<text x="' + (W - 8) + '" y="' + (H - 5) + '" text-anchor="end" font-size="9" fill="#6b7280">' + sf(x1, 1) + '%</text>';
    s += '</svg><p class="fd-hint" style="font-size:10.5px;padding:2px 0">좌꼬리 p(&lt;−2%) ' + nf(lt * 100, 2) + '% · 우꼬리 p(&gt;+2%) ' + nf(rt * 100, 2) + '% · 꼬리확률(계약 tail_prob) ' + (isN(a.tail_prob) ? nf(a.tail_prob * 100, 1) + '%' : '—') + '</p>';
    return s;
  }
  function rateStack(m) {
    if (!m) return '';
    var p = obj(m.p), pv = obj(m.p_prev), i, k, h = '';
    var tot = 0; for (i = 0; i < PATH_K.length; i++) tot += (isN(p[PATH_K[i]]) ? p[PATH_K[i]] : 0);
    if (!(tot > 0)) return '';
    h += '<div style="font-size:10.5px;color:var(--dim,#8a93a3);margin-top:7px">' + esc(str(m.date) || '—') + ' · ' + esc(str(m.src) || '—') + '</div>';
    var hasPrev = false; for (i = 0; i < PATH_K.length; i++) if (isN(pv[PATH_K[i]])) hasPrev = true;
    if (hasPrev) {
      h += '<div class="fd-stack prev" title="발언 반영 전(p_prev)">';
      for (i = 0; i < PATH_K.length; i++) { k = PATH_K[i]; var w0 = (isN(pv[k]) ? pv[k] : 0) / tot * 100; if (w0 > 0) h += '<i style="width:' + nf(w0, 2) + '%;background:' + PATH_C[k] + '"></i>'; }
      h += '</div>';
    }
    h += '<div class="fd-stack">';
    for (i = 0; i < PATH_K.length; i++) {
      k = PATH_K[i]; var v = isN(p[k]) ? p[k] : 0, w = v / tot * 100;
      if (w <= 0) continue;
      h += '<i style="width:' + nf(w, 2) + '%;background:' + PATH_C[k] + '" title="' + attr(k + 'bp ' + nf(v * 100, 1) + '%') + '">' + (v >= 0.12 ? esc(k + ' ' + Math.round(v * 100) + '%') : '') + '</i>';
    }
    h += '</div>';
    if (isN(m.mpt_p_hike)) h += '<div class="fd-hint" style="font-size:10px;padding:1px 0">MPT p(인상) ' + nf(m.mpt_p_hike * 100, 1) + '%' + (str(m.mpt_note) ? ' — ' + esc(m.mpt_note) : '') + '</div>';
    return h;
  }
  function rReact(ST, D) {
    var rc = D.reaction;
    var head = '<div class="fd-h"><b>📈 기대 시장반응</b>' +
      (rc ? '<span class="fd-bd" title="live=실측 인트라데이 · model=모델 추정">' + esc(str(rc.mode) || '—') + '</span>' : '') + '</div>';
    if (!rc) return '<div class="fd-card fd-react" id="fdReact">' + head + '<p class="fd-hint">시장반응 데이터 준비 중…</p></div>';

    var body = todayStrip(obj(D.statements), 'fd-today');
    var rate = obj(rc.rate);
    body += '<div class="fd-kpi">' +
      '<div><span>EFFR</span><b>' + nf(rate.effr, 2) + '</b></div>' +
      '<div><span>목표범위</span><b>' + (arr(rate.target).length === 2 ? nf(rate.target[0], 2) + '–' + nf(rate.target[1], 2) : '—') + '</b></div>' +
      '<div><span>경로 이동</span><b style="color:' + (isN(rate.path_shift_bp) ? (rate.path_shift_bp > 0 ? UP : DOWN) : FLAT) + '">' + (isN(rate.path_shift_bp) ? sf(rate.path_shift_bp, 2) + 'bp' : '—') + '</b></div>' +
      '<div><span>1월27 누적</span><b>' + (isN(rate.cum_bp_to_jan27) ? sf(rate.cum_bp_to_jan27, 1) + 'bp' : '—') + '</b></div>' +
      '</div>';
    body += '<div class="fd-hint" style="font-size:10px;padding:0 0 6px">경로 출처 ' + esc(str(rate.path_shift_src) || '—') +
      (isN(rate.path_shift_live_bp) ? ' · 라이브 ΔZQ ' + sf(rate.path_shift_live_bp, 1) + 'bp' : '') + '</div>';

    body += '<div class="fd-sec">기대 변동 (−2σ ~ +2σ)</div>';
    var as = arr(rc.assets), i;
    if (!as.length) body += '<p class="fd-hint">자산 데이터 대기</p>';
    for (i = 0; i < as.length; i++) body += sigmaRow(as[i]);

    body += '<div class="fd-sec">옵션 내재 분포</div>';
    var sp = spyAsset(rc);
    body += densitySVG(sp);

    body += '<div class="fd-sec">금리 경로 확률</div>';
    var ms = arr(rate.meetings);
    if (!ms.length) body += '<p class="fd-hint">경로 데이터 대기</p>';
    for (i = 0; i < Math.min(3, ms.length); i++) body += rateStack(ms[i]);
    if (ms.length) {
      body += '<div class="fd-hint" style="font-size:10px;padding:4px 0">';
      for (i = 0; i < PATH_K.length; i++) body += '<span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' + PATH_C[PATH_K[i]] + ';margin:0 3px -1px 8px"></span>' + esc(PATH_K[i] + 'bp');
      body += '</div>';
    }

    var q = obj(rc.quality);
    var foot = '<div class="fd-foot">' + esc(str(rc.note) || '옵션 내재 분포 × 발언 서프라이즈 — 투자판단 아님') +
      ' · asof ' + esc(str(rc.asof_market) || '—') +
      (q.cboe_offhours === true ? ' · ⚠ CBOE 장외 시세(σ 과소 가능)' : '') +
      ' · 상승 <span style="color:' + UP + '">빨강</span> / 하락 <span style="color:' + DOWN + '">파랑</span>(국내 관례)' +
      staleNote(rc);
    /* 사후 적중 각주 — calib.n>=10 일 때만(옵셔널 체이닝 없이 가드) */
    if (rc && rc.calib && isN(rc.calib.n) && rc.calib.n >= 10 && isN(rc.calib.sign_hit) && isN(rc.calib.mae_pct)) {
      foot += '<br>기대반응 부호 적중 ' + nf(rc.calib.sign_hit * 100, 1) + '% · 평균오차 ' + nf(rc.calib.mae_pct, 2) + '%p — 표본 ' + rc.calib.n + '일';
    }
    foot += '</div>';
    return '<div class="fd-card fd-react" id="fdReact">' + head + body + foot + '</div>';
  }

  /* ══════════════════ 12. fd-taco ══════════════════ */
  function degStr(deg, band) {
    if (!isN(deg)) return '—';
    var s = n2(deg);
    if (arr(band).length === 2 && isN(band[0]) && isN(band[1])) s += ' [' + n2(band[0]) + '–' + n2(band[1]) + ']';
    return s;
  }
  function threatByIdx(taco) {
    var m = {}, ts = arr(obj(taco).open_threats), i;
    for (i = 0; i < ts.length; i++) if (ts[i] && ts[i].id != null) m[ts[i].id] = ts[i];
    return m;
  }
  /* viz 디스패치 테이블 — 새 컨셉은 함수 하나 추가 */
  var TACO_VIZ = {
    threat_arc: function (viz, taco) {
      var vb = arr(viz.viewBox).length === 2 ? viz.viewBox : [1000, 360];
      var W = isN(vb[0]) ? vb[0] : 1000, H = isN(vb[1]) ? vb[1] : 360;
      var COL = obj(viz.colors);
      var xa = obj(viz.x_axis), dom = arr(xa.domain_days).length === 2 ? xa.domain_days : [0.5, 180];
      var d0 = isN(dom[0]) && dom[0] > 0 ? dom[0] : 0.5, d1 = isN(dom[1]) && dom[1] > d0 ? dom[1] : 180;
      var X0 = 320, XW = W - X0 - 30, Y0 = 34, YH = 246, YB = Y0 + YH;
      var L0 = Math.log(d0), L1 = Math.log(d1);
      function X(dd) { return X0 + (Math.log(clamp(isN(dd) ? dd : d0, d0, d1)) - L0) / (L1 - L0) * XW; }
      function Y(v) { return Y0 + (1 - clamp(isN(v) ? v : 0, 0, 1)) * YH; }
      var idx = threatByIdx(taco), i;

      var s = '<svg class="fd-arc" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet" role="img" aria-label="TACO 위협 궤적 보드">';
      s += '<rect x="0" y="0" width="' + W + '" height="' + H + '" fill="#0b0b0b" rx="10"/>';

      /* ─ 반원 게이지(타코 셸) ─ */
      var g = obj(viz.gauge), gv = isN(g.value) ? clamp(g.value, 0, 1) : null;
      var cx = 160, cy = 214, rr = 100, len = Math.PI * rr;
      s += '<path d="M' + (cx - rr) + ',' + cy + ' A' + rr + ',' + rr + ' 0 0 1 ' + (cx + rr) + ',' + cy + '" fill="none" stroke="#23262e" stroke-width="24" stroke-linecap="round"/>';
      if (gv != null) {
        s += '<path d="M' + (cx - rr) + ',' + cy + ' A' + rr + ',' + rr + ' 0 0 1 ' + (cx + rr) + ',' + cy + '" fill="none" stroke="url(#fdTacoG)" stroke-width="24" stroke-linecap="round" stroke-dasharray="' + nf(len * gv, 2) + ' ' + nf(len, 2) + '"/>';
        s += '<text x="' + cx + '" y="' + (cy - 14) + '" text-anchor="middle" font-size="40" font-weight="800" fill="#f5c542">' + n2(gv) + '</text>';
      } else {
        s += '<text x="' + cx + '" y="' + (cy - 14) + '" text-anchor="middle" font-size="28" font-weight="800" fill="#8a93a3">—</text>';
      }
      s += '<text x="' + cx + '" y="' + (cy + 10) + '" text-anchor="middle" font-size="12" fill="#9aa3b2">' + esc(str(g.label) || 'TACO_90') + '</text>';
      s += '<text x="' + (cx - rr) + '" y="' + (cy + 22) + '" text-anchor="middle" font-size="10.5" fill="#8a93a3">0 HOLD</text>';
      s += '<text x="' + (cx + rr) + '" y="' + (cy + 22) + '" text-anchor="middle" font-size="10.5" fill="#f5c542">1 TACO</text>';
      s += '<text x="' + cx + '" y="' + (cy + 44) + '" text-anchor="middle" font-size="12" fill="#cfd6df" font-family="ui-monospace,Menlo,monospace">P7 ' + (isN(g.p7) ? n2(g.p7) : '—') + ' · P30 ' + (isN(g.p30) ? n2(g.p30) : '—') + '</text>';
      s += '<text x="' + cx + '" y="' + (cy + 62) + '" text-anchor="middle" font-size="10" fill="#6b7280">🌮 셸 채움 = 90일 철회지수</text>';

      /* ─ 축 ─ */
      s += '<line x1="' + X0 + '" y1="' + YB + '" x2="' + (X0 + XW) + '" y2="' + YB + '" stroke="#3a3a3a" stroke-width="1"/>';
      s += '<line x1="' + X0 + '" y1="' + Y0 + '" x2="' + X0 + '" y2="' + YB + '" stroke="#3a3a3a" stroke-width="1"/>';
      var xt = [0.5, 1, 3, 7, 14, 30, 90, 180];
      for (i = 0; i < xt.length; i++) {
        if (xt[i] < d0 || xt[i] > d1) continue;
        s += '<line x1="' + nf(X(xt[i]), 1) + '" y1="' + Y0 + '" x2="' + nf(X(xt[i]), 1) + '" y2="' + YB + '" stroke="#232323" stroke-width="1" stroke-dasharray="2 5"/>';
        s += '<text x="' + nf(X(xt[i]), 1) + '" y="' + (YB + 14) + '" text-anchor="middle" font-size="9.5" fill="#6b7280">' + (xt[i] < 1 ? '½' : xt[i]) + 'd</text>';
      }
      s += '<text x="' + (X0 + XW / 2) + '" y="' + (YB + 30) + '" text-anchor="middle" font-size="10.5" fill="#9aa3b2">위협 발생 후 경과일 (log)</text>';
      s += '<text x="' + (X0 - 14) + '" y="' + (Y0 + YH / 2) + '" text-anchor="middle" font-size="10.5" fill="#9aa3b2" transform="rotate(-90 ' + (X0 - 14) + ' ' + (Y0 + YH / 2) + ')">' + esc(str(obj(viz.y_axis).label) || 'intensity') + ' 0–1</text>';

      /* ─ 생존곡선 실루엣 ─ */
      var sb = arr(viz.survival_bg), path = '';
      for (i = 0; i < sb.length; i++) {
        var pt = sb[i]; if (!arr(pt).length) continue;
        path += (i ? ' L' : 'M') + nf(X(Math.max(pt[0], d0)), 1) + ',' + nf(Y(pt[1]), 1);
      }
      if (path) {
        s += '<path d="' + path + ' L' + nf(X(d1), 1) + ',' + YB + ' L' + nf(X(d0), 1) + ',' + YB + ' Z" fill="#1f2937" fill-opacity="0.55"/>';
        s += '<path d="' + path + '" fill="none" stroke="#2b3a4d" stroke-width="1.2"/>';
        s += '<text x="' + nf(X(d1), 1) + '" y="' + nf(Y(sb.length ? sb[sb.length - 1][1] : 0) - 6, 1) + '" text-anchor="end" font-size="9.5" fill="#4b5563">S(t) 미철회 생존</text>';
      }

      /* ─ 아크 ─ */
      var arcs = arr(viz.arcs);
      for (i = 0; i < arcs.length; i++) {
        var a = arcs[i]; if (!a) continue;
        var t = idx[a.id] || {};
        var col = COL[str(a.topic)] || COL.OTHER || ACC;
        var y0 = isN(a.y0) ? a.y0 : 0.5;
        var lam = isN(a.lambda) ? a.lambda : 7;
        var band = arr(a.band);
        var cand = a.status === 'retreat_candidate';
        if (band.length === 2 && isN(band[0]) && isN(band[1])) {
          s += '<rect x="' + nf(X(band[0]), 1) + '" y="' + nf(Y(y0), 1) + '" width="' + nf(Math.max(1, X(band[1]) - X(band[0])), 1) + '" height="' + nf(Math.max(1, YB - Y(y0)), 1) + '" fill="' + col + '" fill-opacity="0.13"/>';
        }
        var xs = X(d0), ys = Y(y0), xe = X(lam), ye = Y(0.05);
        s += '<g class="fd-arcg" data-tid="' + attr(a.id) + '">';
        s += '<path d="M' + nf(xs, 1) + ',' + nf(ys, 1) + ' Q' + nf((xs + xe) / 2, 1) + ',' + nf(ys - 26, 1) + ' ' + nf(xe, 1) + ',' + nf(ye, 1) + '" fill="none" stroke="' + col + '" stroke-width="2.4"' + (cand ? ' stroke-dasharray="6 4"' : '') + '/>';
        s += '<circle cx="' + nf(xs, 1) + '" cy="' + nf(ys, 1) + '" r="6" fill="' + col + '"/>';
        s += '<circle cx="' + nf(xe, 1) + '" cy="' + nf(ye, 1) + '" r="4" fill="none" stroke="' + col + '" stroke-width="2"/>';
        s += '<text x="' + nf(xs + 10, 1) + '" y="' + nf(ys - 10, 1) + '" font-size="11" fill="' + col + '">' + esc(str(a.label) || str(a.topic) || a.id) + '</text>';
        if (isN(a.deadline_days)) {
          s += '<line x1="' + nf(X(a.deadline_days), 1) + '" y1="' + Y0 + '" x2="' + nf(X(a.deadline_days), 1) + '" y2="' + YB + '" stroke="#ff8a3d" stroke-width="1.2" stroke-dasharray="4 4"/>';
          s += '<text x="' + nf(X(a.deadline_days), 1) + '" y="' + (Y0 - 6) + '" text-anchor="middle" font-size="10" fill="#ff8a3d">⏰ D-' + a.deadline_days + '</text>';
        }
        s += '<title>' + esc(arcTip(a, t)) + '</title>';
        s += '</g>';
        if (cand) s += '<text x="' + nf(xs + 10, 1) + '" y="' + nf(ys + 16, 1) + '" font-size="10" fill="#f5c542">🔎 철회 정황(헤드라인)</text>';
      }

      /* ─ 착지 마커 ─ */
      var ld = arr(viz.landed);
      for (i = 0; i < ld.length; i++) {
        var m = ld[i]; if (!m) continue;
        var mc = COL[str(m.topic)] || COL.OTHER || FLAT;
        var mx = X(Math.max(isN(m.days) ? m.days : d0, d0));
        var deg = isN(m.degree) ? clamp(m.degree, 0, 1) : 0;
        var tip = '착지 · ' + (str(m.label) || str(m.topic) || '') + ' · ' + (isN(m.days) ? n2(m.days) + '일' : '—') + ' · 철회정도 ' + n2(deg) +
          ' · SPX 위협일 ' + (isN(m.spx_threat) ? sf(m.spx_threat, 2) + '%' : '—') + ' · 철회일 ' + (isN(m.spx_retract) ? sf(m.spx_retract, 2) + '%' : '—');
        if (deg <= 0.01) s += '<rect x="' + nf(mx - 5, 1) + '" y="' + (YB - 5) + '" width="10" height="10" fill="none" stroke="' + mc + '" stroke-width="1.6"><title>' + esc(tip) + '</title></rect>';
        else s += '<circle cx="' + nf(mx, 1) + '" cy="' + YB + '" r="' + nf(4 + 3 * deg, 1) + '" fill="' + mc + '" fill-opacity="' + nf(0.25 + 0.7 * deg, 2) + '" stroke="' + mc + '" stroke-width="1.2"><title>' + esc(tip) + '</title></circle>';
      }
      s += '<text x="' + (X0 + 4) + '" y="' + (Y0 - 6) + '" font-size="9.5" fill="#4b5563">● 열린 위협 시작 · ○ 예상 철회(λ) · 하단 마커 = 과거 착지(채움=철회정도)</text>';
      s += '</svg>';
      return s;
    }
  };
  function arcTip(a, t) {
    var parts = [];
    parts.push(str(t.summary_ko) || str(a.label) || String(a.id));
    parts.push('P3 ' + (isN(t.p3) ? n2(t.p3) : '—') + ' · P7 ' + (isN(a.p7) ? n2(a.p7) : (isN(t.p7) ? n2(t.p7) : '—')) + ' · P30 ' + (isN(t.p30) ? n2(t.p30) : '—'));
    parts.push('예상 철회정도 ' + degStr(isN(a.degree_expected) ? a.degree_expected : t.degree_expected, t.degree_band) + (str(t.degree_src) ? ' (' + t.degree_src + ')' : ''));
    parts.push('E[r] 철회 ' + (isN(t.exp_r_retreat_pct) ? sf(t.exp_r_retreat_pct, 2) + '%' : '—') + ' · 유지 ' + (isN(t.exp_r_hold_pct) ? sf(t.exp_r_hold_pct, 2) + '%' : '—'));
    parts.push('위협일 SPX ' + (isN(t.spx_threat_day_pct) ? sf(t.spx_threat_day_pct, 2) + '%' : '—') + ' · 경과 ' + (isN(t.days_open) ? t.days_open + '일' : '—'));
    return parts.join('\n');
  }
  function tacoSummary(taco) {
    var td = obj(taco.today), s = str(td.summary_ko);
    if (s) return s;
    var its = arr(td.items), nT = 0, nR = 0, nH = 0, i, mx = 0;
    for (i = 0; i < its.length; i++) {
      var a = str(its[i] && its[i].act);
      if (a === 'THREAT') nT++; else if (a === 'RETREAT') nR++; else if (a === 'HOLD') nH++;
      if (isN(its[i] && its[i].intensity) && its[i].intensity > mx) mx = its[i].intensity;
    }
    var ot = arr(taco.open_threats).length;
    return '오늘 위협 ' + nT + ' · 유지 ' + nH + ' · 철회 ' + nR + ' — 최고 강도 ' + n2(mx) + ', 열린 위협 ' + ot + '건';
  }
  function rTaco(ST, D) {
    var taco = D.taco;
    var head = '<div class="fd-h"><b>🌮 TACO — Truth Social 발언 엔진</b>' +
      (taco ? '<span class="fd-bd">갱신 ' + kstHM(taco.updated_ts) + ' KST</span>' : '') + '</div>';
    if (!taco) return '<div class="fd-card wide fd-taco" id="fdTaco">' + head + '<p class="fd-hint">TACO 데이터 준비 중…</p></div>';

    var body = '<p class="tsum">' + esc(tacoSummary(taco)) + '</p>';
    var viz = obj(taco.viz), i;

    /* B — 아크 보드 */
    var vt = str(viz.type);
    if (vt && TACO_VIZ[vt]) { try { body += TACO_VIZ[vt](viz, taco); } catch (e) { body += '<p class="fd-hint">시각화 준비 중…</p>'; } }
    else body += '<p class="fd-hint">시각화 준비 중… (viz.type=' + esc(vt || '—') + ')</p>';

    body += '<div class="fd-grid2" style="margin-top:14px">';
    /* A — 오늘 발언 카드 스택 */
    var A = '<div><div class="fd-sec">오늘 발언 (slot A)</div>';
    var its = arr(obj(taco.today).items);
    if (!its.length) A += '<p class="fd-hint">오늘 분류된 포스트 없음</p>';
    for (i = 0; i < its.length; i++) {
      var t = its[i], ac = str(t.act), col = ACT_C[ac] || FLAT;
      A += '<div class="fd-tcard" style="border-left-color:' + col + '">';
      A += '<span class="fd-mono" style="color:var(--dim,#8a93a3)">' + esc(kstFull(t.ts)) + '</span> <b style="color:' + col + '">' + esc(ac || '—') + '</b> ';
      A += esc(str(t.summary_ko) || '—');
      var tg = arr(t.targets);
      A += '<div style="margin-top:3px">';
      for (var j = 0; j < tg.length; j++) A += '<span class="fd-kw">' + esc(tg[j]) + '</span>';
      A += '<span class="fd-kw">강도 ' + n2(t.intensity) + '</span><span class="fd-kw">conf ' + n2(t.conf) + '</span>';
      if (str(t.deadline)) A += '<span class="fd-kw">기한 ' + esc(t.deadline) + '</span>';
      if (str(t.url)) A += ' <a href="' + attr(t.url) + '" target="_blank" rel="noopener" style="color:' + ACC + ';font-size:10px;text-decoration:none">원문 ↗</a>';
      A += '</div>';
      A += '<div style="height:4px;border-radius:2px;background:#1f2937;margin-top:4px"><i style="display:block;height:100%;border-radius:2px;width:' + nf(clamp(isN(t.intensity) ? t.intensity : 0, 0, 1) * 100, 1) + '%;background:' + col + '"></i></div>';
      A += '</div>';
    }
    /* D — 게이지 보조 + 열린 위협 degree_expected */
    var ix = obj(taco.index), cb = obj(taco.calib);
    A += '<div class="fd-sec">지수 · 예상 철회정도 (slot D)</div>';
    A += '<div class="fd-kpi">' +
      '<div><span>TACO_90</span><b style="color:#f5c542">' + n2(ix.taco_90) + '</b></div>' +
      '<div><span>종결 사례</span><b>' + (isN(ix.n_closed) ? ix.n_closed : '—') + '</b></div>' +
      '<div><span>철회율(전체)</span><b>' + n2(ix.retreat_rate_all) + '</b></div>' +
      '<div><span>중앙 소요일</span><b>' + n2(ix.median_days) + '</b></div>' +
      '</div>';
    var ots = arr(taco.open_threats);
    for (i = 0; i < ots.length; i++) {
      A += '<div class="fd-hint" style="padding:2px 0;font-size:11px">· ' + esc(str(ots[i].summary_ko) || ots[i].id) +
        ' — <b style="color:#f5c542">예상 철회정도 ' + esc(degStr(ots[i].degree_expected, ots[i].degree_band)) + '</b>' +
        (str(ots[i].degree_src) ? ' <span style="font-size:10px">(' + esc(ots[i].degree_src) + ')</span>' : '') + '</div>';
    }
    if (isN(cb.hit_rate_p7) || isN(cb.brier)) {
      A += '<div class="fd-hint" style="font-size:10px;padding:2px 0">캘리브레이션 · P7 적중 ' + n2(cb.hit_rate_p7) + ' · Brier ' + n2(cb.brier) + '</div>';
    } else if (str(cb.note)) {
      A += '<div class="fd-hint" style="font-size:10px;padding:2px 0">캘리브레이션 · ' + esc(cb.note) + '</div>';
    }
    A += '</div>';

    /* C — 시장반응 σ 바 + E — 타임라인·주제표·생존 */
    var B = '<div><div class="fd-sec">TACO 시장반응 (slot C)</div>';
    var mk = obj(taco.market), mas = arr(mk.assets);
    if (!mas.length) B += '<p class="fd-hint">시장반응 데이터 대기</p>';
    for (i = 0; i < mas.length; i++) B += sigmaRow(mas[i]);
    B += '<div class="fd-hint" style="font-size:10.5px;padding:3px 0">오늘 기대 ' + unitStr(mk.expected_today_pct, 'pct', 3) + ' · ' + (isN(mk.in_sigma) ? sf(mk.in_sigma, 3) + 'σ' : '—') + ' (σ_ref ' + nf(mk.sigma_ref_pct, 3) + '%)</div>';
    B += '<div class="fd-foot" style="margin-top:4px;border-top:none;padding-top:2px">TACO 시장반응은 1차 SPY 1행(다자산은 후속) — 연준 패널 5자산과 비대칭</div>';

    B += '<div class="fd-sec">타임라인 (slot E)</div>';
    var tl = arr(taco.timeline);
    if (!tl.length) B += '<p class="fd-hint">타임라인 없음</p>';
    else {
      B += '<div class="fd-tl">';
      for (i = 0; i < tl.length; i++) {
        var ph = str(tl[i].phase), pc = PHASE_C[ph] || FLAT;
        if (i) B += '<span class="sl"></span>';
        B += '<span class="st" title="' + attr(kstFull(tl[i].ts) + ' · ' + str(tl[i].label)) + '"><span class="sd" style="background:' + pc + '"></span>' + esc(kstMD(tl[i].ts)) + ' ' + esc(str(tl[i].label).slice(0, 20)) + '</span>';
      }
      B += '</div>';
    }
    var bt = obj(taco.by_topic), ks = Object.keys(bt), rows = '';
    for (i = 0; i < ks.length; i++) {
      var v = bt[ks[i]];
      if (!v || typeof v !== 'object') continue;
      rows += '<tr><td>' + esc(ks[i]) + '</td><td class="n">' + (isN(v.n) ? v.n : '—') + '</td><td class="n">' + n2(v.rate) + '</td><td class="n">' + n2(v.p_shrunk) + '</td><td class="n">' + n2(v.mean_degree) + '</td><td class="n">' + (isN(v.spx_retreat_mean) ? sf(v.spx_retreat_mean, 2) + '%' : '—') + '</td></tr>';
    }
    if (rows) B += '<table class="fd-tb"><tr><th>주제</th><th class="n">n</th><th class="n">철회율</th><th class="n">축소 p</th><th class="n">mean_degree</th><th class="n">철회일 SPX</th></tr>' + rows + '</table>';
    var sv = obj(taco.survival), ll = obj(sv.loglogistic);
    B += '<div class="fd-hint" style="font-size:10.5px;padding:4px 0">생존 · 중앙 ' + n2(ix.median_days) + '일 · log-logistic λ=' + n2(ll.lambda) + ' k=' + n2(ll.k) +
      (arr(sv.S).length ? ' · S(7d)=' + n2(sv.S[3]) + ' S(30d)=' + n2(sv.S[5]) : '') + '</div>';
    B += '</div>';

    body += A + B + '</div>';
    var src = obj(taco.source);
    var foot = '<div class="fd-foot">원문 전문 미게시(자체 요약 + 링크 + 수치) · 출처 ' + esc(str(src.primary) || '—') +
      ' · 24h 포스트 ' + (isN(src.n_posts_24h) ? src.n_posts_24h : '—') + '건' + staleNote(taco) + '</div>';
    return '<div class="fd-card wide fd-taco" id="fdTaco">' + head + body + foot + '</div>';
  }

  /* ══════════════════ 13. 프로필 모달 ══════════════════ */
  var modalEl = null, lastFocus = null;
  function ensureModal() {
    if (modalEl) return modalEl;
    modalEl = document.createElement('div');
    modalEl.className = 'fd-modal';
    if (modalEl.setAttribute) modalEl.setAttribute('class', 'fd-modal');
    modalEl.hidden = true;
    if (document.body && document.body.appendChild) document.body.appendChild(modalEl);
    return modalEl;
  }
  function sparkSVG(hist, col) {
    var hs = arr(hist), W = 300, H = 60, i;
    if (hs.length < 1) return '<p class="fd-hint" style="font-size:11px">점수 이력 없음</p>';
    var xs = hs.length > 1 ? (W - 24) / (hs.length - 1) : 0;
    function Y(v) { return 8 + (1 - (clamp(isN(v) ? v : 0, -1, 1) + 1) / 2) * (H - 20); }
    var pl = '', dots = '';
    for (i = 0; i < hs.length; i++) {
      var x = 12 + xs * i, y = Y(hs[i] && hs[i].pos);
      pl += (i ? ' ' : '') + nf(x, 1) + ',' + nf(y, 1);
      dots += '<circle cx="' + nf(x, 1) + '" cy="' + nf(y, 1) + '" r="2.5" fill="' + col + '"><title>' + esc(str(hs[i].d) + ' · pos ' + nf(hs[i].pos, 2) + ' · abs ' + nf(hs[i].abs, 2) + ' · rel ' + nf(hs[i].rel, 2) + ' · ' + str(hs[i].id)) + '</title></circle>';
    }
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;max-width:320px;height:auto;display:block" role="img" aria-label="최근 성향 점수 추이">' +
      '<line x1="6" y1="' + nf(Y(0), 1) + '" x2="' + (W - 6) + '" y2="' + nf(Y(0), 1) + '" stroke="#6b7280" stroke-width="1" stroke-dasharray="3 4"/>' +
      (hs.length > 1 ? '<polyline points="' + pl + '" fill="none" stroke="' + col + '" stroke-width="1.6"/>' : '') + dots + '</svg>';
  }
  function paneSummary(D, ST, r, p, ring) {
    var pr = obj(r && r.profile), vw = obj(pr.views);
    var h = '<div class="fd-kpi">' +
      '<div><span>성향 s</span><b style="color:' + ring + '">' + (p && isN(p.pos) ? sf(p.pos, 2) : '—') + '</b></div>' +
      '<div><span>Δ 30d</span><b style="color:' + (p && isN(p.delta_30d) ? (p.delta_30d > 0 ? HAWK : DOVE) : FLAT) + '">' + (p ? sf(p.delta_30d, 2) : '—') + '</b></div>' +
      '<div><span>헤드라인 ' + esc(ST.hf) + '</span><b>' + (p ? nf(hfOf(p, ST.hf), 0) : '—') + '</b></div>' +
      '<div><span>발언 90d</span><b>' + (p && isN(p.n_statements_90d) ? p.n_statements_90d : '—') + '</b></div>' +
      '</div>';
    if (p) {
      h += '<div class="fd-hint" style="font-size:10.5px;padding:2px 0">판정 ' + esc(str(p.label_ko) || '—') + ' · 신뢰도 ' + confDots(p.conf) +
        ' · 기준선 ' + nf(p.baseline, 3) + '(' + esc(str(p.baseline_src) || '—') + ')' +
        ' · seed ' + nf(p.seed, 2) + (p.cold_start === true ? ' · <b style="color:#ff8a3d">콜드스타트</b>(정책성 발언 ' + (isN(p.n_policy_90d) ? p.n_policy_90d : '—') + '건 — 이탈·알림 제외)' : '') + '</div>';
    } else {
      h += '<p class="fd-hint">성향 채점 대기 — 로스터에는 반영됐으나 아직 점수가 계산되지 않았습니다.</p>';
    }
    h += '<div class="fd-sec">전문분야</div>';
    var ex = arr(pr.expertise), i;
    if (ex.length) { h += '<div>'; for (i = 0; i < ex.length; i++) h += '<span class="fd-kw">' + esc(ex[i]) + '</span>'; h += '</div>'; }
    else h += '<p class="fd-hint">프로필 수집 대기' + (str(pr.status) ? ' (' + esc(pr.status) + ')' : '') + '</p>';
    h += '<div class="fd-sec">미국 경제관</div><p class="fd-hint">' + (str(vw.economy) ? esc(vw.economy) : '수집 대기') + '</p>';
    h += '<div class="fd-sec">현재 금리관</div><p class="fd-hint">' + (str(vw.rates) ? esc(vw.rates) : '수집 대기') +
      (str(vw.rates_as_of) ? ' <span style="font-size:10px">(' + esc(vw.rates_as_of) + ')</span>' : '') +
      (str(vw.rates_src) ? ' <a href="' + attr(vw.rates_src) + '" target="_blank" rel="noopener" style="color:' + ACC + '">출처 ↗</a>' : '') + '</p>';
    h += '<div class="fd-sec">최근 점수 추이</div>' + sparkSVG(p && p.history, ring);
    return h;
  }
  function paneStatements(D, ST, pid, ring) {
    var items = arr(obj(D.statements).items).filter(function (x) { return x && x.pid === pid && !str(x.superseded_by); });
    if (!items.length) return '<p class="fd-hint">이 인사의 발언 기록이 없습니다.</p>';
    items.sort(function (a, b) { return (isN(b.ts) ? b.ts : 0) - (isN(a.ts) ? a.ts : 0); });
    var show = items.slice(0, 10), h = '', i;
    for (i = 0; i < show.length; i++) {
      var it = show[i];
      h += '<div class="fd-tcard" style="border-left-color:' + scoreColor(it.abs, true) + '">';
      h += '<span class="fd-mono" style="color:var(--dim,#8a93a3)">' + esc(kstFull(it.ts)) + '</span> · ' + esc(KIND_KO[str(it.kind)] || str(it.kind) || '—') + '<br>';
      h += (str(it.url) ? '<a href="' + attr(it.url) + '" target="_blank" rel="noopener" style="color:var(--ink,#e6edf3);text-decoration:none">' + esc(str(it.title) || it.id) + ' ↗</a>' : esc(str(it.title) || it.id));
      h += '<div class="fd-meta">abs <b style="color:' + scoreColor(it.abs, true) + '">' + sf(it.abs, 2) + '</b> ' + esc(str(it.label_ko) || '') +
        ' · rel <b>' + sf(it.rel, 2) + '</b> ' + esc(str(it.rel_label_ko) || '') +
        (it.deviation === true ? ' · <span style="color:#ff4d5e">⚡ 이탈</span>' : '') + '</div>';
      h += '</div>';
    }
    if (items.length > show.length) h += '<p class="fd-hint">더보기 — 총 ' + items.length + '건 중 10건 표시(피드 탭에서 전체 확인)</p>';
    return h;
  }
  function paneHoldings(r) {
    var hd = obj(r && r.holdings), st = str(hd.status);
    var src = str(hd.source_url) ? ' <a href="' + attr(hd.source_url) + '" target="_blank" rel="noopener" style="color:' + ACC + '">원문 ↗</a>' : '';
    if (st === 'ocr_pending') {
      return '<p class="fd-hint">스캔 공시 — OCR 대기(미니)' + (isN(hd.pages) ? ' · ' + hd.pages + '쪽' : '') + (str(hd.form) ? ' · ' + esc(hd.form) : '') + src + '</p>';
    }
    if (st === 'pending') {
      return '<p class="fd-hint">공시 수집 대기' + (str(hd.reason) ? ' — ' + esc(hd.reason) : '') + src + '</p>';
    }
    if (st === 'unavailable') {
      return '<p class="fd-hint">공시 접근 불가 — ' + esc(str(hd.reason) || '사유 미기록') + src + '</p>';
    }
    if (st !== 'ok') return '<p class="fd-hint">공시 상태 미확인' + src + '</p>';

    var sm = obj(hd.summary), rows = arr(hd.rows), txs = arr(hd.transactions), lbs = arr(hd.liabilities), i;
    var lo = 0, hi = 0, hiOpen = false;
    for (i = 0; i < rows.length; i++) {
      var v = obj(rows[i] && rows[i].value);
      if (isN(v.lo)) lo += v.lo;
      if (isN(v.hi)) hi += v.hi; else if (isN(v.lo)) { hi += v.lo; hiOpen = true; }
    }
    var h = '<div class="fd-kpi">' +
      '<div><span>신고 구간 합</span><b style="font-size:12px">' + (rows.length ? usd(lo) + '–' + usd(hi) + (hiOpen ? '+' : '') : '—') + '</b></div>' +
      '<div><span>행 수</span><b>' + (isN(sm.n_rows) ? sm.n_rows : rows.length) + '</b></div>' +
      '<div><span>개별주식</span><b style="font-size:12px">' + (arr(sm.single_stocks).length ? esc(arr(sm.single_stocks).join(', ')) : '—') + '</b></div>' +
      '<div><span>12개월 거래</span><b>' + (isN(sm.n_transactions_12m) ? sm.n_transactions_12m : txs.length) + '</b></div>' +
      '</div>';
    h += donutSVG(obj(sm.by_class));
    if (str(sm.rate_sensitivity)) h += '<p class="fd-hint" style="font-size:11px">금리 민감도 — ' + esc(sm.rate_sensitivity) + '</p>';

    if (rows.length) {
      h += '<table class="fd-htb"><tr><th>자산명</th><th>유형</th><th>구간</th><th>소유자</th><th>EIF</th><th class="n">연도</th></tr>';
      for (i = 0; i < rows.length; i++) {
        var rw = rows[i], vv = obj(rw.value);
        h += '<tr class="fd-hrow"><td>' + esc(str(rw.name) || str(rw.desc_raw) || '—') + (str(rw.ticker) ? ' <span class="fd-mono" style="color:var(--dim,#8a93a3)">' + esc(rw.ticker) + '</span>' : '') + '</td>' +
          '<td>' + esc(CLS_KO[str(rw.asset_class)] || str(rw.asset_class) || '—') + '</td>' +
          '<td class="n">' + esc(str(vv.raw) || rangeUsd(vv.lo, vv.hi)) + '</td>' +
          '<td>' + esc(OWN_KO[str(rw.owner)] || str(rw.owner) || '—') + '</td>' +
          '<td>' + (rw.eif === true ? '✓' : (rw.eif === false ? '—' : '·')) + '</td>' +
          '<td class="n">' + (isN(hd.report_year) ? hd.report_year : '—') + '</td></tr>';
      }
      h += '</table>';
    }
    if (txs.length) {
      h += '<div class="fd-sec">최근 거래 (278-T/PTR)</div>';
      h += '<table class="fd-htb"><tr><th>일자</th><th>자산</th><th>구분</th><th>금액 구간</th><th>공개일</th></tr>';
      for (i = 0; i < Math.min(10, txs.length); i++) {
        var tx = txs[i], am = obj(tx.amount);
        h += '<tr class="fd-trow"><td class="n">' + esc(str(tx.date) || '—') + '</td>' +
          '<td>' + esc(str(tx.desc) || '—') + '</td>' +
          '<td>' + esc(TXN_KO[str(tx.type)] || str(tx.type) || '—') + '</td>' +
          '<td class="n">' + esc(str(am.raw) || rangeUsd(am.lo, am.hi)) + '</td>' +
          '<td class="n">' + esc(str(tx.published) || '—') + '</td></tr>';
      }
      h += '</table>';
      if (txs.length > 10) h += '<p class="fd-hint" style="font-size:10px">총 ' + txs.length + '건 중 최근 10건</p>';
    }
    if (lbs.length) {
      h += '<div class="fd-sec">부채</div>';
      h += '<table class="fd-htb"><tr><th>채권자</th><th>유형</th><th>구간</th><th class="n">연도</th></tr>';
      for (i = 0; i < lbs.length; i++) {
        var lb = lbs[i], la = obj(lb.amount);
        h += '<tr class="fd-lrow"><td>' + esc(str(lb.creditor) || '—') + '</td><td>' + esc(str(lb.type) || '—') + '</td>' +
          '<td class="n">' + esc(str(la.raw) || rangeUsd(la.lo, la.hi)) + '</td><td class="n">' + (isN(lb.year) ? lb.year : '—') + '</td></tr>';
      }
      h += '</table>';
    }
    h += '<div class="fd-foot">' + esc(str(hd.form) || 'OGE 278e / 연은 Form A') + ' · 신고연도 ' + (isN(hd.report_year) ? hd.report_year : '—') +
      (str(hd.filed) ? ' · 제출 ' + esc(hd.filed) : '') + ' · 추출 ' + esc(str(hd.extraction) || '—') + ' · 금액은 공시 구간값' + src + '</div>';
    return h;
  }
  function donutSVG(byClass) {
    var ks = Object.keys(obj(byClass)), i, tot = 0;
    for (i = 0; i < ks.length; i++) if (isN(byClass[ks[i]])) tot += byClass[ks[i]];
    if (!(tot > 0)) return '';
    var COLS = ['#2bc0d4', '#59d0a8', '#ffd23d', '#ff8a3d', '#ff4d5e', '#4ea1ff', '#9b7bff', '#8a93a3'];
    var a0 = -Math.PI / 2, s = '<svg viewBox="0 0 120 120" style="width:120px;height:120px;display:inline-block" role="img" aria-label="유형별 비중">', lg = '';
    for (i = 0; i < ks.length; i++) {
      var v = isN(byClass[ks[i]]) ? byClass[ks[i]] : 0;
      if (v <= 0) continue;
      var a1 = a0 + v / tot * Math.PI * 2, big = (a1 - a0) > Math.PI ? 1 : 0, c = COLS[i % COLS.length];
      var x0 = 60 + 46 * Math.cos(a0), y0 = 60 + 46 * Math.sin(a0), x1 = 60 + 46 * Math.cos(a1), y1 = 60 + 46 * Math.sin(a1);
      s += '<path d="M' + nf(x0, 1) + ',' + nf(y0, 1) + ' A46,46 0 ' + big + ' 1 ' + nf(x1, 1) + ',' + nf(y1, 1) + '" fill="none" stroke="' + c + '" stroke-width="16"><title>' + esc(CLS_KO[ks[i]] || ks[i]) + ' ' + nf(v / tot * 100, 1) + '%</title></path>';
      lg += '<span class="fd-kw" style="border-color:' + c + ';color:' + c + '">' + esc(CLS_KO[ks[i]] || ks[i]) + ' ' + nf(v / tot * 100, 0) + '%</span>';
      a0 = a1;
    }
    s += '</svg>';
    return '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">' + s + '<div style="flex:1;min-width:120px">' + lg + '</div></div>';
  }
  function panePapers(r) {
    var pr = obj(r && r.profile), ps = arr(pr.papers), ex = arr(pr.expertise), h = '', i;
    if (ex.length) { h += '<div>'; for (i = 0; i < ex.length; i++) h += '<span class="fd-kw">' + esc(ex[i]) + '</span>'; h += '</div>'; }
    if (ps.length) {
      h += '<table class="fd-htb"><tr><th class="n">연도</th><th>제목</th><th>게재지</th><th class="n">피인용</th></tr>';
      for (i = 0; i < ps.length; i++) {
        var pp = ps[i];
        h += '<tr><td class="n">' + (isN(pp.year) ? pp.year : '—') + '</td>' +
          '<td>' + (str(pp.url) ? '<a href="' + attr(pp.url) + '" target="_blank" rel="noopener" style="color:var(--ink,#e6edf3);text-decoration:none">' + esc(str(pp.title) || '—') + ' ↗</a>' : esc(str(pp.title) || '—')) + '</td>' +
          '<td>' + esc(str(pp.venue) || str(pp.host_venue) || '—') + '</td>' +
          '<td class="n">' + (isN(pp.cited_by_count) ? pp.cited_by_count : '—') + '</td></tr>';
      }
      h += '</table>';
    } else {
      h += '<p class="fd-hint">논문 목록 없음' + (str(pr.status) ? ' (' + esc(pr.status) + ')' : '') + ' — OpenAlex 수집 대기이거나 학술 이력이 없는 인사입니다.</p>';
    }
    if (str(r && r.openalex_id)) h += '<p class="fd-hint" style="font-size:10.5px">OpenAlex <a href="' + attr('https://openalex.org/' + r.openalex_id) + '" target="_blank" rel="noopener" style="color:' + ACC + '">' + esc(r.openalex_id) + ' ↗</a></p>';
    if (str(r && r.bio_url)) h += '<p class="fd-hint" style="font-size:10.5px">약력 <a href="' + attr(r.bio_url) + '" target="_blank" rel="noopener" style="color:' + ACC + '">' + esc(hostOf(r.bio_url)) + ' ↗</a></p>';
    return h;
  }
  function modalHTML(D, ST, pid, tab) {
    var r = personOf(D, pid), p = posOf(D, pid);
    var ring = ringOfPid(D, pid, ST.neutralRing);
    var nm = (r && str(r.name)) || pid;
    var sub = [(r && str(r.title)) || '', (r && str(r.bank)) || '', ORG_KO[(r && r.org)] || ''].filter(function (x) { return x; }).join(' · ');
    var ini = r ? initialsOf({ r: r, id: pid }) : String(pid || '?').slice(0, 2).toUpperCase();
    var policyMode = (obj(D.roster).photo_policy && obj(D.roster).photo_policy.mode) || 'pd_only';
    var showImg = photoUsable(r, policyMode);
    var av = '<svg width="64" height="64" viewBox="-32 -32 64 64" aria-hidden="true"><circle r="29" fill="none" stroke="' + ring + '" stroke-width="' + (r && r.role === 'chair' ? 3.5 : 2.5) + '"' + (r && r.voter === true ? '' : ' stroke-dasharray="4 3"') + '/><circle r="26" fill="' + ring + '2e"/>' +
      '<text y="6" text-anchor="middle" font-size="17" font-weight="800" fill="#e6edf3">' + esc(ini) + '</text>' +
      (showImg ? '<clipPath id="mclip-' + attr(pid) + '"><circle r="26"/></clipPath><image class="fd-photo" href="' + attr(r.photo) + '" xlink:href="' + attr(r.photo) + '" x="-26" y="-26" width="52" height="52" preserveAspectRatio="xMidYMin slice" clip-path="url(#mclip-' + attr(pid) + ')"/>' : '') + '</svg>';
    var mg = '';
    if (p && isN(p.pos)) {
      var pctp = (clamp(p.pos, -1, 1) + 1) / 2 * 100;
      mg = '<div style="flex:0 0 140px"><div class="fd-g" style="margin:0"><span class="gt" style="background:linear-gradient(90deg,' + DOVE + ',#fff,' + HAWK + ');opacity:.85">' +
        '<i style="position:absolute;left:' + nf(pctp, 1) + '%;top:-1.5px;width:12px;height:12px;border-radius:50%;background:' + ring + ';border:2px solid #0d131c;transform:translateX(-6px);display:block"></i></span>' +
        '<span class="gv" style="color:' + ring + '">' + sf(p.pos, 2) + '</span></div></div>';
    }
    var h = '<div class="fd-sheet" role="dialog" aria-modal="true" aria-labelledby="fdmTitle" tabindex="-1">';
    h += '<div class="fd-mhead">' + av + '<div><h3 id="fdmTitle">' + esc(nm) + '</h3><div class="mt">' + esc(sub || '—') + '</div></div>';
    if (r && r.voter === true) h += '<span class="fd-bd vote">2026 투표권</span>';
    else if (r && r.alternate === true) h += '<span class="fd-bd">대리(alternate)</span>';
    else h += '<span class="fd-bd">비투표</span>';
    h += mg + '<button type="button" class="fd-x" data-act="close" aria-label="닫기">✕</button></div>';
    var TABS = [['summary', '요약'], ['statements', '발언 이력'], ['holdings', '보유자산'], ['papers', '논문·전문']], i;
    h += '<div class="fd-chips fd-tabs" role="tablist" aria-label="프로필 정보">';
    for (i = 0; i < TABS.length; i++) h += '<button type="button" class="fd-chip' + (tab === TABS[i][0] ? ' on' : '') + '" role="tab" id="fdm-tab-' + TABS[i][0] + '" aria-controls="fdm-pane-' + TABS[i][0] + '" aria-selected="' + (tab === TABS[i][0]) + '" tabindex="' + (tab === TABS[i][0] ? '0' : '-1') + '" data-fk="modalTab" data-fv="' + TABS[i][0] + '">' + TABS[i][1] + '</button>';
    h += '</div><div class="fd-body">';
    var panes = [paneSummary(D, ST, r, p, ring), paneStatements(D, ST, pid, ring), paneHoldings(r), panePapers(r)];
    for (i = 0; i < TABS.length; i++) {
      h += '<section class="fd-pane' + (tab === TABS[i][0] ? ' on' : '') + '" id="fdm-pane-' + TABS[i][0] + '" role="tabpanel" aria-labelledby="fdm-tab-' + TABS[i][0] + '" data-pane="' + TABS[i][0] + '"' + (tab === TABS[i][0] ? '' : ' hidden') + '>' +
        panes[i].replace(/<table class="fd-htb">/g, '<div class="fd-table-scroll" role="region" aria-label="' + TABS[i][1] + ' 표, 좌우로 스크롤" tabindex="0"><table class="fd-htb">').replace(/<\/table>/g, '</table></div>') + '</section>';
    }
    if (r && r._fdPortraitVerified && showImg) h += '<div class="fd-foot">사진 · <a href="' + attr(r.photo_source_page) + '" target="_blank" rel="noopener" style="color:' + ACC + '">' + esc(r.photo_credit || '공식 약력') + ' ↗</a></div>';
    var nt = arr(r && r.notes);
    if (nt.length) { h += '<div class="fd-foot">'; for (i = 0; i < nt.length; i++) h += (i ? '<br>' : '') + '· ' + esc(nt[i]); h += '</div>'; }
    h += '</div></div>';
    return h;
  }

  /* ══════════════════ 14. renderFed ══════════════════ */
  var DEFAULTS = {
    group: 'all', hf: '30d', scale: 'sqrt', arrows: true, names: true, neutralRing: true,
    feedGroup: 'all', feedKind: 'all', feedDev: false, feedSort: 'recent',
    calStar: '2', calRange: '7d', modalTab: 'summary'
  };
  var BOOLS = { arrows: 1, names: 1, neutralRing: 1, feedDev: 1 };

  function each(list, fn) { if (!list) return; for (var i = 0; i < list.length; i++) fn(list[i], i); }
  function qa(root, sel) { return (root && root.querySelectorAll) ? (root.querySelectorAll(sel) || []) : []; }

  function renderFed(el, data, opts) {
    injectCSS();
    if (!el) return null;
    ensureModal();                    // body 부작용은 모달 1개뿐(최초 renderFed 때 append)
    var rawData = Object.assign({}, obj(data)), D = withPortraits(rawData);
    var ST = {}, k;
    for (k in DEFAULTS) if (Object.prototype.hasOwnProperty.call(DEFAULTS, k)) ST[k] = DEFAULTS[k];
    var O = obj(opts);
    for (k in O) if (Object.prototype.hasOwnProperty.call(O, k) && k !== 'now') ST[k] = O[k];
    ST.now = isN(O.now) ? O.now : Math.floor(Date.now() / 1000);
    var openPid = null, openTab = ST.modalTab, tabScroll = {}, bodyOverflow = null;

    function haveCore() {
      return !!(D.roster || D.positions);
    }
    function render() {
      if (!haveCore()) { el.innerHTML = '<p class="fd-hint" style="padding:20px">연준 데이터 준비 중…</p>'; return; }
      var h = '<div class="fd-wrap">' + defsSVG() + rHero(ST, D) + rNav(ST);
      h += '<div class="fd-grid">' + rCal(ST, D) + rDist(ST, D) + '</div>';
      h += rPeople(ST, D);
      h += '<div class="fd-grid2">' + rFeed(ST, D) + rReact(ST, D) + '</div>';
      h += rTaco(ST, D);
      h += '<div class="fd-tip" id="fdTip"></div>';
      h += '</div>';
      el.innerHTML = h;
      bind();
      bindPhotos(el);
    }
    function setState(patch) {
      var kk;
      for (kk in obj(patch)) if (Object.prototype.hasOwnProperty.call(patch, kk)) ST[kk] = patch[kk];
      render();
      return ST;
    }
    function renderFilter(key) {
      var id = '', html = '';
      if (/^(group|hf|scale|arrows|names|neutralRing)$/.test(key)) { id = 'fdDist'; html = rDist(ST, D); }
      else if (/^feed(Group|Kind|Dev|Sort)$/.test(key)) { id = 'fdFeed'; html = rFeed(ST, D); }
      else if (/^cal(Star|Range)$/.test(key)) { id = 'fdCal'; html = rCal(ST, D); }
      var current = id && el.querySelector ? el.querySelector('#' + id) : null;
      if (!current || !current.parentNode) { render(); return; }
      function replaceCard(card, markup) {
        var holder = document.createElement('div'); holder.innerHTML = markup;
        var next = holder.firstElementChild;
        if (!next) return false;
        card.parentNode.replaceChild(next, card); bind(next); bindPhotos(next); return true;
      }
      if (!replaceCard(current, html)) { render(); return; }
      if (key === 'neutralRing') {
        var people = el.querySelector('#fdPeople');
        if (people) replaceCard(people, rPeople(ST, D));
      }
    }
    function bind(root) {
      root = root || el;
      var tip = null;
      try { tip = el.querySelector ? el.querySelector('#fdTip') : null; } catch (e) { tip = null; }
      each(qa(root, '[data-fk]'), function (b) {
        b.addEventListener('click', function () {
          var kk = b.getAttribute ? b.getAttribute('data-fk') : null;
          var vv = b.getAttribute ? b.getAttribute('data-fv') : null;
          if (!kk) return;
          if (BOOLS[kk]) ST[kk] = (vv === '1');
          else ST[kk] = vv;
          if (kk === 'modalTab') { openTab = vv; if (openPid) { openProfile(openPid, vv); return; } }
          renderFilter(kk);
          // 필터를 눌러도 키보드 초점과 화면 위치를 유지한다.
          var replacement = null;
          each(qa(el, '[data-fk]'), function (c) {
            if (c.getAttribute('data-fk') === kk && (!replacement || c.getAttribute('data-fv') === vv)) replacement = c;
          });
          safeFocus(replacement);
        });
      });
      each(qa(root, '[data-go]'), function (b) {
        b.addEventListener('click', function () {
          var id = b.getAttribute('data-go'), t = el.querySelector ? el.querySelector('#' + id) : null;
          var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
          if (t && t.scrollIntoView) {
            var nav = el.querySelector ? el.querySelector('.fd-nav') : null;
            var navHeight = nav && nav.getBoundingClientRect ? nav.getBoundingClientRect().height : 0;
            var viewPadding = 0;
            try {
              var computed = window.getComputedStyle ? window.getComputedStyle(el) : null;
              var padding = computed ? parseFloat(computed.paddingTop) : 0;
              if (isN(padding) && padding > 0) viewPadding = padding;
            } catch (e) { /* 스타일 실측이 불가능하면 기본 여백 유지 */ }
            if (t.style) t.style.scrollMarginTop = (isN(navHeight) && navHeight > 0 ? Math.ceil(navHeight + viewPadding) + 12 : 72) + 'px';
            t.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
          }
        });
      });
      each(qa(root, '[data-act="speak"]'), function (b) {
        b.addEventListener('click', function () {
          try { if (window.PV && window.PV.speak) window.PV.speak(briefText(D)); } catch (e) { }
        });
      });
      each(qa(root, '.fd-sum'), function (b) {
        b.addEventListener('click', function () { if (b.classList) b.classList.toggle('open'); });
      });
      each(qa(root, '.fd-node'), function (g) {
        var pid = g.getAttribute ? g.getAttribute('data-id') : null;
        g.addEventListener('click', function () { openProfile(pid); });
        g.addEventListener('keydown', function (ev) {
          if (ev && (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar')) { if (ev.preventDefault) ev.preventDefault(); openProfile(pid); }
        });
        if (tip) {
          g.addEventListener('mousemove', function (ev) { showTip(tip, ev, nodeTipHTML(pid)); });
          g.addEventListener('mouseleave', function () { hideTip(tip); });
          g.addEventListener('focus', function () { });
        }
      });
      each(qa(root, '.cav'), function (a) {
        a.addEventListener('click', function (ev) { if (ev && ev.stopPropagation) ev.stopPropagation(); openProfile(a.getAttribute('data-pid')); });
      });
      each(qa(root, '[data-profile]'), function (b) {
        b.addEventListener('click', function () { openProfile(b.getAttribute('data-profile')); });
      });
      if (tip) each(qa(root, '.fd-arcg'), function (g) {
        var tid = g.getAttribute ? g.getAttribute('data-tid') : null;
        g.addEventListener('mousemove', function (ev) { showTip(tip, ev, arcTipHTML(tid)); });
        g.addEventListener('mouseleave', function () { hideTip(tip); });
      });
    }
    function showTip(tip, ev, html) {
      if (!tip) return;
      tip.innerHTML = html;
      if (tip.classList) tip.classList.add('on');
      if (tip.style) {
        var x = (ev && isN(ev.clientX)) ? ev.clientX : 0, y = (ev && isN(ev.clientY)) ? ev.clientY : 0;
        tip.style.left = (x + 14) + 'px'; tip.style.top = (y + 14) + 'px';
      }
    }
    function hideTip(tip) { if (tip && tip.classList) tip.classList.remove('on'); }
    function nodeTipHTML(pid) {
      var r = personOf(D, pid), p = posOf(D, pid);
      var nm = (r && str(r.name)) || pid;
      var h = '<b>' + esc(nm) + '</b><br>' + esc((r && str(r.title)) || '') + (r && str(r.bank) ? ' · ' + esc(r.bank) : '') + '<br>';
      if (p) {
        h += 's ' + sf(p.pos, 2) + ' (' + esc(str(p.label_ko) || '—') + ') · Δ30d ' + sf(p.delta_30d, 2) + '<br>';
        h += 'hf ' + esc(ST.hf) + ' ' + nf(hfOf(p, ST.hf), 0) + '건 · conf ' + nf(p.conf, 2);
      } else h += '채점 대기(성향 미확정)';
      var last = lastLine(pid, arr(obj(D.statements).items));
      if (last) h += '<br>' + esc(last.replace(/^ · /, ''));
      return h;
    }
    function arcTipHTML(tid) {
      var viz = obj(obj(D.taco).viz), arcs = arr(viz.arcs), idx = threatByIdx(D.taco), i, a = null;
      for (i = 0; i < arcs.length; i++) if (arcs[i] && String(arcs[i].id) === String(tid)) a = arcs[i];
      if (!a) return '';
      return esc(arcTip(a, idx[a.id] || {})).replace(/\n/g, '<br>');
    }
    function safeFocus(target) {
      if (!target || !target.focus) return;
      try { target.focus({ preventScroll: true }); } catch (e) { target.focus(); }
    }
    function switchTab(tab, focusTab) {
      if (!/^(summary|statements|holdings|papers)$/.test(tab)) tab = 'summary';
      var m = ensureModal(), scroller = m.querySelector ? m.querySelector('.fd-body') : null;
      if (scroller) tabScroll[openTab] = scroller.scrollTop;
      openTab = tab; ST.modalTab = tab;
      each(qa(m, '[role="tab"]'), function (b) {
        var on = b.getAttribute('data-fv') === tab;
        if (b.classList) b.classList.toggle('on', on);
        b.setAttribute('aria-selected', String(on)); b.setAttribute('tabindex', on ? '0' : '-1');
        if (on && focusTab) safeFocus(b);
      });
      each(qa(m, '[data-pane]'), function (pane) {
        var on = pane.getAttribute('data-pane') === tab;
        if (pane.classList) pane.classList.toggle('on', on);
        pane.hidden = !on;
      });
      if (scroller) scroller.scrollTop = tabScroll[tab] || 0;
    }
    function openProfile(pid, tab) {
      if (!pid) return;
      var m = ensureModal();
      if (openPid === pid && m.hidden === false) { switchTab(str(tab) || openTab, true); return; }
      if (m.hidden !== false) {
        try { lastFocus = document.activeElement || null; } catch (e) { lastFocus = null; }
        if (document.body && document.body.style) {
          bodyOverflow = document.body.style.overflow;
          document.body.style.overflow = 'hidden';
        }
      }
      openPid = pid; openTab = str(tab) || openTab || 'summary'; tabScroll = {};
      if (!/^(summary|statements|holdings|papers)$/.test(openTab)) openTab = 'summary';
      m.innerHTML = modalHTML(D, ST, pid, openTab);
      m.hidden = false;
      bindPhotos(m);
      hideTip(el.querySelector ? el.querySelector('#fdTip') : null);
      each(qa(m, '[data-act="close"]'), function (b) { b.addEventListener('click', closeProfile); });
      each(qa(m, '[role="tab"]'), function (b) {
        b.addEventListener('click', function () { switchTab(b.getAttribute('data-fv'), true); });
      });
      m.onclick = function (ev) { if (ev && ev.target === m) closeProfile(); };
      // 모달 재개방마다 하나의 핸들러만 교체한다. 숨긴 패널의 링크는 초점 순서에서 제외한다.
      m.onkeydown = function (ev) {
        if (!ev) return;
        if (ev.key === 'Escape' || ev.key === 'Esc') {
          if (ev.preventDefault) ev.preventDefault();
          if (ev.stopPropagation) ev.stopPropagation();
          closeProfile(); return;
        }
        var act = document.activeElement;
        if (act && act.getAttribute && act.getAttribute('role') === 'tab') {
          var tabs = qa(m, '[role="tab"]'), idx = 0, next = -1;
          each(tabs, function (t, i) { if (t === act) idx = i; });
          if (ev.key === 'ArrowRight') next = (idx + 1) % tabs.length;
          else if (ev.key === 'ArrowLeft') next = (idx + tabs.length - 1) % tabs.length;
          else if (ev.key === 'Home') next = 0;
          else if (ev.key === 'End') next = tabs.length - 1;
          if (next >= 0) {
            if (ev.preventDefault) ev.preventDefault();
            switchTab(tabs[next].getAttribute('data-fv'), true); return;
          }
        }
        if (ev.key !== 'Tab') return;
        var f = [];
        each(qa(m, 'button,a[href],[tabindex]:not([tabindex="-1"])'), function (n) {
          if (!n.disabled && n.getAttribute('tabindex') !== '-1' && !(n.closest && n.closest('[hidden]'))) f.push(n);
        });
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1], sheet = m.querySelector ? m.querySelector('.fd-sheet') : null;
        if (ev.shiftKey && (act === first || act === sheet)) { if (ev.preventDefault) ev.preventDefault(); safeFocus(last); }
        else if (!ev.shiftKey && (act === last || act === sheet)) { if (ev.preventDefault) ev.preventDefault(); safeFocus(first); }
      };
      safeFocus(m.querySelector ? m.querySelector('.fd-sheet') : null);
    }
    function closeProfile() {
      openPid = null;
      if (modalEl) { modalEl.hidden = true; modalEl.innerHTML = ''; modalEl.onclick = null; modalEl.onkeydown = null; }
      if (bodyOverflow !== null && document.body && document.body.style) document.body.style.overflow = bodyOverflow;
      bodyOverflow = null;
      try { if (lastFocus && lastFocus.isConnected !== false) safeFocus(lastFocus); } catch (e) { }
      lastFocus = null;
    }

    render();
    return {
      refresh: function (nd) {
        if (nd && typeof nd === 'object') { var kk; for (kk in nd) if (Object.prototype.hasOwnProperty.call(nd, kk)) rawData[kk] = nd[kk]; }
        D = withPortraits(rawData);
        ST.now = Math.floor(Date.now() / 1000);
        render();
      },
      openProfile: openProfile,
      closeProfile: closeProfile,
      setState: setState,
      state: ST
    };
  }

  if (typeof window !== 'undefined') {
    window.renderFed = renderFed;
    window.__fedLayout = layoutNodes;   // 테스트 훅(유일한 추가 전역)
  }
})();
