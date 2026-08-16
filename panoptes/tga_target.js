/* 미 재무부 분기말 현금잔고 가정 — 공식 원문 검증·기간 선택 공통 모듈 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (root) root.PanoptesTgaTarget = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  var DAY = 86400000;
  var SOURCE_ID = 'us_treasury_quarterly_borrowing_estimates';
  var PUBLISHER = 'U.S. Department of the Treasury';

  function validDate(s) {
    if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    var t = Date.parse(s + 'T00:00:00Z');
    return Number.isFinite(t) && new Date(t).toISOString().slice(0, 10) === s;
  }
  function dateMs(s) {
    return validDate(s) ? Date.parse(s + 'T00:00:00Z') : NaN;
  }
  function yymmdd(s) {
    return validDate(s) ? s.slice(2).replace(/-/g, '') : '';
  }
  function asOfMs(value) {
    if (Number.isFinite(value)) return Number(value);
    if (validDate(value)) return dateMs(value);
    if (typeof value === 'string') {
      var parsed = Date.parse(value);
      if (Number.isFinite(parsed)) return parsed;
    }
    return Date.now();
  }
  function officialUrl(value, pathPattern) {
    if (typeof value !== 'string') return false;
    try {
      var url = new URL(value);
      return url.protocol === 'https:' && url.hostname === 'home.treasury.gov' &&
        !url.username && !url.password && (!url.port || url.port === '443') &&
        !url.search && !url.hash && pathPattern.test(url.pathname);
    } catch (_error) {
      return false;
    }
  }
  function quarterOf(targetDate) {
    if (!validDate(targetDate)) return null;
    var year = Number(targetDate.slice(0, 4));
    var monthDay = targetDate.slice(5);
    var quarter = { '03-31': 1, '06-30': 2, '09-30': 3, '12-31': 4 }[monthDay];
    return quarter ? { year: year, quarter: quarter } : null;
  }
  function clone(raw) {
    var out = {};
    Object.keys(raw).forEach(function (key) { out[key] = raw[key]; });
    return out;
  }
  function validateRelease(raw, cutoffMs) {
    if (!raw || typeof raw !== 'object') return null;
    if (raw.source_id !== SOURCE_ID || raw.publisher !== PUBLISHER) return null;
    if (!officialUrl(raw.source_url, /^\/news\/press-releases\/[a-z]{2}\d+\/?$/)) return null;
    if (!officialUrl(raw.discovery_url, /^\/policy-issues\/financing-the-government\/quarterly-refunding\/most-recent-quarterly-refunding-documents\/?$/)) return null;
    if (raw.sources_uses_url != null && !officialUrl(raw.sources_uses_url, /^\/system\/files\/[^?#]+\.pdf$/i)) return null;
    if (!validDate(raw.source_published_date)) return null;
    var published = dateMs(raw.source_published_date);
    if (published > cutoffMs + DAY) return null;
    if (raw.source_published_label !== yymmdd(raw.source_published_date)) return null;
    if (typeof raw.source_published_at !== 'string' || !Number.isFinite(Date.parse(raw.source_published_at))) return null;
    if (raw.source_published_at.slice(0, 10) !== raw.source_published_date) return null;
    if (typeof raw.release_id !== 'string' || raw.source_url.replace(/\/$/, '').split('/').pop() !== raw.release_id) return null;
    if (typeof raw.article_content_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(raw.article_content_sha256)) return null;
    return clone(raw);
  }
  function validateAssumption(raw, releaseDate) {
    if (!raw || typeof raw !== 'object') return null;
    var value = Number(raw.value);
    var q = quarterOf(raw.target_date);
    if (!Number.isFinite(value) || value <= 0 || value > 10000 || raw.unit !== 'billion_usd') return null;
    if (!q || dateMs(raw.target_date) < dateMs(releaseDate)) return null;
    if (raw.target_date_label !== yymmdd(raw.target_date)) return null;
    var expectedPeriod = 'Q' + q.quarter + ' ' + q.year;
    var expectedLabel = 'Q' + q.quarter + '-' + String(q.year).slice(2);
    if (raw.target_period !== expectedPeriod || raw.target_period_label !== expectedLabel) return null;
    return {
      value: value,
      unit: 'billion_usd',
      target_period: expectedPeriod,
      target_period_label: expectedLabel,
      target_date: raw.target_date,
      target_date_label: raw.target_date_label
    };
  }
  function validateConfig(raw, cutoff) {
    if (!raw || typeof raw !== 'object' || raw.schema_version !== 2 || !Array.isArray(raw.assumptions)) return null;
    var cutoffMs = asOfMs(cutoff);
    var release = validateRelease(raw.release, cutoffMs);
    if (!release || raw.assumptions.length < 1 || raw.assumptions.length > 4) return null;
    var assumptions = [];
    for (var i = 0; i < raw.assumptions.length; i++) {
      var item = validateAssumption(raw.assumptions[i], release.source_published_date);
      if (!item) return null;
      assumptions.push(item);
    }
    assumptions.sort(function (a, b) { return a.target_date.localeCompare(b.target_date); });
    for (var j = 1; j < assumptions.length; j++) {
      if (assumptions[j - 1].target_date === assumptions[j].target_date) return null;
    }
    var cutoffDate = new Date(cutoffMs).toISOString().slice(0, 10);
    var upcoming = assumptions.filter(function (item) { return item.target_date >= cutoffDate; });
    return {
      schema_version: 2,
      release: release,
      assumptions: assumptions,
      current: upcoming[0] || null,
      next: upcoming[1] || null,
      as_of: cutoffDate
    };
  }
  function displayModel(target, release, role) {
    if (!target || !release) return null;
    var value = Math.round(target.value) + 'B';
    var next = role === 'next';
    var lineLabel = (next ? '다음 ' : '재무부 ') + target.target_period_label.slice(0, 2) + '말 ' + value + ' · ' + target.target_date_label;
    var legendLabel = (next ? '다음 ' : '미 재무부 ') + target.target_date_label + ' 분기말 가정 ' + value;
    return {
      role: next ? 'next' : 'current',
      lineLabel: lineLabel,
      legendLabel: legendLabel + ' · 공식 발표 ' + release.source_published_label,
      sourceUrl: release.source_url
    };
  }
  function displayModels(model) {
    if (!model || !model.release) return [];
    var result = [];
    if (model.current) result.push(displayModel(model.current, model.release, 'current'));
    if (model.next) result.push(displayModel(model.next, model.release, 'next'));
    return result.filter(Boolean);
  }

  return {
    validateConfig: validateConfig,
    displayModel: displayModel,
    displayModels: displayModels,
    yymmdd: yymmdd
  };
});
