/* Panoptes v2 bridge for the standalone TGA event-context module.
 * Load after tga_flow_events.js + liq_charts.js and before app.js.
 */
(function (root, factory) {
  'use strict';
  var api = factory(root);
  if (root) root.PanoptesTgaFlowBridge = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : null, function (root) {
  'use strict';

  var DEFAULT_URL = '../data/tga-flow-events/current.json';
  var PHASE_KO = {
    CALENDAR_SCHEDULED: '공식 일정 등록',
    UPCOMING: '임박',
    COLLECTION_WINDOW_OPEN: '세수 유입 창',
    POST_EVENT_OBSERVATION: '사후 관찰',
    HISTORICAL: '종료',
    NO_RELEVANT_EVENT: '대기'
  };

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char];
    });
  }
  function todayUtc() {
    return new Date().toISOString().slice(0, 10);
  }
  function validDate(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    var parsed = Date.parse(value + 'T00:00:00Z');
    return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value;
  }
  function contextInputs(data) {
    var source = data || {};
    var funding = ((source.sections || {}).funding || {});
    var references = funding.references || {};
    return {
      tga_series: (funding.series || {}).TGA || {},
      tga_targets: references.treasury_cash_balance_assumptions || source.tga_targets || null,
      release_evidence: references.tga_release_evidence || source.tga_release_evidence || null
    };
  }
  function sourceLinks(config, event) {
    if (!config || !event) return '';
    var wanted = {};
    (event.evidence_source_ids || []).forEach(function (id) { wanted[id] = true; });
    return (config.sources || []).filter(function (source) {
      return wanted[source.source_id];
    }).map(function (source) {
      var label = source.source_id.indexOf('irs_') === 0 ? 'IRS' :
        (source.source_id.indexOf('treasury') >= 0 ? 'Treasury' : 'Federal Reserve');
      return '<a href="' + esc(source.source_url) + '" target="_blank" rel="noopener">' +
        esc(label) + ' ↗</a>';
    }).join('');
  }
  function timeline(config, currentId) {
    if (!config || !Array.isArray(config.events)) return '';
    return '<div class="tgaevt-timeline">' + config.events.map(function (event) {
      var active = event.event_id === currentId ? ' on' : '';
      var scope = event.payer_scopes.length > 1 ? '개인+법인' :
        (event.payer_scopes[0] === 'individual_nonwithheld' ? '개인' : '법인');
      return '<span class="tgaevt-chip' + active + '"><b>' + esc(event.event_date.slice(2).replace(/-/g, '')) +
        '</b>' + esc(scope + ' ' + event.installment + '차') + '</span>';
    }).join('') + '</div>';
  }
  function renderContextHtml(interpreted, config) {
    if (!interpreted || !interpreted.display) return '';
    var display = interpreted.display;
    var phase = PHASE_KO[interpreted.event_phase] || interpreted.event_phase;
    return '<section class="tgaevt" data-tga-event-context="1">' +
      '<div class="tgaevt-head"><b>🗓 TGA 공식 이벤트 컨텍스트</b>' +
      '<span class="tgaevt-phase">' + esc(phase) + '</span>' +
      '<span class="tgaevt-label">' + esc(interpreted.decision_label) + '</span></div>' +
      '<div class="tgaevt-title">' + esc(display.title_ko) + '</div>' +
      timeline(config, interpreted.event && interpreted.event.event_id) +
      '<div class="tgaevt-grid">' +
      '<div><small>기계적 영향</small><p>' + esc(display.mechanical_ko) + '</p></div>' +
      '<div><small>계절성 해석</small><p>' + esc(display.context_ko) + '</p></div>' +
      '<div><small>재무부 대응</small><p>' + esc(display.treasury_ko) + '</p></div>' +
      '<div><small>분기말 가정·방출</small><p>' + esc(display.target_ko) + '</p></div>' +
      '</div><div class="tgaevt-foot"><span>산식 <code>WALCL−TGA−RRP</code> 불변 · 기존 신호등 불변 · 백테스트 전 맥락 오버레이</span>' +
      '<span class="tgaevt-src">' + sourceLinks(config, interpreted.event) + '</span></div></section>';
  }
  function pendingHtml(message) {
    return '<section class="tgaevt tgaevt-pending" data-tga-event-context="1"><b>🗓 TGA 공식 이벤트 컨텍스트</b>' +
      '<p>' + esc(message) + '</p></section>';
  }
  function qualityBlockHtml(updated, today) {
    return '<section class="tgaevt tgaevt-block" data-tga-event-context="1"><b>입력 품질 차단</b>' +
      '<p>유동성 스냅샷 기준일 ' + esc(updated || 'UNKNOWN') + '이 현재 확인일 ' + esc(today) +
      '보다 미래입니다. 수치와 이벤트 해석을 표시하지 않습니다.</p></section>';
  }
  function injectCss(doc) {
    if (!doc || doc.getElementById('tgaEventContextCss')) return;
    var style = doc.createElement('style');
    style.id = 'tgaEventContextCss';
    style.textContent = [
      '.tgaevt{background:linear-gradient(135deg,#151326,#10161d);border:1px solid #5f54a055;border-radius:14px;',
      'padding:16px 18px;margin:-10px 0 24px;color:var(--ink,#dce4ea)}',
      '.tgaevt-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12.5px}',
      '.tgaevt-phase,.tgaevt-label{font-size:10px;font-weight:750;padding:3px 8px;border-radius:999px}',
      '.tgaevt-phase{background:#b48cff22;color:#c9aaff}.tgaevt-label{background:#2bc0d422;color:#59d5e3}',
      '.tgaevt-title{font-size:16px;font-weight:850;margin:10px 0 8px}',
      '.tgaevt-timeline{display:flex;gap:6px;overflow-x:auto;padding:2px 0 11px}',
      '.tgaevt-chip{display:flex;gap:5px;white-space:nowrap;border:1px solid #ffffff16;border-radius:7px;',
      'padding:4px 7px;font-size:9.5px;color:var(--dim,#8a93a3)}',
      '.tgaevt-chip b{font-family:var(--mono,monospace);color:inherit}.tgaevt-chip.on{border-color:#b48cff88;color:#d8c6ff;background:#b48cff14}',
      '.tgaevt-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}',
      '.tgaevt-grid>div{border:1px solid #ffffff12;border-radius:9px;padding:9px 11px;background:#ffffff05}',
      '.tgaevt-grid small{font-size:9.5px;font-weight:750;color:var(--dim,#8a93a3)}',
      '.tgaevt-grid p{font-size:11.5px;line-height:1.55;margin:3px 0 0}',
      '.tgaevt-foot{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-top:10px;',
      'padding-top:9px;border-top:1px solid #ffffff10;font-size:9.5px;color:var(--dim,#8a93a3)}',
      '.tgaevt-foot code{font-family:var(--mono,monospace)}.tgaevt-src{display:flex;gap:8px}',
      '.tgaevt-src a{color:#8fdce4;text-decoration:none}.tgaevt-pending{margin-top:12px}',
      '.tgaevt-pending p,.tgaevt-block p{font-size:11.5px;line-height:1.6;margin:6px 0 0}',
      '.tgaevt-block{border-color:#ff4d5e88;background:#2a1117;margin:12px 0}',
      '@media(max-width:600px){.tgaevt{padding:14px}.tgaevt-grid{grid-template-columns:1fr}}'
    ].join('');
    (doc.head || doc.documentElement).appendChild(style);
  }
  function insertAfterLights(el, html) {
    if (!el || !html || el.querySelector('[data-tga-event-context]')) return;
    var lights = el.querySelector('.liq2-lights');
    if (lights) lights.insertAdjacentHTML('afterend', html);
    else el.insertAdjacentHTML('beforeend', html);
  }
  function annotateTgaLight(el) {
    var cards = el ? el.querySelectorAll('.liq2-lcard') : [];
    for (var i = 0; i < cards.length; i++) {
      var title = cards[i].querySelector('.liq2-lt');
      if (!title || title.textContent.indexOf('TGA') !== 0) continue;
      var sub = cards[i].querySelector('.liq2-ls');
      if (sub) sub.textContent = '기계효과는 음(-) · 계절성/이벤트 맥락은 아래 별도 표시';
      cards[i].setAttribute('data-context-only-overlay', 'true');
      break;
    }
  }
  function install(target) {
    target = target || root;
    if (!target || !target.document || !target.PanoptesTgaFlowEvents ||
        typeof target.renderLiq2 !== 'function' || target.renderLiq2.__tgaEventWrapped) return false;
    var original = target.renderLiq2;
    var wrapped = function (el, data) {
      var today = todayUtc();
      var updated = data && data.updated;
      injectCss(target.document);
      if (!validDate(updated) || updated > today) {
        if (el) el.innerHTML = qualityBlockHtml(updated, today);
        return;
      }
      original(el, data);
      annotateTgaLight(el);
      var url = target.PANOPTES_TGA_EVENT_CONTEXT_URL || DEFAULT_URL;
      target.fetch(url, { cache: 'no-store' }).then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      }).then(function (config) {
        var input = contextInputs(data || {});
        var model = target.PanoptesTgaFlowEvents.validateConfig(config, updated, today);
        var interpreted = target.PanoptesTgaFlowEvents.interpret(config, {
          as_of_date: updated,
          now_date: today,
          tga_series: input.tga_series,
          tga_targets: input.tga_targets,
          release_evidence: input.release_evidence
        });
        insertAfterLights(el, interpreted
          ? renderContextHtml(interpreted, model)
          : pendingHtml('공식 일정 계약이 만료됐거나 검증에 실패해 이벤트 해석을 보류합니다.'));
      }).catch(function () {
        insertAfterLights(el, pendingHtml('공식 일정 데이터를 불러오지 못해 기존 유동성 수치만 표시합니다.'));
      });
    };
    wrapped.__tgaEventWrapped = true;
    wrapped.__original = original;
    target.renderLiq2 = wrapped;
    return true;
  }

  var api = {
    DEFAULT_URL: DEFAULT_URL,
    contextInputs: contextInputs,
    renderContextHtml: renderContextHtml,
    pendingHtml: pendingHtml,
    qualityBlockHtml: qualityBlockHtml,
    install: install
  };
  if (root) install(root);
  return api;
});
