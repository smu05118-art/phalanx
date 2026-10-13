/* ARGUS static-chart axis policy: recalculate the value axis from visible data. */
(function (root) {
  'use strict';
  function finite(v) { return typeof v === 'number' && isFinite(v); }
  function numberOf(point, axis) {
    if (Array.isArray(point)) { return finite(point[axis === 'x' ? 0 : 1]) ? point[axis === 'x' ? 0 : 1] : null; }
    if (point && typeof point === 'object') { return finite(point[axis]) ? point[axis] : (axis === 'y' && finite(point.value) ? point.value : null); }
    return finite(point) ? point : null;
  }
  function stepFor(span) {
    var raw = span / 4, power = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)), fraction = raw / power;
    return (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10) * power;
  }
  function valueAxis(chart, id, axis) {
    var horizontal = chart.options && chart.options.indexAxis === 'y';
    return axis && (axis.axis ? axis.axis === (horizontal ? 'x' : 'y') : id.charAt(0) === (horizontal ? 'x' : 'y'));
  }
  function baselineRequired(chart, axis, datasets) {
    if (axis.axisAutoZeroBaseline === true || axis.stacked) { return true; }
    var title = axis.title && axis.title.text ? String(axis.title.text) : '';
    if (/(누적 진행률|공기 경과율|R²|설명력)/.test(title)) { return true; }
    return datasets.some(function (ds) { return (ds.type || chart.config.type) === 'bar'; });
  }
  function range(values, zero) {
    var min = Math.min.apply(null, values), max = Math.max.apply(null, values), span = max - min;
    if (!span) { span = Math.abs(max) * 0.12 || 1; min -= span; max += span; }
    else { min -= span * 0.12; max += span * 0.12; }
    if (zero) { min = Math.min(0, min); max = Math.max(0, max); }
    var step = stepFor(max - min);
    return { min: Math.floor(min / step) * step, max: Math.ceil(max / step) * step };
  }
  var plugin = {
    id: 'argusAutoAxis',
    beforeUpdate: function (chart) {
      var options = chart.options || {}, scales = options.scales || {}, horizontal = options.indexAxis === 'y';
      Object.keys(scales).forEach(function (id) {
        var axis = scales[id], valueKey = horizontal ? 'x' : 'y', values = [], datasets = [];
        if (!valueAxis(chart, id, axis)) { return; }
        (chart.data.datasets || []).forEach(function (ds, index) {
          var assigned = valueKey === 'x' ? (ds.xAxisID || 'x') : (ds.yAxisID || 'y');
          if (assigned !== id || (chart.isDatasetVisible && !chart.isDatasetVisible(index))) { return; }
          datasets.push(ds);
          (ds.data || []).forEach(function (point) { var value = numberOf(point, valueKey); if (value !== null) { values.push(value); } });
        });
        if (!values.length) { return; }
        var zero = baselineRequired(chart, axis, datasets), domain = range(values, zero);
        axis.min = domain.min;
        axis.max = domain.max;
        axis.beginAtZero = zero;
        chart.$argusAutoAxis = chart.$argusAutoAxis || {};
        chart.$argusAutoAxis[id] = domain;
      });
    }
  };
  root.ArgusAutoAxis = { range: range, baselineRequired: baselineRequired, plugin: plugin };
  if (root.Chart && root.Chart.register) { root.Chart.register(plugin); }
  if (typeof module !== 'undefined' && module.exports) { module.exports = root.ArgusAutoAxis; }
}(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this)));
