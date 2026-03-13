"""
WaniKani Progress Dashboard — web UI showing progress trends over time.

Reads snapshot history from data/wanikani_history.json (written by wanikani_tracker.py)
and renders interactive charts via Chart.js.

Usage:
  python3 wanikani_dashboard.py              # Start on port 8082
  python3 wanikani_dashboard.py --port 9000   # Custom port
"""

import argparse
import json
import os
import subprocess

from flask import Flask, jsonify

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

HISTORY_PATH = os.path.join(PROJECT_ROOT, "data", "wanikani_history.json")

app = Flask(__name__)

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WaniKani Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: "Hiragino Sans", "Yu Gothic", "Noto Sans JP", -apple-system, sans-serif;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: #e0e0e0;
    min-height: 100vh;
    padding: 20px;
  }
  h1 {
    text-align: center;
    font-size: 1.8em;
    margin-bottom: 8px;
    color: #fff;
  }
  .subtitle {
    text-align: center;
    color: #888;
    margin-bottom: 24px;
    font-size: 0.9em;
  }
  .summary-bar {
    display: flex;
    justify-content: center;
    gap: 32px;
    margin-bottom: 28px;
    flex-wrap: wrap;
  }
  .stat-card {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 16px 28px;
    text-align: center;
    min-width: 140px;
  }
  .stat-card .value {
    font-size: 1.8em;
    font-weight: bold;
    color: #fff;
  }
  .stat-card .label {
    font-size: 0.8em;
    color: #999;
    margin-top: 4px;
  }
  .stat-card .value.accent { color: #e94560; }
  .stat-card .value.green { color: #4caf50; }
  .stat-card .value.cyan { color: #00bcd4; }
  .stat-card .value.yellow { color: #ffc107; }
  .chart-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    max-width: 1400px;
    margin: 0 auto;
  }
  .chart-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 20px;
  }
  .chart-card h3 {
    font-size: 1em;
    color: #ccc;
    margin-bottom: 12px;
  }
  .chart-card canvas { width: 100% !important; }
  .sessions-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 18px;
    margin-top: 10px;
    padding: 8px 4px 0;
    border-top: 1px solid rgba(255,255,255,0.06);
  }
  .sessions-legend .leg-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #ccc;
  }
  .sessions-legend .leg-line {
    width: 20px;
    height: 0;
    border-top: 2px solid;
    display: inline-block;
  }
  .sessions-legend .leg-line.dashed {
    border-top-style: dashed;
  }
  .sessions-legend .leg-swatch {
    width: 10px;
    height: 10px;
    border-radius: 2px;
    display: inline-block;
  }
  .level-up-panel {
    max-width: 1400px;
    margin: 0 auto 20px auto;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 20px 28px;
    display: none;
  }
  .level-up-panel h3 {
    font-size: 1.1em;
    color: #fff;
    margin-bottom: 12px;
  }
  .level-up-panel .lu-row {
    display: flex;
    align-items: center;
    gap: 32px;
    flex-wrap: wrap;
  }
  .level-up-panel .lu-progress {
    flex: 1;
    min-width: 280px;
  }
  .lu-bar-outer {
    background: rgba(255,255,255,0.08);
    border-radius: 8px;
    height: 28px;
    position: relative;
    overflow: hidden;
    margin: 8px 0;
  }
  .lu-bar-inner {
    height: 100%;
    border-radius: 8px;
    background: linear-gradient(90deg, #4caf50, #00bcd4);
    transition: width 0.5s;
  }
  .lu-bar-label {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 0.85em;
    font-weight: bold;
    color: #fff;
    text-shadow: 0 1px 3px rgba(0,0,0,0.5);
  }
  .lu-estimates {
    display: flex;
    gap: 24px;
    margin-top: 10px;
    flex-wrap: wrap;
  }
  .lu-est {
    text-align: center;
    min-width: 120px;
  }
  .lu-est .est-time {
    font-size: 1.4em;
    font-weight: bold;
  }
  .lu-est .est-label {
    font-size: 0.75em;
    color: #999;
    margin-top: 2px;
  }
  .lu-est .est-date {
    font-size: 0.8em;
    color: #bbb;
  }
  .lu-stages {
    min-width: 180px;
  }
  .lu-stages canvas {
    max-width: 180px;
    max-height: 180px;
  }
  .lu-schedule {
    margin-top: 16px;
    width: 100%;
  }
  .lu-schedule h4 {
    font-size: 0.9em;
    color: #bbb;
    margin-bottom: 8px;
  }
  .lu-schedule table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85em;
  }
  .lu-schedule th {
    text-align: left;
    color: #999;
    font-weight: normal;
    padding: 6px 10px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
  }
  .lu-schedule td {
    padding: 6px 10px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    color: #ddd;
  }
  .lu-schedule tr:last-child td { border-bottom: none; }
  .lu-schedule .today { color: #fff; font-weight: bold; }
  .lu-schedule .stage-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.8em;
    margin: 1px 3px;
  }
  .empty-state {
    text-align: center;
    padding: 80px 20px;
    color: #888;
  }
  .empty-state h2 { color: #ccc; margin-bottom: 12px; }
  .empty-state code {
    background: rgba(255,255,255,0.1);
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 0.95em;
  }
  .tab-bar {
    display: flex;
    justify-content: center;
    gap: 8px;
    margin-bottom: 24px;
  }
  .tab {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    color: #999;
    padding: 10px 28px;
    border-radius: 24px;
    font-size: 0.95em;
    cursor: pointer;
    transition: all 0.2s;
  }
  .tab:hover { background: rgba(255,255,255,0.1); color: #ccc; }
  .tab.active {
    background: rgba(233,69,96,0.15);
    border-color: #e94560;
    color: #fff;
    font-weight: bold;
  }
  .cohort-no-data {
    text-align: center;
    padding: 40px 20px;
    color: #888;
  }
  .cohort-no-data code {
    background: rgba(255,255,255,0.1);
    padding: 4px 10px;
    border-radius: 6px;
  }
  .streak-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 20px;
    grid-column: 1 / -1;
  }
  .streak-card h3 {
    font-size: 1em;
    color: #ccc;
    margin-bottom: 16px;
  }
  .streak-stats {
    display: flex;
    gap: 40px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }
  .streak-stat {
    text-align: center;
  }
  .streak-stat .big {
    font-size: 2.4em;
    font-weight: bold;
    color: #fff;
  }
  .streak-stat .lbl {
    font-size: 0.8em;
    color: #999;
    margin-top: 4px;
  }
  .gauge-outer {
    background: rgba(255,255,255,0.08);
    border-radius: 8px;
    height: 28px;
    position: relative;
    overflow: hidden;
    margin: 8px 0;
  }
  .gauge-inner {
    height: 100%;
    border-radius: 8px;
    background: linear-gradient(90deg, #e94560, #ffc107, #4caf50);
    transition: width 0.5s;
  }
  .gauge-markers {
    display: flex;
    justify-content: space-between;
    font-size: 0.75em;
    color: #888;
    margin-top: 4px;
  }
  .refresh-btn {
    background: rgba(233,69,96,0.15);
    border: 1px solid #e94560;
    color: #fff;
    padding: 8px 20px;
    border-radius: 20px;
    font-size: 0.85em;
    cursor: pointer;
    transition: all 0.2s;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .refresh-btn:hover { background: rgba(233,69,96,0.3); }
  .refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .refresh-btn .spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .header-row {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 16px;
    margin-bottom: 8px;
  }
  @media (max-width: 900px) {
    .chart-grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="header-row">
  <h1>WaniKani Progress Dashboard</h1>
  <button class="refresh-btn" id="refresh-btn" onclick="refreshData()">Pull Fresh Data</button>
</div>
<div class="subtitle" id="subtitle"></div>

<div class="tab-bar" id="tab-bar" style="display:none;">
  <button class="tab active" data-view="progress" onclick="switchView('progress')">Progress</button>
  <button class="tab" data-view="cohort" onclick="switchView('cohort')">Cohort Comparison</button>
</div>

<div id="view-progress">
<div class="summary-bar" id="summary-bar"></div>

<div class="level-up-panel" id="level-up-panel">
  <h3 id="lu-title"></h3>
  <div class="lu-row">
    <div class="lu-progress">
      <div style="color:#bbb;font-size:0.9em;" id="lu-subtitle"></div>
      <div class="lu-bar-outer">
        <div class="lu-bar-inner" id="lu-bar"></div>
        <div class="lu-bar-label" id="lu-bar-label"></div>
      </div>
      <div class="lu-estimates" id="lu-estimates"></div>
    </div>
    <div class="lu-stages">
      <canvas id="luStageChart"></canvas>
    </div>
  </div>
  <div class="lu-schedule" id="lu-schedule" style="display:none;"></div>
</div>

<div id="empty-state" class="empty-state" style="display:none;">
  <h2>No history data yet</h2>
  <p>Run the tracker to start recording snapshots:</p>
  <p style="margin-top:12px;"><code>python3 wanikani_tracker.py</code></p>
  <p style="margin-top:8px; color:#666;">Each run saves a daily snapshot. Come back after a few runs to see trends.</p>
</div>

<div class="chart-grid" id="chart-grid">
  <div class="chart-card"><h3>Level Progress</h3><canvas id="levelChart"></canvas></div>
  <div class="chart-card"><h3>Items Learned (Guru+)</h3><canvas id="kanjiChart"></canvas></div>
  <div class="chart-card"><h3>Kanji SRS Distribution</h3><canvas id="srsChart"></canvas></div>
  <div class="chart-card"><h3>Accuracy Trend (solid=kanji, dashed=vocab)</h3><canvas id="accuracyChart"></canvas></div>
  <div class="chart-card"><h3>JLPT Kanji Coverage %</h3><canvas id="jlptChart"></canvas></div>
  <div class="chart-card"><h3>N2 / N1 Prediction Timeline</h3><canvas id="predictionChart"></canvas></div>
</div>
</div><!-- end view-progress -->

<div id="view-cohort" style="display:none;">
<div class="chart-grid" id="cohort-grid">
  <div class="chart-card"><h3>Pace: Days per Level</h3><canvas id="cohortPaceChart"></canvas></div>
  <div class="chart-card"><h3>Accuracy vs Community</h3><canvas id="cohortAccuracyChart"></canvas></div>
  <div class="chart-card"><h3>Items Learned Trajectory</h3><canvas id="cohortItemsChart"></canvas></div>
  <div class="chart-card"><h3>Sessions per Day (Last 30 Days)</h3><canvas id="cohortSessionsChart"></canvas><div id="sessionsLegend" class="sessions-legend"></div></div>
  <div class="streak-card" id="streak-card">
    <h3>Study Streaks</h3>
    <div class="streak-stats" id="streak-stats"></div>
    <div style="color:#bbb;font-size:0.85em;margin-bottom:6px;">Current Streak vs Community</div>
    <div class="gauge-outer"><div class="gauge-inner" id="streak-gauge"></div></div>
    <div class="gauge-markers">
      <span>0</span><span>Casual (7d)</span><span>Avg (15d)</span><span>Good (30d)</span><span>Dedicated (60d+)</span>
    </div>
  </div>
</div>
<div class="cohort-no-data" id="cohort-no-data" style="display:none;">
  <h2>No cohort data yet</h2>
  <p>Run the tracker to collect pace and session data:</p>
  <p style="margin-top:12px;"><code>python3 wanikani_tracker.py</code></p>
</div>
</div><!-- end view-cohort -->

<script>
const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: true,
  plugins: {
    legend: { labels: { color: '#ccc', font: { size: 11 } } },
  },
  scales: {
    x: {
      type: 'time',
      time: { unit: 'day', tooltipFormat: 'MMM d, yyyy' },
      ticks: { color: '#888' },
      grid: { color: 'rgba(255,255,255,0.05)' },
    },
    y: {
      ticks: { color: '#888' },
      grid: { color: 'rgba(255,255,255,0.05)' },
    },
  },
};

function deepMerge(target, source) {
  const out = { ...target };
  for (const key of Object.keys(source)) {
    if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
      out[key] = deepMerge(out[key] || {}, source[key]);
    } else {
      out[key] = source[key];
    }
  }
  return out;
}

function makeOpts(overrides = {}) {
  return deepMerge(CHART_DEFAULTS, overrides);
}

// --- Tab switching ---
function switchView(view) {
  document.getElementById('view-progress').style.display = view === 'progress' ? '' : 'none';
  document.getElementById('view-cohort').style.display = view === 'cohort' ? '' : 'none';
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.view === view);
  });
}

// --- Cohort benchmarks (community averages from WK forums) ---
const COHORT = {
  pace: [
    { days: 7, label: 'Speed Runner', color: '#e94560' },
    { days: 10, label: 'Fast', color: '#ff9800' },
    { days: 14, label: 'Median', color: '#ffc107' },
    { days: 20, label: 'Steady', color: '#00bcd4' },
    { days: 30, label: 'Casual', color: '#4caf50' },
  ],
  accuracy: {
    meaning: { top10: 97, median: 92, bottom25: 85 },
    reading: { top10: 90, median: 82, bottom25: 72 },
    overall: { top10: 93, median: 87, bottom25: 78 },
  },
  sessions: { high: 3.0, median: 1.8, low: 1.0 },
  streaks: { dedicated: 60, good: 30, average: 15, casual: 7 },
  kanji_per_level: 33,
};

// --- Cohort chart instances (for cleanup) ---
let cohortCharts = [];

function loadCohortView(snaps) {
  // Destroy previous chart instances
  cohortCharts.forEach(c => c.destroy());
  cohortCharts = [];

  const latest = snaps[snaps.length - 1];
  const pace = latest.pace;
  const acc = latest.accuracy;
  const ss = latest.sessions_streaks;

  if (!pace && !ss) {
    document.getElementById('cohort-no-data').style.display = 'block';
    document.getElementById('cohort-grid').style.display = 'none';
    return;
  }

  // 1. Pace chart — horizontal bar: user vs cohort benchmarks
  const paceCtx = document.getElementById('cohortPaceChart');
  const userAvg = pace && pace.avg ? pace.avg : null;
  const paceLabels = COHORT.pace.map(p => p.label);
  const paceData = COHORT.pace.map(p => p.days);
  const paceColors = COHORT.pace.map(p => p.color + '66');
  const paceBorders = COHORT.pace.map(p => p.color);

  if (userAvg !== null) {
    paceLabels.unshift('You');
    paceData.unshift(userAvg);
    paceColors.unshift('rgba(255,255,255,0.25)');
    paceBorders.unshift('#fff');
  }

  cohortCharts.push(new Chart(paceCtx, {
    type: 'bar',
    data: {
      labels: paceLabels,
      datasets: [{
        label: 'Days / Level',
        data: paceData,
        backgroundColor: paceColors,
        borderColor: paceBorders,
        borderWidth: 2,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: {
        legend: { display: false },
      },
      scales: {
        x: { ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' }, title: { display: true, text: 'Days', color: '#888' } },
        y: { ticks: { color: '#ccc', font: { weight: (ctx) => ctx.tick.label === 'You' ? 'bold' : 'normal' } }, grid: { display: false } },
      },
    },
  }));

  // 2. Accuracy vs Community — grouped bar with annotation ranges
  const accCtx = document.getElementById('cohortAccuracyChart');
  const accCategories = ['Meaning', 'Reading', 'Overall'];
  const accKeys = ['meaning', 'reading', 'overall'];
  const userAccValues = [acc.meaning_pct, acc.reading_pct, acc.overall_pct];
  const medianValues = accKeys.map(k => COHORT.accuracy[k].median);

  function accColor(val, key) {
    if (val >= COHORT.accuracy[key].median) return '#4caf50';
    if (val >= COHORT.accuracy[key].bottom25) return '#ffc107';
    return '#e94560';
  }

  cohortCharts.push(new Chart(accCtx, {
    type: 'bar',
    data: {
      labels: accCategories,
      datasets: [
        {
          label: 'You',
          data: userAccValues,
          backgroundColor: userAccValues.map((v, i) => accColor(v, accKeys[i]) + '99'),
          borderColor: userAccValues.map((v, i) => accColor(v, accKeys[i])),
          borderWidth: 2,
        },
        {
          label: 'Community Median',
          data: medianValues,
          backgroundColor: 'rgba(255,255,255,0.08)',
          borderColor: 'rgba(255,255,255,0.4)',
          borderWidth: 2,
          borderDash: [4, 4],
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: '#ccc', font: { size: 11 } } },
        annotation: {
          annotations: accKeys.reduce((obj, key, i) => {
            obj['range_' + key] = {
              type: 'box',
              xMin: i - 0.4,
              xMax: i + 0.4,
              yMin: COHORT.accuracy[key].bottom25,
              yMax: COHORT.accuracy[key].top10,
              backgroundColor: 'rgba(255,255,255,0.03)',
              borderColor: 'rgba(255,255,255,0.08)',
              borderWidth: 1,
            };
            return obj;
          }, {}),
        },
      },
      scales: {
        y: { min: 60, max: 100, ticks: { color: '#888', callback: v => v + '%' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        x: { ticks: { color: '#ccc' }, grid: { display: false } },
      },
    },
  }));

  // 3. Items Learned Trajectory — user line vs pace reference lines
  const itemsCtx = document.getElementById('cohortItemsChart');
  const daysStudied = latest.days_studied || 1;
  const kanjiLearned = latest.kanji_learned || 0;
  const vocabLearned = latest.vocab_learned || 0;

  // Build user trajectory from history
  const userKanjiPts = snaps.filter(s => s.days_studied > 0).map(s => ({ x: s.days_studied, y: s.kanji_learned }));
  const userVocabPts = snaps.filter(s => s.days_studied > 0 && s.vocab_learned).map(s => ({ x: s.days_studied, y: s.vocab_learned }));

  // Reference lines: kanji expected at different paces over time range
  const maxDays = Math.max(daysStudied * 1.3, 60);
  const refPaces = [
    { daysPerLevel: 7, label: 'Fast (7d/lv)', color: '#e9456066', dash: [6, 3] },
    { daysPerLevel: 14, label: 'Median (14d/lv)', color: '#ffc10766', dash: [6, 3] },
    { daysPerLevel: 25, label: 'Casual (25d/lv)', color: '#4caf5066', dash: [6, 3] },
  ];
  const refDatasets = refPaces.map(rp => {
    const pts = [];
    for (let d = 0; d <= maxDays; d += 5) {
      const levels = d / rp.daysPerLevel;
      pts.push({ x: d, y: Math.round(levels * COHORT.kanji_per_level) });
    }
    return {
      label: rp.label,
      data: pts,
      borderColor: rp.color,
      borderDash: rp.dash,
      pointRadius: 0,
      fill: false,
      tension: 0.3,
    };
  });

  cohortCharts.push(new Chart(itemsCtx, {
    type: 'line',
    data: {
      datasets: [
        {
          label: 'Your Kanji',
          data: userKanjiPts,
          borderColor: '#00bcd4',
          backgroundColor: 'rgba(0,188,212,0.1)',
          fill: true,
          tension: 0.3,
          pointRadius: 3,
        },
        {
          label: 'Your Vocab',
          data: userVocabPts,
          borderColor: '#ab47bc',
          backgroundColor: 'rgba(171,71,188,0.05)',
          fill: false,
          tension: 0.3,
          pointRadius: 3,
          borderDash: [4, 2],
        },
        ...refDatasets,
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: '#ccc', font: { size: 11 } } },
      },
      scales: {
        x: { type: 'linear', title: { display: true, text: 'Days Studied', color: '#888' }, ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { min: 0, title: { display: true, text: 'Items Learned', color: '#888' }, ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
      },
    },
  }));

  // 4. Sessions per Day chart (last 30 days)
  const sessCtx = document.getElementById('cohortSessionsChart');
  if (ss && ss.daily_sessions && Object.keys(ss.daily_sessions).length > 0) {
    const today = new Date();
    const sessLabels = [];
    const sessData = [];
    for (let i = 29; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const ds = d.toISOString().slice(0, 10);
      sessLabels.push(ds);
      sessData.push(ss.daily_sessions[ds] || 0);
    }
    const userAvgSess = ss.sessions_per_day_avg || 0;

    cohortCharts.push(new Chart(sessCtx, {
      type: 'bar',
      data: {
        labels: sessLabels,
        datasets: [
          {
            label: 'Sessions',
            data: sessData,
            backgroundColor: sessData.map(v =>
              v >= COHORT.sessions.high ? '#4caf5099' :
              v >= COHORT.sessions.median ? '#00bcd499' :
              v > 0 ? '#ffc10799' : 'rgba(255,255,255,0.05)'
            ),
            borderRadius: 3,
            order: 1,
          },
          {
            label: 'Your Avg',
            type: 'line',
            data: sessLabels.map(() => userAvgSess),
            borderColor: '#ffffffaa',
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
            order: 0,
          },
          {
            label: 'Median',
            type: 'line',
            data: sessLabels.map(() => COHORT.sessions.median),
            borderColor: '#ffc107aa',
            borderWidth: 2,
            borderDash: [6, 3],
            pointRadius: 0,
            fill: false,
            order: 0,
          },
          {
            label: 'High',
            type: 'line',
            data: sessLabels.map(() => COHORT.sessions.high),
            borderColor: '#4caf5088',
            borderWidth: 1,
            borderDash: [4, 4],
            pointRadius: 0,
            fill: false,
            order: 0,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
        },
        scales: {
          x: { type: 'time', time: { unit: 'day', tooltipFormat: 'MMM d' }, ticks: { color: '#888', maxRotation: 45 }, grid: { display: false } },
          y: { min: 0, ticks: { color: '#888', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.05)' } },
        },
      },
    }));

    // Build HTML legend
    document.getElementById('sessionsLegend').innerHTML =
      '<span class="leg-item"><span class="leg-line" style="border-color:#fff"></span> Your Avg (' + userAvgSess.toFixed(1) + ')</span>' +
      '<span class="leg-item"><span class="leg-line dashed" style="border-color:#ffc107"></span> User Median (' + COHORT.sessions.median + ')</span>' +
      '<span class="leg-item"><span class="leg-line dashed" style="border-color:#4caf50"></span> User High (' + COHORT.sessions.high + ')</span>';
  } else {
    sessCtx.parentElement.innerHTML = '<h3>Sessions per Day</h3><div class="cohort-no-data" style="padding:20px;"><p>No session data. Run <code>python3 wanikani_tracker.py</code> to collect.</p></div>';
  }

  // 5. Streaks display
  const streakStats = document.getElementById('streak-stats');
  const streakGauge = document.getElementById('streak-gauge');
  if (ss) {
    const current = ss.current_streak || 0;
    const longest = ss.longest_streak || 0;
    const reviewDays = ss.total_review_days || 0;
    const recentSess = ss.sessions_per_day_recent_7d || 0;

    streakStats.innerHTML = `
      <div class="streak-stat"><div class="big" style="color:#e94560">${current}</div><div class="lbl">Current Streak (days)</div></div>
      <div class="streak-stat"><div class="big" style="color:#ffc107">${longest}</div><div class="lbl">Longest Streak</div></div>
      <div class="streak-stat"><div class="big" style="color:#00bcd4">${reviewDays}</div><div class="lbl">Total Review Days</div></div>
      <div class="streak-stat"><div class="big" style="color:#ab47bc">${recentSess.toFixed(1)}</div><div class="lbl">Sessions/Day (7d avg)</div></div>
    `;

    // Gauge: map current streak to 0-100% where 60 = 100%
    const gaugePct = Math.min(current / COHORT.streaks.dedicated * 100, 100);
    streakGauge.style.width = gaugePct + '%';
  } else {
    document.getElementById('streak-card').innerHTML = '<h3>Study Streaks</h3><div class="cohort-no-data" style="padding:20px;"><p>No streak data. Run <code>python3 wanikani_tracker.py</code> to collect.</p></div>';
  }
}

async function loadDashboard() {
  const resp = await fetch('/api/history');
  const data = await resp.json();
  const snaps = data.snapshots || [];

  if (snaps.length === 0) {
    document.getElementById('empty-state').style.display = 'block';
    document.getElementById('chart-grid').style.display = 'none';
    document.getElementById('summary-bar').style.display = 'none';
    return;
  }

  document.getElementById('tab-bar').style.display = 'flex';

  const latest = snaps[snaps.length - 1];
  const dates = snaps.map(s => s.date);

  // Summary bar
  document.getElementById('subtitle').textContent =
    `${snaps.length} snapshot${snaps.length > 1 ? 's' : ''} recorded | Latest: ${latest.date}`;

  const summaryHTML = `
    <div class="stat-card"><div class="value accent">Lv ${latest.level}</div><div class="label">Current Level</div></div>
    <div class="stat-card"><div class="value cyan">${latest.kanji_learned}</div><div class="label">Kanji Learned</div></div>
    <div class="stat-card"><div class="value" style="color:#ab47bc">${latest.vocab_learned || 0}</div><div class="label">Vocab Learned</div></div>
    <div class="stat-card"><div class="value green">${latest.accuracy.overall_pct.toFixed(1)}%</div><div class="label">Overall Accuracy</div></div>
    <div class="stat-card"><div class="value yellow">${latest.days_studied}</div><div class="label">Days Studied</div></div>
  `;
  document.getElementById('summary-bar').innerHTML = summaryHTML;

  // Level-Up Estimate Panel
  const lu = latest.level_up;
  if (lu && lu.status === 'in_progress') {
    const panel = document.getElementById('level-up-panel');
    panel.style.display = 'block';
    document.getElementById('lu-title').textContent =
      `Level ${latest.level} → ${latest.level + 1}  ⏱  Time to Level Up`;
    const pct = (lu.already_guru / lu.guru_needed * 100).toFixed(1);
    document.getElementById('lu-subtitle').textContent =
      `${lu.still_needed} more kanji need Guru` +
      (lu.not_started > 0 ? `  (${lu.not_started} not yet in lessons)` : '');
    document.getElementById('lu-bar').style.width = pct + '%';
    document.getElementById('lu-bar-label').textContent =
      `${lu.already_guru} / ${lu.guru_needed} at Guru+  (${pct}%)`;

    function fmtHours(h) {
      if (h < 24) return Math.round(h) + 'h';
      const d = h / 24;
      return d < 2 ? d.toFixed(1) + 'd' : Math.round(d) + 'd';
    }
    function fmtDate(iso) {
      const d = new Date(iso);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) +
        ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    }

    document.getElementById('lu-estimates').innerHTML = `
      <div class="lu-est">
        <div class="est-time" style="color:#4caf50">${fmtHours(lu.optimistic_hours)}</div>
        <div class="est-label">Optimistic (perfect)</div>
        <div class="est-date">${fmtDate(lu.optimistic_date)}</div>
      </div>
      <div class="lu-est">
        <div class="est-time" style="color:#ffc107">${fmtHours(lu.realistic_hours)}</div>
        <div class="est-label">Realistic (${lu.accuracy_multiplier}x adj)</div>
        <div class="est-date">${fmtDate(lu.realistic_date)}</div>
      </div>
    `;

    // Stage donut chart
    const stages = lu.stage_counts || {};
    const stageNames = Object.keys(stages).filter(k => stages[k] > 0);
    const stageColorMap = {
      'Initiate': '#616161',
      'Apprentice I': '#ce93d8', 'Apprentice II': '#ba68c8',
      'Apprentice III': '#ab47bc', 'Apprentice IV': '#9c27b0',
      'Guru I': '#00bcd4', 'Guru II': '#0097a7',
      'Master': '#2196f3', 'Enlightened': '#ffc107', 'Burned': '#424242',
    };
    new Chart(document.getElementById('luStageChart'), {
      type: 'doughnut',
      data: {
        labels: stageNames,
        datasets: [{
          data: stageNames.map(n => stages[n]),
          backgroundColor: stageNames.map(n => stageColorMap[n] || '#888'),
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'bottom', labels: { color: '#ccc', font: { size: 10 }, padding: 6 } },
        },
      },
    });
    // Review schedule table
    if (lu.review_schedule && lu.review_schedule.length > 0) {
      const schedDiv = document.getElementById('lu-schedule');
      schedDiv.style.display = 'block';

      const stageColors = {
        'Apprentice I': '#ce93d8', 'Apprentice II': '#ba68c8',
        'Apprentice III': '#ab47bc', 'Apprentice IV': '#9c27b0',
        'Guru I': '#00bcd4', 'Guru II': '#0097a7',
      };

      // Always show all apprentice stages
      const sortedStages = ['Apprentice I','Apprentice II','Apprentice III','Apprentice IV'];

      const today = new Date().toISOString().slice(0, 10);
      let rows = '';
      lu.review_schedule.forEach(d => {
        const isToday = d.day === today;
        const dayLabel = isToday ? 'Today' :
          d.day_offset === 1 ? 'Tomorrow' :
          new Date(d.day + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
        const cls = isToday ? ' class="today"' : '';

        let stageCells = '';
        sortedStages.forEach(stage => {
          const count = d.stages[stage] || 0;
          const color = stageColors[stage] || '#888';
          if (count > 0) {
            stageCells += `<td><span class="stage-pill" style="background:${color}33;color:${color}">${count}</span></td>`;
          } else {
            stageCells += '<td style="color:#555">—</td>';
          }
        });

        rows += `<tr${cls}><td>${dayLabel}</td>${stageCells}<td style="font-weight:bold">${d.total || 0}</td></tr>`;
      });

      const stageHeaders = sortedStages.map(s => {
        const short = s.replace('Apprentice ', 'App ');
        return `<th>${short}</th>`;
      }).join('');

      schedDiv.innerHTML = `
        <h4>Upcoming Reviews <span style="font-weight:normal;color:#666;font-size:0.85em">— current level kanji only, does not include vocab or prior levels</span></h4>
        <table>
          <thead><tr><th>Day</th>${stageHeaders}<th>Total</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }

  } else if (lu && lu.status === 'ready') {
    const panel = document.getElementById('level-up-panel');
    panel.style.display = 'block';
    document.getElementById('lu-title').textContent =
      `Level ${latest.level} → ${latest.level + 1}`;
    document.getElementById('lu-subtitle').innerHTML =
      '<span style="color:#4caf50;font-size:1.2em;font-weight:bold">Ready to level up!</span>' +
      `  ${lu.already_guru}/${lu.guru_needed} kanji at Guru+`;
    document.getElementById('lu-bar').style.width = '100%';
    document.getElementById('lu-bar-label').textContent = 'Complete!';
  }

  // 1. Level Progress
  new Chart(document.getElementById('levelChart'), {
    type: 'line',
    data: {
      labels: dates,
      datasets: [
        {
          label: 'Level',
          data: snaps.map(s => s.level),
          borderColor: '#e94560',
          backgroundColor: 'rgba(233,69,96,0.1)',
          fill: true,
          tension: 0.3,
        },
        {
          label: 'N2 Target (Lv 48)',
          data: dates.map(() => 48),
          borderColor: 'rgba(255,193,7,0.4)',
          borderDash: [8, 4],
          pointRadius: 0,
          fill: false,
        },
        {
          label: 'N1 Target (Lv 60)',
          data: dates.map(() => 60),
          borderColor: 'rgba(76,175,80,0.4)',
          borderDash: [8, 4],
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: makeOpts({ scales: { y: { min: 0, max: 65, ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } } } }),
  });

  // 2. Kanji Learned
  new Chart(document.getElementById('kanjiChart'), {
    type: 'line',
    data: {
      labels: dates,
      datasets: [
        {
          label: 'Learned (Guru+)',
          data: snaps.map(s => s.kanji_learned),
          borderColor: '#00bcd4',
          backgroundColor: 'rgba(0,188,212,0.1)',
          fill: true,
          tension: 0.3,
        },
        {
          label: 'In Progress',
          data: snaps.map(s => s.kanji_in_progress),
          borderColor: '#ab47bc',
          backgroundColor: 'rgba(171,71,188,0.1)',
          fill: true,
          tension: 0.3,
        },
        {
          label: 'Vocab Learned',
          data: snaps.map(s => s.vocab_learned || 0),
          borderColor: '#ff6f00',
          backgroundColor: 'rgba(255,111,0,0.05)',
          fill: false,
          tension: 0.3,
          borderDash: [6, 3],
        },
      ],
    },
    options: makeOpts({ scales: { y: { min: 0, ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } } } }),
  });

  // 3. SRS Distribution (stacked bar)
  const srsColors = {
    Apprentice: '#ab47bc',
    Guru: '#00bcd4',
    Master: '#2196f3',
    Enlightened: '#ffc107',
    Burned: '#616161',
  };
  new Chart(document.getElementById('srsChart'), {
    type: 'bar',
    data: {
      labels: dates,
      datasets: Object.keys(srsColors).map(stage => ({
        label: stage,
        data: snaps.map(s => (s.srs && s.srs.buckets) ? (s.srs.buckets[stage] || 0) : 0),
        backgroundColor: srsColors[stage],
      })),
    },
    options: makeOpts({
      plugins: { legend: { labels: { color: '#ccc', font: { size: 11 } } } },
      scales: {
        x: { type: 'time', stacked: true, time: { unit: 'day' }, ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { stacked: true, ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
      },
    }),
  });

  // 4. Accuracy Trend
  new Chart(document.getElementById('accuracyChart'), {
    type: 'line',
    data: {
      labels: dates,
      datasets: [
        {
          label: 'Meaning',
          data: snaps.map(s => s.accuracy.meaning_pct),
          borderColor: '#4caf50',
          tension: 0.3,
        },
        {
          label: 'Reading',
          data: snaps.map(s => s.accuracy.reading_pct),
          borderColor: '#ff9800',
          tension: 0.3,
        },
        {
          label: 'Overall',
          data: snaps.map(s => s.accuracy.overall_pct),
          borderColor: '#e0e0e0',
          borderWidth: 2,
          borderDash: [4, 2],
          tension: 0.3,
        },
        {
          label: 'Vocab Meaning',
          data: snaps.map(s => s.vocab_accuracy ? s.vocab_accuracy.meaning_pct : null),
          borderColor: '#81c784',
          borderDash: [6, 3],
          tension: 0.3,
          pointRadius: 2,
        },
        {
          label: 'Vocab Reading',
          data: snaps.map(s => s.vocab_accuracy ? s.vocab_accuracy.reading_pct : null),
          borderColor: '#ffb74d',
          borderDash: [6, 3],
          tension: 0.3,
          pointRadius: 2,
        },
      ],
    },
    options: makeOpts({
      scales: {
        y: { min: 60, max: 100, ticks: { color: '#888', callback: v => v + '%' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        x: { type: 'time', time: { unit: 'day' }, ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
      },
    }),
  });

  // 5. JLPT Coverage
  const jlptColors = { N5: '#4caf50', N4: '#00bcd4', N3: '#ffc107', N2: '#ff9800', N1: '#e94560' };
  new Chart(document.getElementById('jlptChart'), {
    type: 'line',
    data: {
      labels: dates,
      datasets: Object.keys(jlptColors).map(level => ({
        label: level,
        data: snaps.map(s => s.jlpt_coverage && s.jlpt_coverage[level] ? s.jlpt_coverage[level].pct : 0),
        borderColor: jlptColors[level],
        tension: 0.3,
      })),
    },
    options: makeOpts({
      scales: {
        y: { min: 0, max: 100, ticks: { color: '#888', callback: v => v + '%' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        x: { type: 'time', time: { unit: 'day' }, ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
      },
    }),
  });

  // 6. Prediction Convergence (realistic dates over time)
  const n2Dates = [];
  const n1Dates = [];
  for (const s of snaps) {
    const lb = s.predictions && s.predictions.level_based;
    if (lb && lb.N2 && lb.N2.realistic) {
      n2Dates.push(new Date(lb.N2.realistic.date).getTime());
    } else {
      n2Dates.push(null);
    }
    if (lb && lb.N1 && lb.N1.realistic) {
      n1Dates.push(new Date(lb.N1.realistic.date).getTime());
    } else {
      n1Dates.push(null);
    }
  }

  new Chart(document.getElementById('predictionChart'), {
    type: 'line',
    data: {
      labels: dates,
      datasets: [
        {
          label: 'N2 Est. Date',
          data: n2Dates,
          borderColor: '#ffc107',
          tension: 0.3,
          spanGaps: true,
        },
        {
          label: 'N1 Est. Date',
          data: n1Dates,
          borderColor: '#4caf50',
          tension: 0.3,
          spanGaps: true,
        },
      ],
    },
    options: makeOpts({
      scales: {
        y: {
          type: 'time',
          time: { unit: 'month', tooltipFormat: 'MMM yyyy' },
          ticks: { color: '#888' },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
        x: { type: 'time', time: { unit: 'day' }, ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
      },
      plugins: {
        legend: { labels: { color: '#ccc', font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              if (ctx.raw === null) return '';
              const d = new Date(ctx.raw);
              return ctx.dataset.label + ': ' + d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
            }
          }
        }
      },
    }),
  });

  // Load cohort view (charts created but hidden until tab clicked)
  loadCohortView(snaps);
}

async function refreshData() {
  const btn = document.getElementById('refresh-btn');
  const origText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Pulling...';

  try {
    const resp = await fetch('/api/refresh', { method: 'POST' });
    const data = await resp.json();
    if (data.ok) {
      btn.innerHTML = 'Done!';
      setTimeout(() => location.reload(), 500);
    } else {
      btn.innerHTML = 'Error';
      console.error('Refresh failed:', data.error);
      setTimeout(() => { btn.innerHTML = origText; btn.disabled = false; }, 3000);
    }
  } catch (err) {
    btn.innerHTML = 'Error';
    console.error('Refresh error:', err);
    setTimeout(() => { btn.innerHTML = origText; btn.disabled = false; }, 3000);
  }
}

loadDashboard();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return HTML_PAGE


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Run the tracker to pull fresh data from WaniKani."""
    tracker_path = os.path.join(PROJECT_ROOT, "wanikani_tracker.py")
    try:
        result = subprocess.run(
            ["python3", tracker_path],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return jsonify({"ok": False, "error": result.stderr or "Tracker failed"}), 500
        return jsonify({"ok": True})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Tracker timed out"}), 504
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/history")
def api_history():
    if not os.path.exists(HISTORY_PATH):
        return jsonify({"snapshots": []})
    try:
        with open(HISTORY_PATH) as f:
            data = json.load(f)
        return jsonify(data)
    except (json.JSONDecodeError, ValueError):
        return jsonify({"snapshots": []})


def main():
    parser = argparse.ArgumentParser(description="WaniKani progress dashboard")
    parser.add_argument("--port", type=int, default=8082, help="Port (default 8082)")
    args = parser.parse_args()

    print(f"WaniKani Dashboard: http://localhost:{args.port}")
    print("Press Ctrl+C to stop")
    app.run(debug=False, port=args.port)


if __name__ == "__main__":
    main()
