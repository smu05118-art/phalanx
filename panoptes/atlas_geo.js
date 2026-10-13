/* ATLAS Geo is a dated research archive, deliberately separate from live Panoptes events. */
(function () {
  'use strict';

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>'"]/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[ch];
    });
  }
  function list(items) {
    return '<ul>' + (Array.isArray(items) ? items : []).map(function (item) { return '<li>' + esc(item) + '</li>'; }).join('') + '</ul>';
  }
  function installStyles() {
    if (document.getElementById('atlas-geo-style')) return;
    var style = document.createElement('style');
    style.id = 'atlas-geo-style';
    style.textContent = '' +
      '.atlas-geo{max-width:1180px;margin:0 auto;color:var(--ink)}' +
      '.atlas-geo-head{display:flex;gap:14px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;margin-bottom:18px}' +
      '.atlas-geo h2{font-size:22px;margin:0 0 5px}.atlas-geo p{line-height:1.65}' +
      '.atlas-geo-status{border:1px solid rgba(255,138,61,.55);background:rgba(255,138,61,.1);color:#ffd5ba;border-radius:999px;padding:6px 11px;font:600 11px var(--mono);white-space:nowrap}' +
      '.atlas-geo-note{border-left:3px solid #ff8a3d;background:var(--panel);padding:12px 14px;border-radius:0 9px 9px 0;color:#cdd6de;margin:0 0 16px}' +
      '.atlas-geo-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px}' +
      '.atlas-geo-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0}' +
      '.atlas-geo-card h3{font-size:15px;margin:0 0 5px}.atlas-geo-meta{font:11px var(--mono);color:var(--dim);margin-bottom:12px}' +
      '.atlas-geo-card h4{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--dim);margin:13px 0 5px}' +
      '.atlas-geo-card ul{padding-left:18px;color:#cdd6de;font-size:12px;line-height:1.55}.atlas-geo-card li+li{margin-top:4px}' +
      '.atlas-geo-sources{font:10px var(--mono);color:var(--accent);line-height:1.55;overflow-wrap:anywhere}' +
      '.atlas-geo-foot{font-size:12px;color:var(--dim);border-top:1px solid var(--line);padding-top:13px;margin-top:18px}' +
      '@media(max-width:700px){.atlas-geo h2{font-size:19px}.atlas-geo-grid{grid-template-columns:1fr}}';
    document.head.appendChild(style);
  }
  function render(root, data) {
    var cards = (data.theaters || []).map(function (theater) {
      return '<article class="atlas-geo-card">' +
        '<h3>' + esc(theater.title) + '</h3>' +
        '<p class="atlas-geo-meta">기준일 ' + esc(theater.as_of) + ' · ' + esc(theater.freshness) + '</p>' +
        '<p>' + esc(theater.headline) + '</p>' +
        '<h4>확인된 당시 기록</h4>' + list(theater.confirmed) +
        '<h4>현재값으로 쓰지 않는 미해결 항목</h4>' + list(theater.unresolved) +
        '<h4>원본 출처 ID</h4><p class="atlas-geo-sources">' + esc((theater.source_ids || []).join(' · ')) + '</p>' +
      '</article>';
    }).join('');
    root.innerHTML = '<section class="atlas-geo" aria-live="polite">' +
      '<div class="atlas-geo-head"><div><h2>🗃 ATLAS Geo 아카이브</h2><p class="hint">ATLAS의 검토 완료 스냅샷을 Panoptes 안에서 기준일과 함께 보존합니다.</p></div>' +
      '<span class="atlas-geo-status">STALE ARCHIVE · ' + esc(data.source_site && data.source_site.data_window) + '</span></div>' +
      '<p class="atlas-geo-note">' + esc(data.notice) + '</p>' +
      '<div class="atlas-geo-grid">' + cards + '</div>' +
      '<p class="atlas-geo-foot">' + esc(data.panoptes_boundary) + '</p></section>';
  }
  async function mount(root) {
    if (!root || root.dataset.atlasGeoLoaded === '1') return;
    root.dataset.atlasGeoLoaded = '1';
    root.textContent = 'ATLAS Geo 아카이브를 불러오는 중…';
    try {
      var response = await fetch('data/atlas_geo_snapshot.json', { cache: 'no-cache' });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      var data = await response.json();
      if (!data || data.status !== 'stale_archive' || !Array.isArray(data.theaters)) throw new Error('invalid archive contract');
      installStyles();
      render(root, data);
    } catch (error) {
      root.innerHTML = '<p class="hint">ATLAS Geo 아카이브를 표시하지 못했습니다. 기존 분쟁지도와 사건 데이터에는 영향이 없습니다.</p>';
      console.warn('ATLAS Geo archive', error);
    }
  }
  window.AtlasGeo = { mount: mount };
}());
