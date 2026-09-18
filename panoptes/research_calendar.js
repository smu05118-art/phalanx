/* Source-preserving calendar projection. No network, storage, DOM, or clock reads. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else if (typeof define === 'function' && define.amd) define([], factory);
  else root.PHXCalendar = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var own = function (o, k) { return Object.prototype.hasOwnProperty.call(o, k); };
  var object = function (v) { return v !== null && typeof v === 'object' && !Array.isArray(v); };
  var text = function (v) { return typeof v === 'string' ? v.trim() : ''; };
  var pad = function (n) { return String(n).padStart(2, '0'); };
  var unknown = function (v) { return v == null || (typeof v === 'string' && /^(?:\s*|TBD|미정|미공지|미확인)$/i.test(v.trim())); };

  function validDate(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    var y = +value.slice(0, 4), m = +value.slice(5, 7), d = +value.slice(8, 10);
    if (y < 1 || m < 1 || m > 12 || d < 1) return false;
    var leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
    return d <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];
  }

  function safeHttps(value) {
    if (typeof value !== 'string' || !value || /[\x00-\x20\x7f\\]/.test(value) || !/^https:\/\//i.test(value)) return null;
    try {
      var u = new URL(value);
      if (u.protocol !== 'https:' || !u.hostname || u.username || u.password) return null;
      return u.href;
    } catch (_) { return null; }
  }

  function canonical(value, depth, seen) {
    if (depth > 40) throw new Error('row_too_deep');
    if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
    if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
    if (typeof value !== 'object' || seen.has(value)) throw new Error('invalid_json_row');
    seen.add(value);
    var result;
    if (Array.isArray(value)) result = '[' + value.map(function (v) { return canonical(v, depth + 1, seen); }).join(',') + ']';
    else result = '{' + Object.keys(value).sort().map(function (k) { return JSON.stringify(k) + ':' + canonical(value[k], depth + 1, seen); }).join(',') + '}';
    seen.delete(value);
    return result;
  }

  function fingerprint(value) {
    var a = 2166136261, b = 5381;
    for (var i = 0; i < value.length; i++) {
      a = Math.imul(a ^ value.charCodeAt(i), 16777619);
      b = Math.imul(b, 33) ^ value.charCodeAt(i);
    }
    return (a >>> 0).toString(16).padStart(8, '0') + (b >>> 0).toString(16).padStart(8, '0');
  }

  function kstParts(ts) {
    if (typeof ts !== 'number' || !Number.isSafeInteger(ts)) return null;
    var shifted = new Date(ts * 1000 + 9 * 3600000);
    if (!Number.isFinite(shifted.getTime())) return null;
    var y = shifted.getUTCFullYear();
    if (y < 1 || y > 9999) return null;
    return { date: String(y).padStart(4, '0') + '-' + pad(shifted.getUTCMonth() + 1) + '-' + pad(shifted.getUTCDate()),
      time: pad(shifted.getUTCHours()) + ':' + pad(shifted.getUTCMinutes()) };
  }

  function lifecycle(raw, undated) {
    var s = text(raw).toLowerCase();
    var label = { cancelled: '취소', canceled: '취소', done: '완료', completed: '완료',
      scheduled: '예정', pending: '기록 대조 대기', estimated: '계산 예상일', tbd: '일정 미정' }[s];
    // A URL, an elapsed date, or a timestamp never establishes verified/confirmed.
    if (!label) label = s ? '상태 미확인' : (undated ? '일정 미정' : '일정 등록');
    if (undated && label !== '일정 미정') label += ' · 날짜 미정';
    return label;
  }

  function build(earnings, fed) {
    var events = [], sources = [], issues = [], ids = new Map();
    function issue(source, rowIndex, code, field) {
      var out = { source: source, rowIndex: rowIndex, code: code };
      if (field) out.field = field;
      issues.push(out);
    }
    function sourceDocument(name, data, field, detailUrl) {
      var meta = { id: name, status: 'ok', inputCount: 0, eventCount: 0, rejectedCount: 0, duplicateCount: 0,
        updatedLabel: null, detailUrl: detailUrl };
      sources.push(meta);
      if (data == null) { meta.status = 'unavailable'; issue(name, null, 'source_unavailable'); return [meta, []]; }
      if (!object(data) || !Array.isArray(data[field])) {
        meta.status = 'invalid'; issue(name, null, 'invalid_source_shape', field); return [meta, []];
      }
      meta.inputCount = data[field].length;
      // Publication metadata stays separate from event dates.
      if (name === 'earnings' && validDate(data.generated)) meta.updatedLabel = data.generated;
      if (name === 'fed' && kstParts(data.updated_ts)) {
        var updated = kstParts(data.updated_ts); meta.updatedLabel = updated.date + ' ' + updated.time + ' KST';
      }
      return [meta, data[field]];
    }
    function sourceLink(row, name, i) {
      var value = own(row, 'source_url') ? row.source_url : row.url;
      var provided = !unknown(value), url = provided ? safeHttps(value) : null;
      if (provided && !url) issue(name, i, 'unsafe_source_url', own(row, 'source_url') ? 'source_url' : 'url');
      return { url: url, label: url ? '원문 연결' : (provided ? '원문 URL 사용 불가' : '원문 URL 미제공') };
    }
    function appendRows(name, data, field, detailUrl, convert) {
      var pair = sourceDocument(name, data, field, detailUrl), meta = pair[0], seen = new Set(), upstream = new Map();
      pair[1].forEach(function (row, i) {
        if (!object(row)) { meta.rejectedCount++; issue(name, i, 'invalid_row'); return; }
        var serial;
        try { serial = canonical(row, 0, new Set()); }
        catch (_) { meta.rejectedCount++; issue(name, i, 'invalid_json_row'); return; }
        if (seen.has(serial)) { meta.duplicateCount++; return; }
        var event = convert(row, i);
        if (!event) { meta.rejectedCount++; return; }
        seen.add(serial);
        var key = text(row.id);
        if (key && upstream.has(key) && upstream.get(key) !== serial) issue(name, i, 'conflicting_source_id', 'id');
        if (key) upstream.set(key, serial);
        var base = event.kind + '-' + fingerprint(serial), id = base, n = 1;
        while (ids.has(id) && ids.get(id) !== serial) id = base + '-' + (++n);
        ids.set(id, serial); event.id = id;
        event.searchText = [event.title, event.ticker, event.market, event.date, event.timeLabel,
          event.timezoneLabel, event.statusLabel, event.sourceLabel, text(row.kind)].filter(Boolean).join(' ').toLowerCase();
        events.push(event); meta.eventCount++;
      });
      if (meta.status === 'ok' && meta.rejectedCount) meta.status = 'partial';
    }

    appendRows('earnings', earnings, 'entries', 'index.html#tab=ecal', function (row, i) {
      var missing = unknown(row.date);
      if (!missing && !validDate(row.date)) { issue('earnings', i, 'invalid_date', 'date'); return null; }
      var market = text(row.market), ticker = text(row.ticker), title = text(row.name) || ticker;
      if (!title) { issue('earnings', i, 'missing_title', 'name'); return null; }
      var time = text(row.time), timeLabel = '시각 미상';
      if (row.all_day === true) timeLabel = row.time_confirmed === false ? '날짜만 공지 · 시각 미상' : '종일';
      else if (time === '장전' || time === '장마감') timeLabel = time + ' · 정확한 시각 미상';
      else if (row.time_confirmed !== false && time && !unknown(time)) {
        if (/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(time)) timeLabel = time + ' (원자료 현지시각)';
        else issue('earnings', i, 'unsupported_time_label', 'time');
      }
      var link = sourceLink(row, 'earnings', i);
      return { id: null, kind: 'earnings', title: title, ticker: ticker || null, market: market || null,
        date: missing ? null : row.date, timeLabel: timeLabel,
        timezoneLabel: market === 'US' ? '미국 현지일' : market === 'JP' ? '일본 현지일' : (market ? market + ' 현지일' : '현지일 · 시간대 미상'),
        statusLabel: lifecycle(row.status, missing) + ' · ' + link.label,
        sourceLabel: text(row.src) || '출처 미상', sourceUrl: link.url,
        detailUrl: 'index.html#tab=ecal', phx: row.phx === true, searchText: '' };
    });

    appendRows('fed', fed, 'items', 'panoptes/#fed', function (row, i) {
      var missing = unknown(row.ts), when = missing ? null : kstParts(row.ts);
      if (!missing && !when) { issue('fed', i, 'invalid_epoch_seconds', 'ts'); return null; }
      var title = text(row.title) || text(row.title_en) || text(row.id);
      if (!title) { issue('fed', i, 'missing_title', 'title'); return null; }
      var timeLabel = '시각 미상';
      if (row.all_day === true) timeLabel = row.time_confirmed === false ? '날짜만 공지 · 시각 미상' : '종일';
      else if (when && row.time_confirmed === true) timeLabel = when.time;
      var link = sourceLink(row, 'fed', i);
      return { id: null, kind: 'macro', title: title, ticker: text(row.ticker) || null, market: text(row.country) || null,
        date: when ? when.date : null, timeLabel: timeLabel, timezoneLabel: 'KST',
        statusLabel: lifecycle(row.status, missing) + ' · ' + link.label,
        sourceLabel: text(row.src) || '출처 미상', sourceUrl: link.url,
        detailUrl: 'panoptes/#fed', phx: row.phx === true, searchText: '' };
    });
    // These are display dates in distinct source time bases, not absolute chronology.
    events.sort(function (a, b) {
      if (a.date === null && b.date !== null) return 1;
      if (b.date === null && a.date !== null) return -1;
      return String(a.date || '').localeCompare(String(b.date || '')) || a.kind.localeCompare(b.kind) || a.title.localeCompare(b.title) || a.id.localeCompare(b.id);
    });
    return { events: events, sources: sources, issues: issues };
  }

  return Object.freeze({ build: build });
}));
