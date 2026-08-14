/* liq_charts_v2.js — 유동성 대시보드 v2 렌더러 + 기대 인플레이션 섹션 (의존성 0)
 *
 *   window.renderLiq2(el, data)
 *     el   : 렌더 대상 컨테이너 엘리먼트
 *     data : liquidity2.json 전체 객체
 *
 * 설계 요점 (스케일 문제 해결)
 *   · y도메인은 "표시 윈도(기간칩)" 데이터만으로 min/max + 4% 패딩 — 전 구간이 아님.
 *     → 최근 변화가 화면 높이를 실제로 채운다.
 *   · SOFR/EFFR은 절대금리가 아니라 IORB 대비 스프레드(bp) 시계열을 그린다.
 *   · 기준선은 표시 윈도 도메인 안에 들어올 때만 그린다(도메인 강제확장 금지).
 *
 * v2 추가 (④ 기대 인플레이션)
 *   · chartSVG 가 다중 라인(10Y BEI + 5Y5Y) 과 밴드 음영(1.85~2.15) 을 지원한다.
 *     스케일 규칙은 그대로 — y도메인은 표시 윈도 값만으로 잡고, 기준선/밴드는 도메인을 넓히지 않는다
 *     (밴드는 도메인에 맞춰 클립, 기준선이 구간 밖이면 가장자리에 '구간 밖' 캡션만 남긴다).
 *   · 스프레드(10Y BEI − 5Y5Y) 시계열은 렌더러에서 파생 — JSON 스키마는 건드리지 않는다.
 *   · 해석 블록: BEI 정의/프리미엄 구성 → 스윙은 중단기 → 5Y5Y 앵커 게이지 → 항등식 괴리(bp).
 *
 * 로드 시 부작용 없음 — window.renderLiq2 정의만 한다. CSS는 첫 렌더에서 1회 주입.
 */
(function () {
  'use strict';

  /* ── 팔레트 ─────────────────────────────────────────────────────────── */
  var LC = { green: '#3ddc97', yellow: '#ffd23d', orange: '#ff8a3d', red: '#ff4d5e', gray: '#8a93a3' };
  var LL = { green: '초록불', yellow: '노란불', orange: '주황불', red: '빨간불', gray: '—' };
  var UP = '#ff4d5e';    // 나쁜 방향
  var DOWN = '#4ea1ff';  // 좋은 방향
  var NEUTRAL = '#8a93a3';

  /* 지표별 bad_direction — 어느 쪽으로 움직이면 "나쁜" 것인지.
     배지 색은 부호가 아니라 이 방향성에 맞춘다.
       NETLIQ↓ = 유동성 긴축 = 빨강 / HY_OAS↑ = 크레딧 악화 = 빨강
       VIX↑ = 빨강 / USDKRW↑ = 원화 약세·자금이탈 = 빨강                        */
  var BAD_DIR = {
    NETLIQ: 'down', TGA: 'up', RRP: 'down', RESERVES: 'down',
    SOFR_IORB_BP: 'up', EFFR_IORB_BP: 'up',
    HY_OAS: 'up', IG_OAS: 'up', T10Y2Y: 'down', NFCI: 'up',
    DXY: 'up', USDKRW: 'up', USDJPY: 'up', VIX: 'up'
  };

  var RANGES = [['3M', 3], ['6M', 6], ['1Y', 12], ['ALL', 0]];
  var DEFAULT_RANGE = '6M';

  /* ── 포맷 유틸 ──────────────────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(v, dp) {
    if (v == null || isNaN(v)) return '—';
    var s = Number(v).toFixed(dp == null ? 2 : dp);
    var p = s.split('.');
    p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return p.join('.');
  }
  function sgn(v, dp) {
    if (v == null || isNaN(v)) return '—';
    return (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(v), dp);
  }
  var F = {
    trillion: function (v) { return v == null ? '—' : '$' + num(v / 1000, 2) + 'T'; },
    billion0: function (v) { return v == null ? '—' : num(v, 0) + 'B'; },
    billion1: function (v) { return v == null ? '—' : num(v, 1) + 'B'; },
    bp: function (v) { return v == null ? '—' : sgn(v, 1) + 'bp'; },
    pct2: function (v) { return v == null ? '—' : num(v, 2) + '%p'; },
    spct2: function (v) { return v == null ? '—' : sgn(v, 2) + '%p'; },
    pctv: function (v) { return v == null ? '—' : num(v, 2) + '%'; },
    plain2: function (v) { return num(v, 2); },
    plain3: function (v) { return num(v, 3); },
    won: function (v) { return v == null ? '—' : num(v, 1) + '원'; },
    vix: function (v) { return num(v, 2); }
  };
  var D = {   /* Δ 배지용 — 부호 포함 축약 표기 */
    billion: function (v) { return sgn(v, 0) + 'B'; },
    billion1: function (v) { return sgn(v, 1) + 'B'; },
    bp: function (v) { return sgn(v, 1) + 'bp'; },
    pp: function (v) { return sgn(v, 2) + '%p'; },
    plain2: function (v) { return sgn(v, 2); },
    plain1: function (v) { return sgn(v, 1); }
  };

  /* ── 날짜/시계열 유틸 ──────────────────────────────────────────────── */
  function keysOf(s) { return s ? Object.keys(s).sort() : []; }
  function lastKey(s) { var k = keysOf(s); return k.length ? k[k.length - 1] : null; }
  function lastVal(s) { var k = lastKey(s); return k == null ? null : s[k]; }
  function shiftMonths(ds, m) {
    var p = ds.split('-'), y = +p[0], mo = +p[1] - 1, d = +p[2];
    var t = mo - m, ny = y + Math.floor(t / 12), nm = ((t % 12) + 12) % 12;
    var dim = new Date(Date.UTC(ny, nm + 1, 0)).getUTCDate();
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    return ny + '-' + pad(nm + 1) + '-' + pad(Math.min(d, dim));
  }
  function shiftDays(ds, n) {
    var p = ds.split('-');
    var t = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2] - n));
    var pad = function (x) { return (x < 10 ? '0' : '') + x; };
    return t.getUTCFullYear() + '-' + pad(t.getUTCMonth() + 1) + '-' + pad(t.getUTCDate());
  }
  /* days일 전(달력 기준, 그 이하 마지막 유효값) 대비 변화 */
  function calcDelta(series, days) {
    var ks = keysOf(series);
    if (ks.length < 2) return { abs: null, pct: null };
    var lk = ks[ks.length - 1], target = shiftDays(lk, days), base = null;
    for (var i = ks.length - 1; i >= 0; i--) { if (ks[i] <= target) { base = series[ks[i]]; break; } }
    if (base == null) return { abs: null, pct: null };
    var v = series[lk];
    return { abs: v - base, pct: base ? (v - base) / Math.abs(base) * 100 : null };
  }

  /* 여러 시리즈를 하나의 날짜축(ks)에 정렬 — 보조 시리즈는 ffill, 값이 없는 앞구간은 버린다. */
  function alignSeries(ks, sers) {
    var sk = sers.map(keysOf);
    var ptr = sers.map(function () { return 0; });
    var okKs = [], vs = sers.map(function () { return []; });
    for (var i = 0; i < ks.length; i++) {
      var row = [], ok = true;
      for (var j = 0; j < sers.length; j++) {
        var arr = sk[j], v = null;
        while (ptr[j] < arr.length && arr[ptr[j]] <= ks[i]) { v = sers[j][arr[ptr[j]]]; ptr[j]++; }
        if (v == null && ptr[j] > 0) v = sers[j][arr[ptr[j] - 1]];
        if (v == null || isNaN(v)) ok = false;
        row.push(v);
      }
      if (!ok) continue;
      okKs.push(ks[i]);
      for (var q = 0; q < sers.length; q++) vs[q].push(row[q]);
    }
    return { ks: okKs, vs: vs };
  }

  /* 두 시리즈의 차(같은 날짜만) — 스키마 추가 없이 렌더러에서 스프레드 시계열을 만든다. */
  function deriveSpread(a, b) {
    var out = {}, ks = keysOf(a);
    for (var i = 0; i < ks.length; i++) {
      var x = a[ks[i]], y = b[ks[i]];
      if (x == null || y == null || isNaN(x) || isNaN(y)) continue;
      out[ks[i]] = Math.round((x - y) * 1000) / 1000;
    }
    return out;
  }

  /* ── 차트 SVG ───────────────────────────────────────────────────────
     y도메인 = 넘겨받은 (윈도) 값들만의 min/max + 4% 패딩.                */
  var W = 600, H = 168, PL = 8, PR = 54, PT = 14, PB = 22;

  function chartSVG(ks, vsList, colors, refs, fmt, band) {
    var n = ks.length, flat = [];
    for (var q = 0; q < vsList.length; q++) flat = flat.concat(vsList[q]);
    /* domain=true 기준선만 y도메인에 포함한다. TGA 재무부 가정 참고선처럼 항상 보여야 하는 값에만 사용. */
    for (var rd = 0; rd < refs.length; rd++) {
      if (refs[rd].domain && refs[rd].v != null && !isNaN(refs[rd].v)) flat.push(Number(refs[rd].v));
    }
    if (n < 2 || !flat.length) return { svg: '<div class="liq2-empty">표시 구간 데이터 부족</div>', map: null };
    var mn = Math.min.apply(null, flat), mx = Math.max.apply(null, flat);
    var rg = mx - mn;
    var padv = rg > 0 ? rg * 0.04 : (Math.abs(mx) * 0.02 || 1);
    var lo = mn - padv, hi = mx + padv, span = (hi - lo) || 1;
    var pw = W - PL - PR, ph = H - PT - PB;
    var X = function (i) { return PL + pw * (n === 1 ? 0 : i / (n - 1)); };
    var Y = function (v) { return PT + ph * (1 - (v - lo) / span); };

    var s = [];
    /* 밴드 음영 — 도메인에 맞춰 클립(도메인 강제확장 없음), 완전히 벗어나면 생략 */
    if (band && band.lo != null && band.hi != null) {
      var bl = Math.max(Math.min(band.lo, band.hi), lo), bh = Math.min(Math.max(band.lo, band.hi), hi);
      if (bh > bl) {
        var byy = Y(bh);
        s.push('<rect x="' + PL + '" y="' + byy.toFixed(1) + '" width="' + (W - PL - PR) +
          '" height="' + (Y(bl) - byy).toFixed(1) + '" fill="' + (band.c || '#8a93a3') +
          '" opacity="' + (band.o || 0.12) + '"/>');
      }
    }
    /* 가로 그리드 4줄 + 우측 y라벨 */
    for (var g = 0; g < 4; g++) {
      var gv = lo + span * (g / 3), gy = Y(gv);
      s.push('<line class="liq2-grid" x1="' + PL + '" y1="' + gy.toFixed(1) +
        '" x2="' + (W - PR) + '" y2="' + gy.toFixed(1) + '"/>');
      s.push('<text class="liq2-ylab" x="' + (W - PR + 6) + '" y="' + (gy + 3.2).toFixed(1) + '">' +
        esc(fmt(gv)) + '</text>');
    }
    /* 기준선 — 윈도 도메인 밖이면 생략(도메인 강제확장 금지) */
    for (var r = 0; r < refs.length; r++) {
      var rf = refs[r];
      if (rf.v < lo || rf.v > hi) {
        /* 구간 밖 — 도메인을 늘리지 않는 대신, 어느 쪽에 있는지만 가장자리에 남긴다 */
        if (rf.edge && rf.label) {
          s.push('<text class="liq2-reflab" x="' + (PL + 3) + '" y="' +
            (rf.v < lo ? (H - PB - 4) : (PT + 9)) + '" fill="' + rf.c + '" opacity=".85">' +
            esc((rf.v < lo ? '↓ ' : '↑ ') + rf.label + ' (표시 구간 밖)') + '</text>');
        }
        continue;
      }
      var ry = Y(rf.v);
      s.push('<line x1="' + PL + '" y1="' + ry.toFixed(1) + '" x2="' + (W - PR) + '" y2="' + ry.toFixed(1) +
        '" stroke="' + rf.c + '" stroke-width="1"' +
        (rf.solid ? ' opacity=".75"' : ' stroke-dasharray="4 3" opacity=".7"') + '/>');
      if (rf.label) {
        s.push('<text class="liq2-reflab" x="' + (PL + 3) + '" y="' + (ry - 3.5).toFixed(1) +
          '" fill="' + rf.c + '">' + esc(rf.label) + '</text>');
      }
    }
    /* x라벨 4개 (YYYY-MM) */
    var xn = Math.min(4, n);
    for (var t = 0; t < xn; t++) {
      var idx = Math.round((n - 1) * t / (xn - 1 || 1));
      var tx = X(idx), anch = t === 0 ? 'start' : (t === xn - 1 ? 'end' : 'middle');
      s.push('<text class="liq2-xlab" x="' + tx.toFixed(1) + '" y="' + (H - 6) +
        '" text-anchor="' + anch + '">' + esc(ks[idx].slice(0, 7)) + '</text>');
    }
    /* 라인 (시리즈 수만큼) */
    var lx = X(n - 1), marks = [];
    for (var li = 0; li < vsList.length; li++) {
      var vv = vsList[li], cc = colors[li] || colors[0];
      var pts = [];
      for (var i = 0; i < n; i++) pts.push(X(i).toFixed(1) + ',' + Y(vv[i]).toFixed(1));
      s.push('<polyline points="' + pts.join(' ') + '" fill="none" stroke="' + cc +
        '" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>');
      marks.push({ c: cc, v: vv[n - 1], py: Y(vv[n - 1]) });
    }
    /* 마지막 점 + 값 라벨(2선이면 라벨끼리 겹치지 않게 밀어냄) */
    marks.sort(function (a, b) { return a.py - b.py; });
    var prevLab = -1e9;
    for (var m = 0; m < marks.length; m++) {
      var t0 = Math.max(PT + 9, Math.min(H - PB - 3, marks[m].py - 8));
      if (t0 - prevLab < 12) t0 = prevLab + 12;
      marks[m].ly = Math.min(H - PB - 1, t0);
      prevLab = marks[m].ly;
      s.push('<circle cx="' + lx.toFixed(1) + '" cy="' + marks[m].py.toFixed(1) +
        '" r="3.2" fill="' + marks[m].c + '"/>');
      s.push('<text class="liq2-last" x="' + (lx - 5).toFixed(1) + '" y="' + marks[m].ly.toFixed(1) +
        '" text-anchor="end" fill="' + marks[m].c + '">' + esc(fmt(marks[m].v)) + '</text>');
    }
    /* 호버 크로스헤어 — 시리즈마다 점 하나 */
    var hvd = '';
    for (var h = 0; h < vsList.length; h++) {
      hvd += '<circle r="3.6" fill="none" stroke="' + (colors[h] || colors[0]) + '" stroke-width="1.6"/>';
    }
    s.push('<g class="liq2-hv" style="display:none">' +
      '<line y1="' + PT + '" y2="' + (H - PB) + '" stroke="' + colors[0] + '" stroke-width="1" opacity=".45"/>' +
      hvd + '</g>');

    var svg = '<svg class="liq2-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img">' + s.join('') + '</svg>';
    return { svg: svg, map: { X: X, Y: Y, n: n } };
  }

  /* ── 카드 조립 ─────────────────────────────────────────────────────── */
  function deltaBadge(label, chg, pct, key, dfmt) {
    if (chg == null || isNaN(chg)) {
      return '<span class="liq2-dlt" style="color:' + NEUTRAL + '">' + label + ' —</span>';
    }
    var bad = BAD_DIR[key];
    var arrow = chg > 0 ? '↑' : (chg < 0 ? '↓' : '→');
    var col = NEUTRAL;
    if (bad && chg !== 0) col = ((chg > 0) === (bad === 'up')) ? UP : DOWN;
    var tip = (pct == null || isNaN(pct)) ? '' : ' (' + sgn(pct, 2) + '%)';
    return '<span class="liq2-dlt" style="color:' + col + ';background:' + col + '1f">' +
      label + ' ' + arrow + ' ' + esc(dfmt(chg)) + esc(tip) + '</span>';
  }

  function buildCard(spec, S, cutoff) {
    var wrap = document.createElement('div');
    wrap.className = 'liq2-chart';

    var keys = spec.key2 ? [spec.key, spec.key2] : [spec.key];
    var colors = spec.key2 ? [spec.color, spec.color2] : [spec.color];
    var sers = keys.map(function (k) { return (S || {})[k] || {}; });
    var series = sers[0];

    var ks = keysOf(series);
    var wks = cutoff ? ks.filter(function (k) { return k >= cutoff; }) : ks;
    if (wks.length < 2) wks = ks.slice(-2);
    var al = alignSeries(wks, sers);          /* 2선이면 보조 시리즈를 같은 날짜축에 정렬 */
    wks = al.ks;

    var cur = lastVal(series);
    var dlt = spec.deltas || {};
    var d1 = dlt.d1w != null ? { abs: dlt.d1w, pct: dlt.p1w } : calcDelta(series, 7);
    var d4 = dlt.d4w != null ? { abs: dlt.d4w, pct: dlt.p4w } : calcDelta(series, 28);
    var dfmt = spec.dfmt || D.plain2;

    var curs = '<b class="liq2-cur" style="color:' + spec.color + '">' + esc(spec.fmt(cur)) + '</b>';
    if (spec.key2) {
      curs += '<b class="liq2-cur2" style="color:' + spec.color2 + '">' +
        esc(spec.fmt(lastVal(sers[1]))) + '</b>';
    }
    var head = '<div class="liq2-ct">' +
      '<span class="liq2-name">' + esc(spec.title) + '</span>' + curs +
      deltaBadge('1주', d1.abs, spec.nopct ? null : d1.pct, spec.key, dfmt) +
      deltaBadge('4주', d4.abs, spec.nopct ? null : d4.pct, spec.key, dfmt) +
      '</div>' +
      (spec.legend ? '<div class="liq2-clg">' + spec.legend.map(function (lg) {
        return '<span><i style="background:' + lg[1] + '"></i>' + esc(lg[0]) + '</span>';
      }).join('') + '</div>' : '') +
      (spec.sub ? '<div class="liq2-csub">' + esc(spec.sub) + '</div>' : '');

    spec.colors = colors;
    var built = chartSVG(wks, al.vs, colors, spec.refs || [], spec.fmt, spec.band);
    wrap.innerHTML = head + '<div class="liq2-plot">' + built.svg +
      '<div class="liq2-tip" style="display:none"></div></div>';

    if (built.map) attachHover(wrap, wks, al.vs, built.map, spec);
    return wrap;
  }

  function attachHover(wrap, ks, vsList, map, spec) {
    var svg = wrap.querySelector('svg.liq2-svg');
    var tip = wrap.querySelector('.liq2-tip');
    var hv = wrap.querySelector('.liq2-hv');
    if (!svg || !tip || !hv) return;
    var line = hv.getElementsByTagName('line')[0];
    var dots = hv.getElementsByTagName('circle');
    var cols = spec.colors || [spec.color];
    var plot = wrap.querySelector('.liq2-plot');

    svg.addEventListener('mousemove', function (e) {
      var r = svg.getBoundingClientRect();
      if (!r.width) return;
      var vx = (e.clientX - r.left) / r.width * W;
      var i = Math.round((vx - PL) / (W - PL - PR) * (map.n - 1));
      if (i < 0) i = 0; if (i > map.n - 1) i = map.n - 1;
      var px = map.X(i), py = map.Y(vsList[0][i]);
      line.setAttribute('x1', px.toFixed(1)); line.setAttribute('x2', px.toFixed(1));
      var rows = '';
      for (var j = 0; j < vsList.length; j++) {
        if (dots[j]) {
          dots[j].setAttribute('cx', px.toFixed(1));
          dots[j].setAttribute('cy', map.Y(vsList[j][i]).toFixed(1));
        }
        var lbl = (spec.legend && spec.legend[j]) ? spec.legend[j][0] + ' ' : '';
        rows += '<b style="color:' + (cols[j] || cols[0]) + '">' + esc(lbl + spec.fmt(vsList[j][i])) + '</b>';
      }
      hv.style.display = '';
      tip.innerHTML = '<span class="liq2-tipd">' + esc(ks[i]) + '</span>' + rows;
      tip.style.display = '';
      var pr = plot.getBoundingClientRect();
      var left = px / W * pr.width;
      tip.style.left = Math.max(2, Math.min(pr.width - tip.offsetWidth - 2, left - tip.offsetWidth / 2)) + 'px';
      tip.style.top = Math.max(0, py / H * pr.height - tip.offsetHeight - 8) + 'px';
    });
    svg.addEventListener('mouseleave', function () {
      hv.style.display = 'none';
      tip.style.display = 'none';
    });
  }

  /* ── 차트 정의 ─────────────────────────────────────────────────────── */
  function tgaTargetOf(d) {
    var fund = ((d.sections || {}).funding || {});
    var t = ((fund.references || {}).treasury_cash_balance_assumption) || d.tga_target;
    var api = typeof window !== 'undefined' ? window.PanoptesTgaTarget : null;
    return api ? api.validateTarget(t) : null;
  }
  function fundingSpecs(d, S) {
    var ref0 = { v: 0, c: '#8a93a3', solid: true, label: '0' };
    var ref5 = { v: 5, c: '#ff8a3d', label: '+5bp' };
    var ref10 = { v: 10, c: '#ff4d5e', label: '+10bp' };
    var target = tgaTargetOf(d);
    var tgaRefs = [{ v: 900, c: '#ff8a3d', edge: true, label: '내부 경계 900B' }];
    var tgaSub = '주황 점선 = Panoptes 내부 경계 900B';
    if (target) {
      var display = window.PanoptesTgaTarget.displayModel(target);
      tgaRefs.unshift({ v: Number(target.value), c: '#c6cfda', edge: true, domain: true,
        label: display.lineLabel });
      tgaSub = '회색 점선 = ' + display.legendLabel + ' · ' + tgaSub;
    } else {
      tgaSub = '미 재무부 목표 데이터 없음 · ' + tgaSub;
    }
    return [
      { key: 'NETLIQ', title: 'Net Liquidity (WALCL−TGA−RRP)', color: '#2bc0d4', fmt: F.trillion, dfmt: D.billion },
      { key: 'TGA', title: 'TGA (재무부 현금)', color: '#ff8a3d', fmt: F.billion0, dfmt: D.billion,
        refs: tgaRefs, sub: tgaSub },
      { key: 'RRP', title: 'RRP (역레포 잔고)', color: '#ffd23d', fmt: F.billion1, dfmt: D.billion1 },
      { key: 'RESERVES', title: '지급준비금 (WRESBAL)', color: '#59d0a8', fmt: F.trillion, dfmt: D.billion },
      { key: 'SOFR_IORB_BP', title: 'SOFR − IORB', color: '#ff4d5e', fmt: F.bp, dfmt: D.bp,
        refs: [ref0, ref5, ref10], sub: '레포 스트레스 — 0 위로 벌어지면 담보자금 조달비용 상승' },
      { key: 'EFFR_IORB_BP', title: 'EFFR − IORB', color: '#4ea1ff', fmt: F.bp, dfmt: D.bp,
        refs: [ref0, ref5, ref10], sub: '은행 시스템 — IORB 위로 붙으면 reserve 부족 신호' }
    ];
  }
  function creditSpecs(d, S) {
    var L = ((d.sections || {}).credit || {}).latest || {};
    var g = function (k) { return (L[k] || {}).value != null ? (L[k] || {}).value : lastVal(S[k]); };
    return [
      { key: 'HY_OAS', title: 'HY OAS (하이일드 스프레드)', color: '#ff6b6b', fmt: F.pct2, dfmt: D.pp,
        refs: [{ v: 4.5, c: '#ff8a3d', label: '4.5' }, { v: 5.5, c: '#ff4d5e', label: '5.5' }] },
      { key: 'IG_OAS', title: 'IG OAS (투자등급 스프레드)', color: '#ffab3d', fmt: F.pct2, dfmt: D.pp },
      { key: 'T10Y2Y', title: '10Y − 2Y 커브', color: '#b48cff', fmt: F.spct2, dfmt: D.pp,
        refs: [{ v: 0, c: '#8a93a3', solid: true, label: '0 (역전 경계)' }],
        sub: 'DGS10 ' + F.pct2(g('DGS10')) + ' · DGS2 ' + F.pct2(g('DGS2')) },
      { key: 'NFCI', title: 'NFCI (시카고 연준 금융환경지수)', color: '#8a93a3', fmt: F.plain3, dfmt: D.plain2,
        sub: '양수 = 평균보다 타이트한 금융환경' }
    ];
  }
  function fxvolSpecs(d, S) {
    var L = ((d.sections || {}).fxvol || {}).latest || {};
    var g = function (k) { return (L[k] || {}).value != null ? (L[k] || {}).value : lastVal(S[k]); };
    return [
      { key: 'DXY', title: '달러지수 (광의, DTWEXBGS)', color: '#4dd0e1', fmt: F.plain2, dfmt: D.plain2 },
      { key: 'USDKRW', title: '원/달러', color: '#ff7ab8', fmt: F.won, dfmt: D.plain1 },
      { key: 'USDJPY', title: '엔/달러', color: '#ffd23d', fmt: F.plain2, dfmt: D.plain2 },
      { key: 'VIX', title: 'VIX', color: '#ff4d5e', fmt: F.vix, dfmt: D.plain2,
        refs: [{ v: 20, c: '#ff8a3d', label: '20' }, { v: 30, c: '#ff4d5e', label: '30' }],
        sub: '기대인플레 BEI10 ' + F.pct2(g('BEI10')) + ' · 실질금리 REAL10 ' + F.pct2(g('REAL10')) }
    ];
  }

  var INFL_BLUE = '#4ea1ff', INFL_YEL = '#ffd23d', INFL_SPD = '#b48cff';
  var ANCHOR_BADGE = {
    green: '앵커 견고', yellow: '앵커 유지', orange: '앵커 이완 조짐', red: '앵커 이완', gray: '판정 보류'
  };

  /* inflation 섹션의 값 접근 — computed → latest → 시계열 마지막값 순으로 폴백 */
  function inflVals(d, S) {
    var sec = ((d.sections || {}).inflation) || {};
    var C = sec.computed || {}, L = sec.latest || {};
    var g = function (key, ck) {
      if (C[ck] != null) return C[ck];
      if ((L[key] || {}).value != null) return L[key].value;
      return lastVal((S || {})[key] || {});
    };
    var v = {
      bei10: g('BEI10', 'bei10'), bei5: g('BEI5', 'bei5'), fwd: g('FWD5Y5Y', 'fwd5y5y'),
      real10: g('REAL10', 'real10'), real5: g('REAL5', 'real5'),
      target: C.anchor_target != null ? C.anchor_target : 2.00,
      band: (C.anchor_band && C.anchor_band.length === 2) ? C.anchor_band : [1.85, 2.15],
      light: (d.lights || {}).infl_anchor || C.light || 'gray'
    };
    var idc = C.identity_check || {};
    v.spread = C.spread != null ? C.spread
      : (v.bei10 != null && v.fwd != null ? Math.round((v.bei10 - v.fwd) * 100) / 100 : null);
    v.impFwd = idc.implied_fwd != null ? idc.implied_fwd
      : (v.bei10 != null && v.bei5 != null ? 2 * v.bei10 - v.bei5 : null);
    v.impBei10 = idc.implied_bei10 != null ? idc.implied_bei10
      : (v.bei5 != null && v.fwd != null ? (v.bei5 + v.fwd) / 2 : null);
    v.gapBp = idc.gap_bp != null ? idc.gap_bp
      : (v.impFwd != null && v.fwd != null ? (v.fwd - v.impFwd) * 100 : null);
    v.anchorGap = C.anchor_gap != null ? C.anchor_gap
      : (v.fwd != null ? Math.round((v.fwd - v.target) * 100) / 100 : null);
    var dl = d.deltas || {}, C4 = C.d4w || {};
    var d4 = function (k) {
      if (C4[k] != null) return C4[k];
      if ((dl[k] || {}).d4w != null) return dl[k].d4w;
      return calcDelta((S || {})[k] || {}, 28).abs;
    };
    v.bei10_4w = d4('BEI10');
    v.fwd_4w = d4('FWD5Y5Y');
    return v;
  }

  function inflationSpecs(d, S) {
    var v = inflVals(d, S);
    return [
      { key: 'BEI10', key2: 'FWD5Y5Y', title: '기대 인플레 — 10Y BEI vs 5Y5Y',
        color: INFL_BLUE, color2: INFL_YEL, fmt: F.pctv, dfmt: D.pp,
        band: { lo: v.band[0], hi: v.band[1], c: '#8a93a3', o: 0.13 },
        refs: [{ v: v.target, c: '#8a93a3', solid: true, edge: true,
                 label: num(v.target, 2) + '% 목표' }],
        legend: [['10Y BEI', INFL_BLUE], ['5Y5Y Forward', INFL_YEL]],
        sub: '회색 실선 = ' + num(v.target, 2) + '% 목표 · 음영 = 앵커밴드 ' +
          num(v.band[0], 2) + '~' + num(v.band[1], 2) + '% · Δ배지는 10Y BEI 기준' },
      { key: 'BEI_SPREAD', title: '중단기 vs 중장기 갭 (10Y BEI − 5Y5Y)',
        color: INFL_SPD, fmt: F.spct2, dfmt: D.pp, nopct: true,   /* 0 근처 기준값 — % 변화는 무의미 */
        refs: [{ v: 0, c: '#8a93a3', label: '0' }],
        sub: '＋ = 중단기 기대가 장기보다 높음(유가·뉴스가 끌어올리는 쪽) / − = 끌어내리는 쪽' }
    ];
  }

  /* 해석 블록 — 정의·프리미엄 구성 → 스윙은 중단기 → 5Y5Y 앵커 게이지 → 항등식 괴리 */
  function inflationNote(d, S) {
    var v = inflVals(d, S);
    var col = LC[v.light] || LC.gray;
    var badge = ANCHOR_BADGE[v.light] || ANCHOR_BADGE.gray;
    var swing = v.spread == null ? '판정 보류'
      : (v.spread > 0.02 ? '지금은 <b style="color:' + UP + '">중단기가 올리는 쪽</b>'
        : (v.spread < -0.02 ? '지금은 <b style="color:' + DOWN + '">중단기가 내리는 쪽</b>'
          : '지금은 중단기·중장기가 거의 같은 자리'));
    var st = function (lbl, val, sub, c) {
      return '<div class="liq2-nst"><div class="liq2-nsl">' + esc(lbl) + '</div>' +
        '<div class="liq2-nsv"' + (c ? ' style="color:' + c + '"' : '') + '>' + esc(val) + '</div>' +
        '<div class="liq2-nss">' + esc(sub || '') + '</div></div>';
    };
    var stats =
      st('10Y BEI', F.pctv(v.bei10), '4주 ' + sgn(v.bei10_4w, 2) + '%p', INFL_BLUE) +
      st('5Y BEI', F.pctv(v.bei5), '중단기 기대') +
      st('5Y5Y Forward', F.pctv(v.fwd), '4주 ' + sgn(v.fwd_4w, 2) + '%p', INFL_YEL) +
      st('갭 (10Y BEI − 5Y5Y)', sgn(v.spread, 2) + '%p', '중단기 − 중장기', INFL_SPD) +
      st(num(v.target, 2) + '% 목표 대비', sgn(v.anchorGap, 2) + '%p', badge, col) +
      st('항등식 괴리', sgn(v.gapBp, 1) + 'bp', '2×BEI10−BEI5 vs 실제') +
      st('실질금리 (TIPS)', F.pctv(v.real10), '5Y ' + F.pctv(v.real5));

    var li = [];
    li.push('<b>정의</b> <code>10Y BEI = 10Y 금리 − 10Y TIPS</code> — 즉 ' +
      '<code>≈ 기대 인플레 + 인플레 리스크 프리미엄 + 유동성 프리미엄</code>. 순수한 기대치가 아니라 ' +
      '프리미엄이 섞인 <b>proxy</b>임. 현재 ' + esc(F.pctv(v.bei10)) + ', 4주 ' +
      esc(sgn(v.bei10_4w, 2)) + '%p.');
    li.push('<b>스윙은 중단기에서</b> — 모델 후반부(5Y5Y)는 2% 안팎으로 고정되는 성질이라 10Y BEI의 ' +
      '움직임은 대부분 중단기 기대에서 나옴. 그래서 유가·매크로 서프라이즈·뉴스 플로우에 민감함. ' +
      '현재 갭 <b>' + esc(sgn(v.spread, 2)) + '%p</b> → ' + swing + '.');
    li.push('<b>5Y5Y = 2% 목표 신뢰도 게이지</b> — 중장기 구간만 뽑아낸 proxy라 중앙은행 신뢰도를 본다. ' +
      '현재 ' + esc(F.pctv(v.fwd)) + ' (목표 대비 ' + esc(sgn(v.anchorGap, 2)) + '%p, 4주 ' +
      esc(sgn(v.fwd_4w, 2)) + '%p) → <span class="liq2-badge" style="background:' + col +
      '22;color:' + col + '">' + esc(badge) + '</span> · 판정 기준 |5Y5Y−2.00| ≤0.15 / ≤0.30 / ≤0.50.');
    var gapTxt = v.gapBp == null ? '괴리는 산출 보류.'
      : (Math.abs(v.gapBp) < 0.5
        ? '지금은 괴리가 사실상 0 — 두 프록시가 같은 얘기를 하는 중. 이게 벌어질수록 프리미엄 차이가 커졌다는 뜻임.'
        : '괴리가 0으로 딱 떨어지지 않는 것 자체가 <b>둘 다 프리미엄이 낀 proxy</b>라는 증거임.');
    li.push('<b>항등식</b> <code>10Y BEI ≈ (5Y BEI + 5Y5Y)/2</code>, ' +
      '<code>5Y5Y ≈ 2×10Y BEI − 5Y BEI</code> — 계산값 ' + esc(num(v.impFwd, 2)) + '% vs 실제 ' +
      esc(F.pctv(v.fwd)) + ', 괴리 <b>' + esc(sgn(v.gapBp, 1)) + 'bp</b>' +
      '(10Y BEI 쪽으로는 계산값 ' + esc(num(v.impBei10, 2)) + '%). ' + gapTxt);

    return '<div class="liq2-note"><div class="liq2-nh">기대 인플레이션 읽는 법' +
      '<span class="liq2-badge" style="background:' + col + '22;color:' + col + '">5Y5Y ' +
      esc(badge) + ' · ' + esc(LL[v.light] || '—') + '</span></div>' +
      '<div class="liq2-nsts">' + stats + '</div>' +
      '<ul class="liq2-nl"><li>' + li.join('</li><li>') + '</li></ul></div>';
  }

  /* ── 신호등 카드 (현행 5 + hy/curve/vix/dxy4w = 9, +infl_anchor) ────── */
  function lightCards(d) {
    var lights = d.lights || {};
    var fund = (d.sections || {}).funding || {};
    var C = fund.computed || {};
    var FL = fund.latest || {};
    var CL = ((d.sections || {}).credit || {}).latest || {};
    var XL = ((d.sections || {}).fxvol || {}).latest || {};
    var dl = d.deltas || {};
    var v = function (o, k) { return ((o || {})[k] || {}).value; };
    var items = [
      ['repo', '레포 (SOFR−IORB)', F.bp(C.sofr_iorb_bp),
        (C.sofr_iorb_bp != null && C.sofr_iorb_bp > 0) ? 'IORB 위 = 스트레스' : 'IORB 아래 = 안정'],
      ['bank', '은행 (EFFR−IORB)', F.bp(C.effr_iorb_bp),
        (C.effr_iorb_bp != null && C.effr_iorb_bp < 0) ? 'IORB 아래 = 정상' : '경계'],
      ['tga', 'TGA 흡수압력', F.billion0(v(FL, 'TGA')),
        lights.tga === 'green' ? '내부 기준 900B 미만' : '내부 경계 초과·재축적 압력'],
      ['rrp', 'RRP 완충재', F.billion1(v(FL, 'RRP')),
        (v(FL, 'RRP') != null && v(FL, 'RRP') < 20) ? '사실상 고갈' : '남아있음'],
      ['netliq', 'Net Liq 방향', F.trillion(C.net_liquidity),
        sgn(C.net_liquidity_chg_1w, 0) + 'B / 1주'],
      ['hy', 'HY OAS (크레딧)', F.pct2(v(CL, 'HY_OAS')),
        sgn((dl.HY_OAS || {}).d4w, 2) + '%p / 4주'],
      ['curve', '10Y−2Y 커브', F.spct2(v(CL, 'T10Y2Y')),
        (v(CL, 'T10Y2Y') != null && v(CL, 'T10Y2Y') < 0) ? '역전 상태' : '정상 기울기'],
      ['vix', 'VIX (변동성)', F.vix(v(XL, 'VIX')), 'S&P 내재변동성'],
      ['dxy4w', '달러 4주 변화', sgn((dl.DXY || {}).p4w, 2) + '%',
        'DXY ' + F.plain2(v(XL, 'DXY')) + ' — 급등=글로벌 긴축']
    ];
    if (lights.infl_anchor) {
      var IC = ((d.sections || {}).inflation || {}).computed || {};
      var IL = ((d.sections || {}).inflation || {}).latest || {};
      var fwdv = IC.fwd5y5y != null ? IC.fwd5y5y : v(IL, 'FWD5Y5Y');
      var agap = IC.anchor_gap != null ? IC.anchor_gap : (fwdv != null ? fwdv - 2 : null);
      items.push(['infl_anchor', '기대인플레 앵커 (5Y5Y)', F.pctv(fwdv),
        '2.00% 목표 대비 ' + sgn(agap, 2) + '%p']);
    }
    return items.map(function (it) {
      var col = LC[lights[it[0]]] || LC.gray;
      return '<div class="liq2-lcard" style="border-top:3px solid ' + col + '">' +
        '<div class="liq2-lt">' + esc(it[1]) + '<span class="liq2-dot" style="background:' + col + '"></span></div>' +
        '<div class="liq2-lv">' + esc(it[2]) + '</div>' +
        '<div class="liq2-ls">' + esc(it[3]) + '</div></div>';
    }).join('');
  }

  /* ── CSS (1회 주입) ────────────────────────────────────────────────── */
  var CSS = [
    '.liq2{--liq2-mono:var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace);',
    '--liq2-panel:var(--panel,#12161c);--liq2-line:var(--line,#232a33);--liq2-dim:var(--dim,#8a93a3)}',
    '.liq2-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:6px}',
    '.liq2-head h2{font-size:20px;font-weight:800;margin:0}',
    '.liq2-ov{font-size:12px;font-weight:700;padding:4px 12px;border-radius:999px}',
    '.liq2-chips{display:flex;gap:4px;margin-left:auto;background:var(--liq2-panel);',
    'border:1px solid var(--liq2-line);border-radius:999px;padding:3px}',
    '.liq2-chip{font-family:var(--liq2-mono);font-size:11px;font-weight:700;padding:4px 11px;',
    'border-radius:999px;border:0;background:transparent;color:var(--liq2-dim);cursor:pointer;line-height:1}',
    '.liq2-chip[aria-pressed="true"]{background:#2bc0d422;color:#2bc0d4}',
    '.liq2-sub{color:var(--liq2-dim);font-size:12.5px;margin:0 0 18px}',
    '.liq2-lights{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px}',
    '.liq2-lcard{background:var(--liq2-panel);border:1px solid var(--liq2-line);border-radius:12px;',
    'padding:12px 15px;min-width:148px;flex:1 1 148px}',
    '.liq2-lt{font-size:11px;color:var(--liq2-dim);font-weight:600;display:flex;align-items:center;gap:6px}',
    '.liq2-dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-left:auto}',
    '.liq2-lv{font-family:var(--liq2-mono);font-size:20px;font-weight:750;margin-top:4px}',
    '.liq2-ls{font-family:var(--liq2-mono);font-size:10.5px;color:var(--liq2-dim);margin-top:2px}',
    '.liq2-sec{font-size:13px;font-weight:750;margin:0 0 10px;display:flex;align-items:baseline;gap:8px}',
    '.liq2-sec span{font-family:var(--liq2-mono);font-size:10.5px;color:var(--liq2-dim);font-weight:500}',
    '.liq2-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px;margin-bottom:24px}',
    '.liq2-chart{background:var(--liq2-panel);border:1px solid var(--liq2-line);border-radius:12px;padding:13px 15px 8px}',
    '.liq2-ct{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap;font-size:12.5px;font-weight:650}',
    '.liq2-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}',
    '.liq2-cur{font-family:var(--liq2-mono);font-size:14.5px;font-weight:800;margin-left:auto}',
    '.liq2-cur2{font-family:var(--liq2-mono);font-size:14.5px;font-weight:800}',
    '.liq2-clg{display:flex;gap:11px;flex-wrap:wrap;font-family:var(--liq2-mono);font-size:10px;',
    'color:var(--liq2-dim);margin-top:4px}',
    '.liq2-clg i{width:8px;height:8px;border-radius:2px;display:inline-block;margin-right:4px}',
    '.liq2-dlt{font-family:var(--liq2-mono);font-size:10px;font-weight:700;padding:2px 6px;border-radius:5px;white-space:nowrap}',
    '.liq2-csub{font-size:10.5px;color:var(--liq2-dim);margin-top:3px;font-family:var(--liq2-mono)}',
    '.liq2-plot{position:relative;margin-top:6px}',
    '.liq2-svg{width:100%;height:auto;display:block;overflow:visible}',
    '.liq2-svg text{font-family:var(--liq2-mono);font-size:10px;fill:var(--liq2-dim)}',
    '.liq2-svg .liq2-reflab{font-size:9px;font-weight:700}',
    '.liq2-svg .liq2-last{font-size:10.5px;font-weight:800}',
    '.liq2-grid-line,.liq2-svg .liq2-grid{stroke:var(--liq2-line);stroke-width:1;opacity:.55}',
    '.liq2-empty{font-size:11.5px;color:var(--liq2-dim);padding:56px 0;text-align:center}',
    '.liq2-tip{position:absolute;pointer-events:none;background:#0b0e13ee;border:1px solid var(--liq2-line);',
    'border-radius:7px;padding:4px 8px;font-family:var(--liq2-mono);font-size:10.5px;white-space:nowrap;z-index:3}',
    '.liq2-tip .liq2-tipd{color:var(--liq2-dim);margin-right:6px}',
    '.liq2-tip b+b{margin-left:8px}',
    '.liq2-note{background:var(--liq2-panel);border:1px solid var(--liq2-line);border-radius:14px;',
    'padding:16px 18px;margin:-8px 0 24px}',
    '.liq2-nh{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12.5px;',
    'font-weight:750;margin-bottom:12px}',
    '.liq2-badge{font-family:var(--liq2-mono);font-size:10.5px;font-weight:700;padding:3px 9px;border-radius:999px}',
    '.liq2-nsts{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:8px;margin-bottom:13px}',
    '.liq2-nst{border:1px solid var(--liq2-line);border-radius:9px;padding:8px 10px}',
    '.liq2-nsl{font-size:10px;color:var(--liq2-dim);font-weight:600}',
    '.liq2-nsv{font-family:var(--liq2-mono);font-size:15px;font-weight:800;margin-top:2px}',
    '.liq2-nss{font-family:var(--liq2-mono);font-size:9.5px;color:var(--liq2-dim);margin-top:1px}',
    '.liq2-nl{margin:0;padding-left:17px;font-size:12.5px;line-height:1.8}',
    '.liq2-nl li{margin-bottom:7px}',
    '.liq2-nl li:last-child{margin-bottom:0}',
    '.liq2-nl code{font-family:var(--liq2-mono);font-size:11.5px;background:#ffffff12;',
    'border:1px solid var(--liq2-line);border-radius:5px;padding:1px 5px}',
    '.liq2-comment{background:var(--liq2-panel);border:1px solid var(--liq2-line);border-radius:14px;',
    'padding:20px 24px;max-width:920px}',
    '.liq2-comment pre{font-family:var(--sans,inherit);font-size:13.5px;line-height:1.85;white-space:pre-wrap;margin:0}',
    '.liq2-cmeta{font-family:var(--liq2-mono);font-size:11px;color:var(--liq2-dim);margin-top:14px;',
    'border-top:1px solid var(--liq2-line);padding-top:10px}'
  ].join('');

  function injectCss() {
    if (typeof document === 'undefined') return;
    if (document.getElementById('liq2Css')) return;
    var st = document.createElement('style');
    st.id = 'liq2Css';
    st.textContent = CSS;
    (document.head || document.documentElement).appendChild(st);
  }

  /* ── 렌더 ───────────────────────────────────────────────────────────── */
  function renderLiq2(el, data) {
    if (!el) return;
    injectCss();
    var d = data || {};
    var sec = d.sections || {};
    var S = {};
    ['funding', 'credit', 'fxvol', 'inflation'].forEach(function (k) {
      var ss = (sec[k] || {}).series || {};
      Object.keys(ss).forEach(function (n) { S[n] = ss[n] || {}; });
    });

    /* 중단기 vs 중장기 갭 — 렌더러에서 파생(JSON 스키마 불변) */
    var hasInfl = !!(S.BEI10 && S.FWD5Y5Y && keysOf(S.BEI10).length && keysOf(S.FWD5Y5Y).length);
    if (hasInfl) S.BEI_SPREAD = deriveSpread(S.BEI10, S.FWD5Y5Y);

    var ov = d.overall || 'gray';
    var ovc = LC[ov] || LC.gray;
    var state = { range: DEFAULT_RANGE };

    /* 전 차트 공통 기준일 — 가장 최근 관측일 */
    var anchor = d.updated || null;
    Object.keys(S).forEach(function (n) {
      var lk = lastKey(S[n]);
      if (lk && (!anchor || lk > anchor)) anchor = lk;
    });

    el.className = (el.className || '').indexOf('liq2') >= 0 ? el.className : ((el.className || '') + ' liq2').trim();
    el.innerHTML =
      '<div class="liq2-head"><h2>💧 유동성 대시보드</h2>' +
      '<span class="liq2-ov" style="background:' + ovc + '22;color:' + ovc + '">종합 ' + esc(LL[ov] || '—') + '</span>' +
      '<div class="liq2-chips" role="group" aria-label="기간">' +
      RANGES.map(function (r) {
        return '<button type="button" class="liq2-chip" data-r="' + r[0] + '" aria-pressed="' +
          (r[0] === state.range) + '">' + r[0] + '</button>';
      }).join('') + '</div></div>' +
      '<p class="liq2-sub">Net Liquidity = 연준 총자산 − TGA − RRP · FRED 실시간 · ' +
      'y축은 선택 기간 데이터 기준(TGA는 재무부 참고선 포함) · 업데이트 ' + esc(d.updated || '—') + '</p>' +
      '<div class="liq2-lights">' + lightCards(d) + '</div>' +
      '<div class="liq2-sec">① 단기자금 <span>NetLiq · TGA · RRP · 지급준비금 · IORB 대비 스프레드(bp)</span></div>' +
      '<div class="liq2-grid" data-g="funding"></div>' +
      '<div class="liq2-sec">② 크레딧 · 커브 <span>HY/IG OAS · 장단기 금리차 · 금융환경지수</span></div>' +
      '<div class="liq2-grid" data-g="credit"></div>' +
      '<div class="liq2-sec">③ 환율 · 변동성 <span>달러지수 · 원달러 · 엔달러 · VIX</span></div>' +
      '<div class="liq2-grid" data-g="fxvol"></div>' +
      (hasInfl ? '<div class="liq2-sec">④ 기대 인플레이션 <span>10Y BEI(명목−TIPS) · 5Y5Y Forward · ' +
        '중단기 vs 중장기 갭 — 모두 프리미엄이 섞인 proxy</span></div>' +
        '<div class="liq2-grid" data-g="inflation"></div>' + inflationNote(d, S) : '') +
      '<div class="liq2-comment"><pre>' + esc(d.commentary || '') + '</pre>' +
      '<div class="liq2-cmeta">자동 생성 해석 — 실시간 FRED 수치 기반. 투자 조언 아님. ' +
      '#NetLiquidity #TGA #RRP #SOFR #IORB #HYOAS #T10Y2Y #DXY #VIX #BEI #5Y5Y</div></div>';

    var groups = {
      funding: { el: el.querySelector('[data-g="funding"]'), specs: fundingSpecs(d, S) },
      credit: { el: el.querySelector('[data-g="credit"]'), specs: creditSpecs(d, S) },
      fxvol: { el: el.querySelector('[data-g="fxvol"]'), specs: fxvolSpecs(d, S) }
    };
    if (hasInfl) {
      groups.inflation = { el: el.querySelector('[data-g="inflation"]'), specs: inflationSpecs(d, S) };
    }

    function draw() {
      var months = 6;
      for (var i = 0; i < RANGES.length; i++) if (RANGES[i][0] === state.range) months = RANGES[i][1];
      var cutoff = (months && anchor) ? shiftMonths(anchor, months) : null;
      Object.keys(groups).forEach(function (gk) {
        var g = groups[gk];
        if (!g.el) return;
        g.el.innerHTML = '';
        g.specs.forEach(function (sp) {
          sp.deltas = (d.deltas || {})[sp.key] || {};
          g.el.appendChild(buildCard(sp, S, cutoff));
        });
      });
    }

    var chips = el.querySelectorAll('.liq2-chip');
    for (var c = 0; c < chips.length; c++) {
      chips[c].addEventListener('click', function (e) {
        state.range = e.currentTarget.getAttribute('data-r');
        for (var j = 0; j < chips.length; j++) {
          chips[j].setAttribute('aria-pressed', String(chips[j].getAttribute('data-r') === state.range));
        }
        draw();
      });
    }
    draw();
  }

  if (typeof window !== 'undefined') window.renderLiq2 = renderLiq2;
  if (typeof module !== 'undefined' && module.exports) module.exports = {
    renderLiq2: renderLiq2,
    _test: { chartSVG: chartSVG, fundingSpecs: fundingSpecs, tgaTargetOf: tgaTargetOf }
  };
})();
