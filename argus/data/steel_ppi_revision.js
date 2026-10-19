/* BLS PPI official-revision overlay — 2026-10-19.
 * Keep the frozen dashboard payload intact and replace only observations whose
 * exact BLS series code and period were reissued by the primary publisher.
 */
(function () {
  'use strict';
  if (!window.ARGUS_STEEL || !window.ARGUS_STEEL.market || !Array.isArray(window.ARGUS_STEEL.market.series)) return;
  var note = 'BLS 원기관 월간 NSA 지수. 잠정치(P). 개별 최초 발표일 미확보; 조회일을 발표일로 간주하지 않음. 같은 지표의 원기관 개정은 변경 이력에 남깁니다.';
  var base = 'https://api.bls.gov/publicAPI/v2/timeseries/data/';
  var revisions = {
    steel_scrap_ppi: {
      code: 'WPU1012', source: 'bls_WPU1012_94031a25adc6',
      values: {'2026-05': 596.470, '2026-06': 598.045, '2026-07': 589.770, '2026-08': 582.967}
    },
    steel_pipe_ppi: {
      code: 'PCU3312103312100', source: 'bls_PCU3312103312100_9c5f01a96c24',
      values: {'2026-06': 527.048, '2026-07': 530.926, '2026-08': 539.982}
    },
    carbon_pipe_ppi: {
      code: 'PCU33121033121002', source: 'bls_PCU33121033121002_133f88a79cf1',
      values: {'2026-06': 204.908, '2026-07': 206.069, '2026-08': 211.543}
    }
  };
  window.ARGUS_STEEL.market.series.forEach(function (series) {
    var revision = revisions[series.id];
    if (!revision || !Array.isArray(series.points)) return;
    series.points.forEach(function (point) {
      if (!Object.prototype.hasOwnProperty.call(revision.values, point.period)) return;
      point.value = revision.values[point.period];
      point.source_id = revision.source;
      point.note = note;
      delete point.published_at;
      point.source_url = base + revision.code;
    });
  });
}());
