/* TGA 재무부 분기말 현금잔고 가정 — 검증·표시 공통 모듈 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (root) root.PanoptesTgaTarget = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  var ALLOWED_STATUS = { current_verified: true, historical_latest_verified: true };

  function validDate(s) {
    if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    var t = Date.parse(s + 'T00:00:00Z');
    return Number.isFinite(t) && new Date(t).toISOString().slice(0, 10) === s;
  }
  function validateTarget(raw, nowMs) {
    if (!raw || typeof raw !== 'object') return null;
    var value = Number(raw.value);
    var now = Number.isFinite(nowMs) ? nowMs : Date.now();
    var published = Date.parse(raw.source_published_date || '');
    var targetDate = Date.parse(raw.target_date || '');
    if (!Number.isFinite(value) || value <= 0 || value > 10000 || raw.unit !== 'billion_usd') return null;
    if (!validDate(raw.source_published_date) || published > now + 86400000) return null;
    if (!validDate(raw.target_date) || !Number.isFinite(targetDate)) return null;
    if (!ALLOWED_STATUS[raw.current_status]) return null;
    if (typeof raw.source_id !== 'string' || !/^(gs_gir|us_treasury)_/.test(raw.source_id)) return null;
    if (typeof raw.target_period !== 'string' || !raw.target_period.trim()) return null;
    /* 현행으로 표기된 목표일이 이미 끝났다면 선을 숨긴다. 과거 참고값은 명시적 stale 상태만 허용. */
    if (raw.current_status === 'current_verified' && targetDate + 86400000 < now) return null;
    var out = {};
    Object.keys(raw).forEach(function (k) { out[k] = raw[k]; });
    out.value = value;
    return out;
  }
  function validateConfig(raw, nowMs) {
    return validateTarget(raw && raw.treasury_cash_balance_assumption, nowMs);
  }
  function displayModel(target) {
    var t = validateTarget(target);
    if (!t) return null;
    var value = Math.round(t.value) + 'B';
    var period = t.target_period_label || t.target_period;
    var checked = t.source_published_label || t.source_published_date;
    if (t.current_status === 'current_verified') {
      return {
        stale: false,
        lineLabel: '미 재무부 분기말 가정 ' + value + ' · ' + period,
        legendLabel: '미 재무부 분기말 가정 ' + value + ' · ' + period + ' · 현행 공식값 · 확인 ' + checked
      };
    }
    return {
      stale: true,
      lineLabel: 'DB 마지막 확인값 ' + value + ' · ' + period + ' · 현행성 미확인',
      legendLabel: 'DB 마지막 확인값 ' + value + ' · ' + period + ' · 현행성 미확인 · 확인 ' + checked
    };
  }

  return { validateTarget: validateTarget, validateConfig: validateConfig, displayModel: displayModel };
});
