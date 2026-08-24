import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '..', '..', '..');
const input = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(repo, 'data', 'tga-flow-events', 'current.json');
const require = createRequire(import.meta.url);
const api = require(path.join(repo, 'panoptes', 'tga_flow_events.js'));
const config = JSON.parse(fs.readFileSync(input, 'utf8'));
const today = new Date().toISOString().slice(0, 10);

assert.equal(config.schema_version, 'atlas-panoptes-tga-event-context-v1');
assert.equal(config.status, 'ok');
assert.equal(config.net_liquidity_contract.formula, 'WALCL - TGA - RRP');
assert.equal(config.net_liquidity_contract.formula_override_allowed, false);
assert.equal(config.release_watch_policy.quarter_end_assumption_is_cap, false);
assert.equal(
  config.release_watch_policy.reference_overshoot_alone_confirms_release,
  false
);
assert.equal(
  config.release_watch_policy.positive_liquidity_effect_before_confirmation,
  false
);
assert.ok(!('persona_lenses' in config));
assert.ok(!('lenses' in config));

const model = api.validateConfig(config, today, today);
assert.ok(model, 'public collector output must satisfy the browser contract');
assert.equal(model.contract_id, 'atlas-panoptes-tga-event-context-v1');
assert.equal(model.events.length, 5);
assert.equal(model.policy.formula_override, false);
assert.equal(model.policy.existing_light_override, false);

const september = model.events.find(event => event.event_date === '2026-09-15');
assert.ok(september);
assert.deepEqual(
  september.payer_scopes,
  ['individual_nonwithheld', 'calendar_year_corporation']
);
assert.equal(september.mechanics.tga_direction, 'up');
assert.equal(september.mechanics.bank_reserves, 'down_all_else_equal');
assert.equal(september.mechanics.net_liquidity_proxy, 'down_all_else_equal');
assert.equal(september.treasury_guidance.release_confirmation, false);

console.log('public TGA event collector frontend contract: ok');
