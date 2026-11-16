'use strict';

const chartFont = 'KaiTi,"楷体",serif';
const numberFormat = new Intl.NumberFormat('zh-CN', {maximumFractionDigits: 2});

function chartValue(value, unit) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const formatted = numberFormat.format(Number(value));
  return unit ? `${formatted} ${unit}` : formatted;
}

document.querySelectorAll('canvas[data-chart]').forEach(canvas => {
  const config = charts[canvas.dataset.chart];
  if (!config) return;
  const unit = canvas.dataset.unit || '';
  const isCurve = Boolean(config._curve);
  const isSeasonal = Boolean(config._seasonal);
  const datasets = (config.datasets || []).map((dataset, index, all) => ({
    pointHoverRadius: isCurve ? 5 : 3,
    spanGaps: true,
    ...dataset,
    borderWidth: isCurve ? (index === all.length - 1 ? 2.8 : 1.4) : (dataset.borderWidth || 1.5),
    pointRadius: isCurve ? (index === all.length - 1 ? 3.5 : 2) : 0,
  }));
  new Chart(canvas, {
    type: 'line',
    data: {labels: config.labels || [], datasets},
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      normalized: true,
      interaction: {mode: isCurve ? 'nearest' : 'index', intersect: false},
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 12,
            font: {family: chartFont, size: 10},
          },
        },
        tooltip: {
          callbacks: {
            title(items) {
              if (!items.length) return '';
              return String(items[0].label);
            },
            label(context) {
              return `${context.dataset.label || ''}: ${chartValue(context.parsed.y, unit)}`;
            },
          },
        },
      },
      scales: {
        x: {
          title: {
            display: isCurve,
            text: config._curve === 'cash-spread' ? '合约期限（价差=0M−对应期限）' : (isCurve ? '合约月份（价差=近月−对应月份）' : ''),
            font: {family: chartFont, size: 10},
          },
          ticks: {
            maxTicksLimit: isCurve ? 20 : (isSeasonal ? 12 : 8),
            maxRotation: isCurve ? 0 : 45,
            font: {family: chartFont, size: 10},
          },
          grid: {color: '#e3e3e3'},
        },
        y: {
          title: {display: Boolean(unit), text: unit, font: {family: chartFont, size: 11}},
          ticks: {
            font: {family: chartFont, size: 10},
            callback(value) { return numberFormat.format(Number(value)); },
          },
          grid: {color: '#e3e3e3'},
        },
      },
    },
  });
});
