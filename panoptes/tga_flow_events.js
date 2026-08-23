/* Panoptes TGA event context — official-calendar validation + interpretation overlay.
 *
 * This module never changes WALCL-TGA-RRP or the existing traffic light.  It
 * separates the direct accounting effect of a TGA inflow from its scheduled
 * seasonal context and from any later, evidence-confirmed cash release.
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (root) root.PanoptesTgaFlowEvents = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  var CONTRACT_ID = 'atlas-panoptes-tga-event-context-v1';
  var LEGACY_CONTRACT_ID = 'panoptes-tga-event-context-v1';
  var DECISION_LABEL = '판단 보조용 자동등급';
  var DAY = 86400000;
  var ALLOWED_HOSTS = {
    'www.irs.gov': true,
    'irs.gov': true,
    'home.treasury.gov': true,
    'fiscaldata.treasury.gov': true,
    'api.fiscaldata.treasury.gov': true,
    'www.federalreserve.gov': true,
    'federalreserve.gov': true
  };
  var PAYER_SCOPES = {
    individual_nonwithheld: true,
    calendar_year_corporation: true
  };

  function isObject(value) {
    return !!value && typeof value === 'object' && !Array.isArray(value);
  }
  function validDate(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    var time = Date.parse(value + 'T00:00:00Z');
    return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value;
  }
  function dateMs(value) {
    return validDate(value) ? Date.parse(value + 'T00:00:00Z') : NaN;
  }
  function validTimestamp(value) {
    if (typeof value !== 'string' || !value) return false;
    var parsed = Date.parse(value);
    return Number.isFinite(parsed) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value);
  }
  function validSha(value) {
    return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  }
  function yymmdd(value) {
    return validDate(value) ? value.slice(2).replace(/-/g, '') : '';
  }
  function todayUtc() {
    return new Date().toISOString().slice(0, 10);
  }
  function hostOf(value) {
    try {
      var url = new URL(value);
      if (url.protocol !== 'https:' || url.username || url.password) return null;
      return url.hostname;
    } catch (error) {
      return null;
    }
  }
  function dayDiff(later, earlier) {
    return Math.round((dateMs(later) - dateMs(earlier)) / DAY);
  }
  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function canonicalTitle(event, payerScopes) {
    var hasIndividual = payerScopes.indexOf('individual_nonwithheld') >= 0;
    var hasCorporate = payerScopes.indexOf('calendar_year_corporation') >= 0;
    var prefix = hasIndividual && hasCorporate ? '미국' :
      (hasIndividual ? '미국 개인' : '미국 역년 법인');
    return prefix + ' ' + event.tax_year + '년 추정세 ' + event.installment + '차 납부분';
  }

  /* Canonical Atlas dashboard export -> small browser validation model. */
  function normalizeCanonical(raw) {
    if (!isObject(raw) || raw.schema_version !== CONTRACT_ID) return null;
    if (raw.status !== 'ok' || !Number.isInteger(raw.tax_year) ||
        !validTimestamp(raw.collected_at) || raw.signal_label !== DECISION_LABEL) return null;
    var contract = raw.net_liquidity_contract;
    if (!isObject(contract) || contract.formula !== 'WALCL - TGA - RRP' ||
        contract.formula_override_allowed !== false ||
        contract.tga_increase_mechanical_effect !== 'net_liquidity_proxy_decrease' ||
        contract.scheduled_event_policy !== 'contextualize_seasonality_without_reversing_formula_sign') return null;
    var release = raw.release_watch_policy;
    if (!isObject(release) || release.quarter_end_assumption_is_cap !== false ||
        release.reference_overshoot_alone_confirms_release !== false ||
        release.positive_liquidity_effect_before_confirmation !== false ||
        !Array.isArray(release.confirmation_requires_any) || !release.confirmation_requires_any.length) return null;
    var confirmationSet = {};
    release.confirmation_requires_any.forEach(function (condition) {
      confirmationSet[condition] = true;
    });
    if (Object.keys(confirmationSet).length !== 3 ||
        !confirmationSet.subsequent_observed_tga_drawdown ||
        !confirmationSet.official_treasury_outflow_or_net_financing_evidence_implying_drawdown ||
        !confirmationSet.verified_federal_reserve_offset_or_observed_reserve_replenishment) return null;
    var treasury = raw.treasury_context;
    var cashReference = isObject(treasury) ? treasury.cash_balance_reference : null;
    if (!isObject(treasury) || !isObject(treasury.cash_balance_reference) ||
        cashReference.semantic !== 'treasury_assumption_not_cap' ||
        !validDate(cashReference.reference_date) || cashReference.unit !== 'billion_usd' ||
        !Number.isFinite(Number(cashReference.value)) || Number(cashReference.value) < 0 ||
        Number(cashReference.value) > 5000) return null;
    if (!Array.isArray(raw.sources) || !Array.isArray(raw.events) || !raw.events.length) return null;
    var normalizedSources = raw.sources.map(function (source) {
      if (!isObject(source)) return null;
      if (source.source_published_date !== 'UNKNOWN' && !validDate(source.source_published_date)) return null;
      if (source.source_updated_date !== 'UNKNOWN' && !validDate(source.source_updated_date)) return null;
      if (validDate(source.source_published_date) && source.source_published_date > raw.collected_at.slice(0, 10)) return null;
      if (validDate(source.source_updated_date) && source.source_updated_date > raw.collected_at.slice(0, 10)) return null;
      return {
        source_id: source.source_id,
        source_url: source.source_url,
        raw_sha256: source.content_sha256,
        source_published_at: 'UNKNOWN',
        source_updated_at: 'UNKNOWN',
        source_published_date: source.source_published_date,
        source_updated_date: source.source_updated_date,
        publisher: source.publisher,
        source_role: source.source_role,
        media_type: source.media_type
      };
    });
    if (normalizedSources.some(function (source) { return source == null; })) return null;
    var sourceIds = {};
    normalizedSources.forEach(function (source) { sourceIds[source.source_id] = true; });
    var normalizedEvents = [];
    for (var i = 0; i < raw.events.length; i++) {
      var sourceEvent = raw.events[i];
      if (!isObject(sourceEvent) || sourceEvent.event_type !== 'us_estimated_tax_due_date' ||
          !validDate(sourceEvent.event_date) || sourceEvent.event_date_role !== 'statutory_due_date' ||
          !Number.isInteger(sourceEvent.tax_year) || !Array.isArray(sourceEvent.payer_scopes) ||
          !sourceEvent.payer_scopes.length || !isObject(sourceEvent.cash_flow_context) ||
          !isObject(sourceEvent.interpretation)) return null;
      var payerScopes = [], evidence = {}, installment = null;
      for (var p = 0; p < sourceEvent.payer_scopes.length; p++) {
        var payer = sourceEvent.payer_scopes[p];
        if (!isObject(payer) || !Number.isInteger(payer.installment_number) ||
            !Array.isArray(payer.source_ids) || !payer.source_ids.length) return null;
        var mapped = payer.payer_type === 'individual' ? 'individual_nonwithheld' :
          (payer.payer_type === 'calendar_year_corporation' ? 'calendar_year_corporation' : null);
        if (!mapped || payerScopes.indexOf(mapped) >= 0) return null;
        if (installment == null) installment = payer.installment_number;
        if (installment !== payer.installment_number) return null;
        payerScopes.push(mapped);
        payer.source_ids.forEach(function (id) { evidence[id] = true; });
      }
      evidence[contract.source_id] = true;
      var guidance = null;
      if (sourceEvent.treasury_financing_context_id != null) {
        if (sourceEvent.treasury_financing_context_id !== treasury.context_id ||
            !isObject(treasury.september_short_bill_guidance) ||
            treasury.september_short_bill_guidance.status !== 'expected_reduction_announced' ||
            treasury.september_short_bill_guidance.interpretation !== 'less_issuance_than_otherwise_not_an_observed_tga_release') return null;
        evidence[treasury.source_id] = true;
        guidance = {
          effect: 'additional_drain_mitigation',
          release_confirmation: false,
          source_id: treasury.source_id
        };
      }
      var flow = sourceEvent.cash_flow_context;
      if (flow.expected_tga_direction !== 'increase' ||
          flow.expected_bank_reserve_direction !== 'decrease' ||
          flow.net_liquidity_proxy_effect !== 'drain' ||
          flow.classification !== 'scheduled_seasonal_drain' ||
          flow.formula_override !== false ||
          sourceEvent.interpretation.mechanical_effect !== 'negative_for_net_liquidity_proxy' ||
          sourceEvent.interpretation.positive_effect_allowed_without_observed_offset_or_drawdown !== false) return null;
      var normalizedEvent = {
        event_id: sourceEvent.event_id,
        event_type: 'estimated_tax_due',
        event_date: sourceEvent.event_date,
        event_date_role: sourceEvent.event_date_role,
        tax_year: sourceEvent.tax_year,
        installment: installment,
        payer_scopes: payerScopes,
        mechanics: {
          tga_direction: 'up',
          bank_reserves: 'down_all_else_equal',
          net_liquidity_proxy: 'down_all_else_equal'
        },
        classification: 'scheduled_seasonal_drain',
        formula_override: false,
        existing_light_override: false,
        automatic_risk_off: false,
        evidence_source_ids: Object.keys(evidence).sort(),
        title_ko: canonicalTitle({ tax_year: sourceEvent.tax_year, installment: installment }, payerScopes)
      };
      if (guidance) normalizedEvent.treasury_guidance = guidance;
      normalizedEvents.push(normalizedEvent);
    }
    var validThrough = normalizedEvents.map(function (event) { return event.event_date; }).sort().pop();
    return {
      schema_version: 1,
      contract_id: CONTRACT_ID,
      as_of_date: raw.collected_at.slice(0, 10),
      collected_at: raw.collected_at,
      valid_through: validThrough,
      policy: {
        net_liquidity_formula: 'WALCL-TGA-RRP',
        formula_override: false,
        existing_light_override: false,
        tga_inflow_mechanical_effect: 'negative',
        scheduled_event_signal_policy: 'context_only',
        quarter_end_assumption_role: 'reference_not_cap',
        release_confirmation_policy: 'observed_outflow_required',
        decision_label: DECISION_LABEL
      },
      display: { upcoming_days: 30, collection_days_after: 3, observation_days_after: 14 },
      events: normalizedEvents,
      sources: normalizedSources,
      canonical: clone(raw)
    };
  }

  function normalizeConfig(raw) {
    if (isObject(raw) && raw.schema_version === CONTRACT_ID) return normalizeCanonical(raw);
    if (isObject(raw) && raw.schema_version === 1 &&
        (raw.contract_id === CONTRACT_ID || raw.contract_id === LEGACY_CONTRACT_ID)) {
      var legacy = clone(raw);
      legacy.contract_id = CONTRACT_ID;
      return legacy;
    }
    return null;
  }

  function validatePolicy(policy) {
    return isObject(policy) &&
      policy.net_liquidity_formula === 'WALCL-TGA-RRP' &&
      policy.formula_override === false &&
      policy.existing_light_override === false &&
      policy.tga_inflow_mechanical_effect === 'negative' &&
      policy.scheduled_event_signal_policy === 'context_only' &&
      policy.quarter_end_assumption_role === 'reference_not_cap' &&
      policy.release_confirmation_policy === 'observed_outflow_required' &&
      policy.decision_label === DECISION_LABEL;
  }

  function validateSources(sources, collectedAt) {
    if (!Array.isArray(sources) || sources.length < 3) return null;
    var result = [], seen = {};
    for (var i = 0; i < sources.length; i++) {
      var source = sources[i];
      if (!isObject(source) || typeof source.source_id !== 'string' ||
          !/^[a-z0-9_.-]+$/.test(source.source_id) || seen[source.source_id]) return null;
      var host = hostOf(source.source_url);
      if (!host || !ALLOWED_HOSTS[host] || !validSha(source.raw_sha256)) return null;
      if (source.source_published_at !== 'UNKNOWN' && !validTimestamp(source.source_published_at)) return null;
      if (source.source_updated_at !== 'UNKNOWN' && !validTimestamp(source.source_updated_at)) return null;
      if (validTimestamp(source.source_published_at) && Date.parse(source.source_published_at) > Date.parse(collectedAt)) return null;
      if (validTimestamp(source.source_updated_at) && Date.parse(source.source_updated_at) > Date.parse(collectedAt)) return null;
      seen[source.source_id] = true;
      result.push(clone(source));
    }
    return { rows: result, ids: seen };
  }

  function validateEvent(event, sourceIds) {
    if (!isObject(event) || typeof event.event_id !== 'string' ||
        !/^[a-z0-9_.-]+$/.test(event.event_id) || !validDate(event.event_date) ||
        event.event_date_role !== 'statutory_due_date' ||
        event.event_type !== 'estimated_tax_due' ||
        !Number.isInteger(event.tax_year) || !Number.isInteger(event.installment) ||
        event.installment < 1 || event.installment > 4 ||
        typeof event.title_ko !== 'string' || !event.title_ko.trim()) return null;
    if (!Array.isArray(event.payer_scopes) || !event.payer_scopes.length) return null;
    var scopeSeen = {};
    for (var s = 0; s < event.payer_scopes.length; s++) {
      var scope = event.payer_scopes[s];
      if (!PAYER_SCOPES[scope] || scopeSeen[scope]) return null;
      scopeSeen[scope] = true;
    }
    if (!isObject(event.mechanics) || event.mechanics.tga_direction !== 'up' ||
        event.mechanics.bank_reserves !== 'down_all_else_equal' ||
        event.mechanics.net_liquidity_proxy !== 'down_all_else_equal' ||
        event.classification !== 'scheduled_seasonal_drain' ||
        event.formula_override !== false || event.existing_light_override !== false ||
        event.automatic_risk_off !== false) return null;
    if (!Array.isArray(event.evidence_source_ids) || !event.evidence_source_ids.length) return null;
    for (var e = 0; e < event.evidence_source_ids.length; e++) {
      if (!sourceIds[event.evidence_source_ids[e]]) return null;
    }
    if (event.treasury_guidance != null) {
      if (!isObject(event.treasury_guidance) ||
          event.treasury_guidance.effect !== 'additional_drain_mitigation' ||
          event.treasury_guidance.release_confirmation !== false ||
          !sourceIds[event.treasury_guidance.source_id]) return null;
    }
    return clone(event);
  }

  function validateConfig(raw, asOf, nowDate) {
    raw = normalizeConfig(raw);
    if (!raw || raw.schema_version !== 1 || raw.contract_id !== CONTRACT_ID ||
        !validDate(raw.as_of_date) || !validTimestamp(raw.collected_at) ||
        !validDate(raw.valid_through) || !validatePolicy(raw.policy)) return null;
    asOf = asOf || raw.as_of_date;
    nowDate = nowDate || todayUtc();
    if (!validDate(asOf) || !validDate(nowDate) || asOf > nowDate ||
        raw.as_of_date > nowDate || asOf > raw.valid_through) return null;
    if (Date.parse(raw.collected_at) > Date.parse(nowDate + 'T23:59:59Z')) return null;
    var sources = validateSources(raw.sources, raw.collected_at);
    if (!sources) return null;
    var display = raw.display;
    if (!isObject(display) || !Number.isInteger(display.upcoming_days) ||
        !Number.isInteger(display.collection_days_after) ||
        !Number.isInteger(display.observation_days_after) ||
        display.upcoming_days < 1 || display.upcoming_days > 90 ||
        display.collection_days_after < 0 || display.collection_days_after > 7 ||
        display.observation_days_after <= display.collection_days_after ||
        display.observation_days_after > 45) return null;
    if (!Array.isArray(raw.events) || !raw.events.length) return null;
    var events = [], eventSeen = {}, previous = '';
    for (var i = 0; i < raw.events.length; i++) {
      var event = validateEvent(raw.events[i], sources.ids);
      if (!event || eventSeen[event.event_id] || (previous && event.event_date < previous)) return null;
      eventSeen[event.event_id] = true;
      previous = event.event_date;
      events.push(event);
    }
    var model = clone(raw);
    model.events = events;
    model.sources = sources.rows;
    model.as_of = asOf;
    return model;
  }

  function phaseOf(eventDate, asOf, display) {
    var until = dayDiff(eventDate, asOf);
    if (until > display.upcoming_days) return 'CALENDAR_SCHEDULED';
    if (until > 0) return 'UPCOMING';
    var after = -until;
    if (after <= display.collection_days_after) return 'COLLECTION_WINDOW_OPEN';
    if (after <= display.observation_days_after) return 'POST_EVENT_OBSERVATION';
    return 'HISTORICAL';
  }

  function relevantEvent(model, asOf) {
    var events = model.events || [];
    var candidates = [];
    var phasePriority = {
      COLLECTION_WINDOW_OPEN: 0,
      POST_EVENT_OBSERVATION: 1,
      UPCOMING: 2,
      CALENDAR_SCHEDULED: 3
    };
    for (var i = 0; i < events.length; i++) {
      var diff = dayDiff(events[i].event_date, asOf);
      var phase = phaseOf(events[i].event_date, asOf, model.display);
      if (phase !== 'HISTORICAL') candidates.push({ event: events[i], diff: diff, phase: phase });
    }
    if (!candidates.length) return null;
    candidates.sort(function (a, b) {
      var ap = phasePriority[a.phase], bp = phasePriority[b.phase];
      if (ap !== bp) return ap - bp;
      return Math.abs(a.diff) - Math.abs(b.diff);
    });
    return candidates[0];
  }

  function latestTga(series, asOf, nowDate) {
    if (!isObject(series)) return { observation: null, future_ignored: false };
    var keys = Object.keys(series).sort(), future = false, chosen = null;
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i], value = Number(series[key]);
      if (!validDate(key) || !Number.isFinite(value)) continue;
      if (key > nowDate || key > asOf) { future = true; continue; }
      chosen = { observation_date: key, value_billion_usd: value };
    }
    return { observation: chosen, future_ignored: future };
  }

  function targetRows(targets) {
    var rows = [];
    if (isObject(targets) && Array.isArray(targets.assumptions)) rows = targets.assumptions;
    else if (isObject(targets)) {
      if (isObject(targets.current)) rows.push(targets.current);
      if (isObject(targets.next)) rows.push(targets.next);
    }
    return rows.filter(function (row) {
      return isObject(row) && validDate(row.target_date) && Number.isFinite(Number(row.value));
    }).map(function (row) {
      return { target_date: row.target_date, value_billion_usd: Number(row.value) };
    }).sort(function (a, b) { return a.target_date.localeCompare(b.target_date); });
  }

  function observationOn(series, observationDate, asOf, nowDate) {
    if (!isObject(series) || !validDate(observationDate) ||
        observationDate > asOf || observationDate > nowDate) return null;
    var value = Number(series[observationDate]);
    return Number.isFinite(value)
      ? { observation_date: observationDate, value_billion_usd: value }
      : null;
  }

  function hasPostTargetDrawdown(series, targetDate, anchorValue, asOf, nowDate) {
    if (!isObject(series) || !validDate(targetDate) || !Number.isFinite(anchorValue)) return false;
    var keys = Object.keys(series);
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i], value = Number(series[key]);
      if (validDate(key) && key > targetDate && key <= asOf && key <= nowDate &&
          Number.isFinite(value) && value < anchorValue) return true;
    }
    return false;
  }

  function targetAssessment(observation, targets, releaseEvidence, series, asOf, nowDate) {
    if (!observation) return {
      status: 'OBSERVATION_MISSING', release_status: 'NOT_EVALUATED',
      note_ko: 'TGA 관측값이 없어 분기말 가정 비교를 보류합니다.'
    };
    var rows = targetRows(targets);
    if (!rows.length) return {
      status: 'ASSUMPTION_MISSING', release_status: 'NOT_EVALUATED',
      note_ko: '유효한 재무부 분기말 현금잔고 가정이 없어 비교를 보류합니다.'
    };
    asOf = validDate(asOf) ? asOf : observation.observation_date;
    nowDate = validDate(nowDate) ? nowDate : asOf;
    var exact = null, next = null, previous = null;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].target_date === observation.observation_date) exact = rows[i];
      if (!next && rows[i].target_date >= observation.observation_date) next = rows[i];
      if (rows[i].target_date < observation.observation_date) previous = rows[i];
    }
    var evidence = isObject(releaseEvidence) ? releaseEvidence : {};
    var priorAnchor = previous
      ? observationOn(series, previous.target_date, asOf, nowDate)
      : null;
    if (!exact && previous && priorAnchor &&
        priorAnchor.value_billion_usd > previous.value_billion_usd) {
      var priorGap = priorAnchor.value_billion_usd - previous.value_billion_usd;
      var observedPostTargetDrawdown = hasPostTargetDrawdown(
        series, previous.target_date, priorAnchor.value_billion_usd, asOf, nowDate
      );
      var priorRelease = evidence.observed_tga_drawdown === true ||
        evidence.dts_net_withdrawals_observed === true ||
        evidence.verified_federal_reserve_offset === true ||
        evidence.observed_reserve_replenishment === true || observedPostTargetDrawdown;
      return {
        status: 'ABOVE_ASSUMPTION_WATCH',
        release_status: priorRelease ? 'RELEASE_CONFIRMED' : 'RELEASE_EVIDENCE_PENDING',
        target_date: previous.target_date,
        target_value_billion_usd: previous.value_billion_usd,
        target_date_observation_billion_usd: priorAnchor.value_billion_usd,
        latest_observation_date: observation.observation_date,
        latest_observation_billion_usd: observation.value_billion_usd,
        distance_billion_usd: priorGap,
        note_ko: priorRelease
          ? '분기말 가정 상회 뒤 실제 TGA 감소·DTS 순인출·Fed 상쇄 중 하나가 확인됐습니다.'
          : '분기말 가정 상회 WATCH가 유지 중이며 TGA 감소·DTS 순인출·Fed 상쇄 확인이 필요합니다.'
      };
    }
    if (!exact) {
      if (!next) return {
        status: previous && !priorAnchor ? 'POST_TARGET_ANCHOR_MISSING' : 'NO_ACTIVE_ASSUMPTION',
        release_status: 'NOT_EVALUATED',
        note_ko: previous && !priorAnchor
          ? '분기말 기준일의 TGA 관측값이 없어 상회·방출 판정을 보류합니다.'
          : '관측일 이후의 유효한 분기말 가정이 없습니다.'
      };
      var distance = observation.value_billion_usd - next.value_billion_usd;
      return {
        status: 'DISTANCE_ONLY', release_status: 'NOT_EVALUATED', target_date: next.target_date,
        target_value_billion_usd: next.value_billion_usd,
        distance_billion_usd: distance,
        note_ko: '분기말 전 비교는 거리만 표시하며 상회 판정이나 방출 신호를 내지 않습니다.'
      };
    }
    var gap = observation.value_billion_usd - exact.value_billion_usd;
    if (gap <= 0) return {
      status: 'AT_OR_BELOW_ASSUMPTION', release_status: 'NO_RELEASE_WATCH',
      target_date: exact.target_date, target_value_billion_usd: exact.value_billion_usd,
      distance_billion_usd: gap,
      note_ko: '동일 기준일의 분기말 가정과 같거나 낮습니다.'
    };
    var observedRelease = evidence.observed_tga_drawdown === true ||
      evidence.dts_net_withdrawals_observed === true ||
      evidence.verified_federal_reserve_offset === true ||
      evidence.observed_reserve_replenishment === true;
    return {
      status: 'ABOVE_ASSUMPTION_WATCH',
      release_status: observedRelease ? 'RELEASE_CONFIRMED' : 'RELEASE_EVIDENCE_PENDING',
      target_date: exact.target_date, target_value_billion_usd: exact.value_billion_usd,
      distance_billion_usd: gap,
      note_ko: observedRelease
        ? '분기말 가정 상회 뒤 TGA 감소·DTS 순인출·Fed 상쇄 중 하나가 확인됐습니다.'
        : '분기말 가정 상회는 WATCH일 뿐이며 TGA 감소·DTS 순인출·Fed 상쇄 확인이 필요합니다.'
    };
  }

  function displayModel(eventState, assessment) {
    var event = eventState ? eventState.event : null;
    var guidance = event && event.treasury_guidance;
    return {
      decision_label: DECISION_LABEL,
      title_ko: event ? yymmdd(event.event_date) + ' | ' + event.title_ko : 'TGA 공식 이벤트 대기',
      phase: eventState ? eventState.phase : 'NO_RELEVANT_EVENT',
      mechanical_ko: event
        ? '즉시 기계효과: TGA↑ · 은행 준비금↓ · Net Liquidity 프록시↓'
        : '즉시 기계효과: 관측 이벤트 없음',
      context_ko: event
        ? '계절성 해석: 사전예고된 정상 drain · 단독 위험신호 아님 · 기존 신호등 불변'
        : '계절성 해석: 공식 일정 이벤트 대기',
      treasury_ko: guidance
        ? '재무부 대응: 단기물 발행 축소 예고 · 추가 drain 완화(세금 유입 자체가 공급은 아님)'
        : '재무부 대응: 별도 공식 가이던스 없음',
      target_ko: assessment.note_ko,
      release_status: assessment.release_status
    };
  }

  function interpret(raw, context) {
    context = context || {};
    var asOf = context.as_of_date || (raw && raw.as_of_date);
    var nowDate = context.now_date || todayUtc();
    var model = validateConfig(raw, asOf, nowDate);
    if (!model) return null;
    var eventState = relevantEvent(model, asOf);
    var tga = latestTga(context.tga_series, asOf, nowDate);
    var targets = context.tga_targets;
    if (!targets && model.canonical && model.canonical.treasury_context) {
      var reference = model.canonical.treasury_context.cash_balance_reference;
      if (isObject(reference) && validDate(reference.reference_date) &&
          Number.isFinite(Number(reference.value))) {
        targets = { assumptions: [{ target_date: reference.reference_date, value: Number(reference.value) }] };
      }
    }
    var assessment = targetAssessment(
      tga.observation, targets, context.release_evidence, context.tga_series, asOf, nowDate
    );
    return {
      contract_id: CONTRACT_ID,
      as_of_date: asOf,
      decision_label: DECISION_LABEL,
      formula: 'WALCL-TGA-RRP',
      formula_override: false,
      existing_light_override: false,
      mechanical_effect: eventState ? 'NEGATIVE' : 'NOT_APPLICABLE',
      contextual_signal: eventState ? 'EXPECTED_SEASONAL_DRAIN' : 'NO_RELEVANT_EVENT',
      event: eventState ? clone(eventState.event) : null,
      event_phase: eventState ? eventState.phase : 'NO_RELEVANT_EVENT',
      tga_observation: tga.observation,
      future_observation_ignored: tga.future_ignored,
      target_assessment: assessment,
      display: displayModel(eventState, assessment)
    };
  }

  function chartMarkers(raw, fromDate, toDate, asOf, nowDate) {
    var model = validateConfig(raw, asOf, nowDate);
    if (!model || !validDate(fromDate) || !validDate(toDate) || fromDate > toDate) return [];
    return model.events.filter(function (event) {
      return event.event_date >= fromDate && event.event_date <= toDate;
    }).map(function (event) {
      return {
        date: event.event_date,
        date_label: yymmdd(event.event_date),
        label_ko: event.title_ko,
        color: '#b48cff',
        line_style: 'event_marker',
        classification: event.classification
      };
    });
  }

  return {
    CONTRACT_ID: CONTRACT_ID,
    DECISION_LABEL: DECISION_LABEL,
    validateConfig: validateConfig,
    phaseOf: phaseOf,
    relevantEvent: relevantEvent,
    targetAssessment: targetAssessment,
    interpret: interpret,
    chartMarkers: chartMarkers,
    yymmdd: yymmdd
  };
});
