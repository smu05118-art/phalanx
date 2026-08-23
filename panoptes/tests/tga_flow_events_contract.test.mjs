import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const panoptes = path.resolve(here, '..');
const repo = path.resolve(panoptes, '..');
const require = createRequire(import.meta.url);
const api = require(path.join(panoptes, 'tga_flow_events.js'));
const bridge = require(path.join(panoptes, 'tga_flow_events_bridge.js'));
const config = JSON.parse(
  fs.readFileSync(path.join(repo, 'data', 'tga-flow-events', 'current.json'), 'utf8')
);
const clone = value => JSON.parse(JSON.stringify(value));

assert.equal(config.schema_version, 'atlas-panoptes-tga-event-context-v1');
assert.equal(config.status, 'ok');
assert.equal(config.signal_label, '판단 보조용 자동등급');
assert.equal(config.net_liquidity_contract.formula, 'WALCL - TGA - RRP');
assert.equal(config.net_liquidity_contract.formula_override_allowed, false);
assert.equal(
  config.net_liquidity_contract.scheduled_event_policy,
  'contextualize_seasonality_without_reversing_formula_sign'
);
assert.equal(config.release_watch_policy.quarter_end_assumption_is_cap, false);
assert.equal(config.release_watch_policy.reference_overshoot_alone_confirms_release, false);
assert.equal(config.release_watch_policy.positive_liquidity_effect_before_confirmation, false);
assert.equal(config.treasury_context.cash_balance_reference.semantic, 'treasury_assumption_not_cap');
assert.equal(config.events.length, 5);
assert.ok(!('persona_lenses' in config), 'public dashboard export must not contain private persona evidence');

const model = api.validateConfig(config, '2026-08-23', '2026-08-23');
assert.ok(model, 'official event context must validate');
assert.equal(model.contract_id, 'atlas-panoptes-tga-event-context-v1');
assert.equal(model.policy.net_liquidity_formula, 'WALCL-TGA-RRP');
assert.equal(model.policy.formula_override, false);
assert.equal(model.policy.existing_light_override, false);
assert.equal(model.policy.quarter_end_assumption_role, 'reference_not_cap');
assert.equal(model.policy.release_confirmation_policy, 'observed_outflow_required');
const sep = model.events.find(row => row.event_date === '2026-09-15');
assert.ok(sep);
assert.deepEqual(sep.payer_scopes, ['individual_nonwithheld', 'calendar_year_corporation']);
assert.equal(sep.mechanics.tga_direction, 'up');
assert.equal(sep.mechanics.bank_reserves, 'down_all_else_equal');
assert.equal(sep.mechanics.net_liquidity_proxy, 'down_all_else_equal');
assert.equal(sep.classification, 'scheduled_seasonal_drain');
assert.equal(sep.automatic_risk_off, false);
assert.equal(sep.treasury_guidance.effect, 'additional_drain_mitigation');
assert.equal(sep.treasury_guidance.release_confirmation, false);

const interpreted = api.interpret(config, {
  as_of_date: '2026-08-23',
  now_date: '2026-08-23',
  tga_series: { '2026-08-12': 910, '2026-08-19': 953.61 },
  tga_targets: {
    assumptions: [
      { target_date: '2026-09-30', value: 950 },
      { target_date: '2026-12-31', value: 850 }
    ]
  }
});
assert.ok(interpreted);
assert.equal(interpreted.event.event_date, '2026-09-15');
assert.equal(interpreted.event_phase, 'UPCOMING');
assert.equal(interpreted.mechanical_effect, 'NEGATIVE');
assert.equal(interpreted.contextual_signal, 'EXPECTED_SEASONAL_DRAIN');
assert.equal(interpreted.formula, 'WALCL-TGA-RRP');
assert.equal(interpreted.formula_override, false);
assert.equal(interpreted.existing_light_override, false);
assert.equal(interpreted.target_assessment.status, 'DISTANCE_ONLY');
assert.equal(interpreted.target_assessment.release_status, 'NOT_EVALUATED');
assert.match(interpreted.display.mechanical_ko, /TGA↑/);
assert.match(interpreted.display.context_ko, /단독 위험신호 아님/);
assert.match(interpreted.display.treasury_ko, /추가 drain 완화/);
assert.match(interpreted.display.target_ko, /상회 판정이나 방출 신호를 내지 않습니다/);

const onEvent = api.interpret(config, {
  as_of_date: '2026-06-15',
  now_date: '2026-08-23',
  tga_series: { '2026-06-12': 700 }
});
assert.equal(onEvent.event.event_date, '2026-06-15');
assert.equal(onEvent.event_phase, 'COLLECTION_WINDOW_OPEN');
const afterEvent = api.interpret(config, {
  as_of_date: '2026-06-25',
  now_date: '2026-08-23',
  tga_series: { '2026-06-24': 730 }
});
assert.equal(afterEvent.event.event_date, '2026-06-15');
assert.equal(afterEvent.event_phase, 'POST_EVENT_OBSERVATION');

const exactWatch = api.interpret(config, {
  as_of_date: '2026-09-30',
  now_date: '2026-09-30',
  tga_series: { '2026-09-30': 975 },
  tga_targets: { assumptions: [{ target_date: '2026-09-30', value: 950 }] }
});
assert.equal(exactWatch.target_assessment.status, 'ABOVE_ASSUMPTION_WATCH');
assert.equal(exactWatch.target_assessment.release_status, 'RELEASE_EVIDENCE_PENDING');
assert.equal(exactWatch.target_assessment.distance_billion_usd, 25);
assert.match(exactWatch.target_assessment.note_ko, /WATCH일 뿐/);

const confirmed = api.interpret(config, {
  as_of_date: '2026-09-30',
  now_date: '2026-09-30',
  tga_series: { '2026-09-30': 975 },
  tga_targets: { assumptions: [{ target_date: '2026-09-30', value: 950 }] },
  release_evidence: { observed_tga_drawdown: true }
});
assert.equal(confirmed.target_assessment.release_status, 'RELEASE_CONFIRMED');

const confirmedBySubsequentObservation = api.interpret(config, {
  as_of_date: '2026-10-07',
  now_date: '2026-10-07',
  tga_series: { '2026-09-30': 975, '2026-10-07': 930 },
  tga_targets: {
    assumptions: [
      { target_date: '2026-09-30', value: 950 },
      { target_date: '2026-12-31', value: 850 }
    ]
  }
});
assert.equal(confirmedBySubsequentObservation.target_assessment.status, 'ABOVE_ASSUMPTION_WATCH');
assert.equal(confirmedBySubsequentObservation.target_assessment.release_status, 'RELEASE_CONFIRMED');
assert.equal(confirmedBySubsequentObservation.target_assessment.target_date, '2026-09-30');

const pendingAfterTarget = api.interpret(config, {
  as_of_date: '2026-10-07',
  now_date: '2026-10-07',
  tga_series: { '2026-09-30': 975, '2026-10-07': 980 },
  tga_targets: { assumptions: [{ target_date: '2026-09-30', value: 950 }] }
});
assert.equal(pendingAfterTarget.target_assessment.status, 'ABOVE_ASSUMPTION_WATCH');
assert.equal(pendingAfterTarget.target_assessment.release_status, 'RELEASE_EVIDENCE_PENDING');

const canonicalReferenceFallback = api.interpret(config, {
  as_of_date: '2026-08-23',
  now_date: '2026-08-23',
  tga_series: { '2026-08-19': 953.61 }
});
assert.equal(canonicalReferenceFallback.target_assessment.status, 'DISTANCE_ONLY');
assert.equal(canonicalReferenceFallback.target_assessment.target_date, '2026-09-30');

const below = api.interpret(config, {
  as_of_date: '2026-09-30',
  now_date: '2026-09-30',
  tga_series: { '2026-09-30': 940 },
  tga_targets: { assumptions: [{ target_date: '2026-09-30', value: 950 }] }
});
assert.equal(below.target_assessment.status, 'AT_OR_BELOW_ASSUMPTION');
assert.equal(below.target_assessment.release_status, 'NO_RELEASE_WATCH');

const ignoresFutureObservation = api.interpret(config, {
  as_of_date: '2026-08-23',
  now_date: '2026-08-23',
  tga_series: { '2026-08-19': 953.61, '2026-08-24': 999 }
});
assert.equal(ignoresFutureObservation.tga_observation.observation_date, '2026-08-19');
assert.equal(ignoresFutureObservation.future_observation_ignored, true);
assert.equal(
  api.validateConfig(config, '2026-08-24', '2026-08-23'),
  null,
  'future-dated liquidity snapshots must fail closed'
);
assert.equal(api.validateConfig(config, '2027-01-16', '2027-01-16'), null, 'expired calendar fails closed');

const bad = mutate => {
  const value = clone(config);
  mutate(value);
  return api.validateConfig(value, '2026-08-23', '2026-08-23');
};
assert.equal(bad(v => { v.net_liquidity_contract.formula_override_allowed = true; }), null);
assert.equal(bad(v => { v.net_liquidity_contract.tga_increase_mechanical_effect = 'positive'; }), null);
assert.equal(bad(v => { v.release_watch_policy.quarter_end_assumption_is_cap = true; }), null);
assert.equal(bad(v => { v.release_watch_policy.reference_overshoot_alone_confirms_release = true; }), null);
assert.equal(bad(v => { v.release_watch_policy.positive_liquidity_effect_before_confirmation = true; }), null);
assert.equal(bad(v => { v.sources[0].source_url = 'https://example.com/form.pdf'; }), null);
assert.equal(bad(v => { v.sources[0].content_sha256 = 'bad'; }), null);
assert.equal(bad(v => { v.events[2].cash_flow_context.net_liquidity_proxy_effect = 'injection'; }), null);
assert.equal(
  bad(v => { v.events[2].interpretation.positive_effect_allowed_without_observed_offset_or_drawdown = true; }),
  null
);
assert.equal(bad(v => { v.events[2].event_date = '2026-99-14'; }), null);
assert.equal(bad(v => { v.events[2].payer_scopes[0].source_ids = ['unknown']; }), null);

const markers = api.chartMarkers(
  config, '2026-08-01', '2026-10-01', '2026-08-23', '2026-08-23'
);
assert.equal(markers.length, 1);
assert.equal(markers[0].date, '2026-09-15');
assert.equal(markers[0].date_label, '260915');
assert.equal(markers[0].line_style, 'event_marker');

const html = bridge.renderContextHtml(interpreted, model);
assert.match(html, /TGA 공식 이벤트 컨텍스트/);
assert.match(html, /즉시 기계효과/);
assert.match(html, /기존 신호등 불변/);
assert.match(html, /판단 보조용 자동등급/);
assert.match(html, /260915/);
assert.match(html, /Federal Reserve/);
assert.match(html, /Treasury/);
assert.doesNotMatch(html, /persona_lenses/);
const inputs = bridge.contextInputs({
  tga_targets: { assumptions: [] },
  sections: { funding: { series: { TGA: { '2026-08-19': 953.61 } }, references: {} } }
});
assert.equal(inputs.tga_series['2026-08-19'], 953.61);
assert.deepEqual(inputs.tga_targets, { assumptions: [] });
assert.match(bridge.qualityBlockHtml('2026-08-24', '2026-08-23'), /입력 품질 차단/);
assert.match(bridge.qualityBlockHtml('<script>', '2026-08-23'), /&lt;script&gt;/);

console.log('tga flow event contract: ok');
