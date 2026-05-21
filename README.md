# Troy Banks Audit Demo — Electricity Tariff Billing Comparison

---

<style>
  body { line-height: 1.65; }
  a[id]:not([href]) {
    display: block;
    height: 0;
    overflow: hidden;
  }
  h2 {
    font-size: 1.85rem;
    font-weight: 700;
    margin: 2.75rem 0 1.1rem;
    padding-bottom: 0.4rem;
    scroll-margin-top: 2rem;
  }
  h3 {
    font-size: 1.35rem;
    font-weight: 600;
    margin: 1.5rem 0 0.65rem;
    line-height: 1.3;
  }
  h4 {
    font-size: 1.15rem;
    font-weight: 600;
    margin: 1.15rem 0 0.45rem;
  }
  p { margin: 0.65rem 0 1rem; }
  ul, ol { margin: 0.65rem 0 1.35rem; padding-left: 1.4rem; }
  li { margin-bottom: 0.45rem; }
  li > ul, li > ol { margin-top: 0.35rem; margin-bottom: 0.5rem; }
  pre, .tree-block {
    background: #faf8f5;
    border: 1px solid #e0dbd4;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin: 1.15rem 0 1.65rem;
    overflow-x: auto;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.82rem;
    line-height: 1.5;
  }
  .flow-block {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.82rem;
    line-height: 1.5;
  }
  .feature-card {
    background: #f6f4f1;
    border: 1px solid #e0dbd4;
    border-radius: 10px;
    padding: 1.15rem 1.4rem 1.25rem;
    margin: 1.35rem 0 2rem;
  }
  .feature-card > h3:first-child { margin-top: 0; }
  .feature-lead {
    font-size: 1.08rem;
    color: #4a4a4a;
    margin: 0 0 1rem;
    padding-left: 0.65rem;
    border-left: 3px solid #c4b8a8;
  }
  .feature-card ul { margin-bottom: 0.75rem; }
  .meta-line {
    margin: 0.85rem 0 0;
    padding-top: 0.75rem;
    border-top: 1px solid #e0dbd4;
    font-size: 0.98rem;
  }
  .meta-line dt {
    display: inline;
    font-weight: 600;
    font-size: 1.05rem;
    margin-right: 0.35rem;
  }
  .meta-line dd { display: inline; margin: 0; }
  .step-block {
    margin: 1.25rem 0 1.5rem;
    padding: 0.85rem 0 0.25rem;
  }
  .step-block h4 {
    margin: 0 0 0.5rem;
    font-size: 1.12rem;
    color: #333;
  }
  .step-block pre {
    margin: 0.5rem 0 0;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0 1.65rem;
    font-size: 0.95rem;
  }
  th {
    text-align: left;
    background: #ebe6de;
    padding: 0.55rem 0.75rem;
    border: 1px solid #d4ccc0;
    font-weight: 600;
  }
  td {
    padding: 0.5rem 0.75rem;
    border: 1px solid #e0dbd4;
    vertical-align: top;
  }
  a { color: #1d4ed8; }
  .toc-links { margin: 0.65rem 0 2rem; padding-left: 1.4rem; line-height: 2; }
  .toc-links a { font-weight: 500; }
</style>

A Streamlit and FastAPI application for comparing Virginia Beach (VEPGA) electricity rate schedules. It normalizes customer billing history, detects usage anomalies, calculates charges under alternative tariffs, and presents savings in an interactive dashboard.

---

<a id="readme-contents"></a>

---

## Contents

---


- [Overview](#readme-overview)
- [Project structure](#readme-project-structure)
- [Features](#readme-features)
- [Installation](#readme-installation)
- [Quick start](#readme-quick-start)
- [Data pipeline](#readme-data-pipeline)
- [Configuration](#readme-configuration)
- [File guide](#readme-file-guide)
- [Implementation details](#readme-implementation-details)
- [Troubleshooting](#readme-troubleshooting)
- [Next steps](#readme-next-steps)
- [Support](#readme-support)


---
<a id="readme-overview"></a>

---

## Overview

---


This project helps electricity customers in Virginia Beach compare current charges to alternative VEPGA rate schedules (VE-100, VE-102, VE-110, VE-120, VE-154).

<ol>
  <li>Normalize billing history from raw Excel and PDF sources</li>
  <li>Analyze usage patterns and detect anomalies</li>
  <li>Calculate charges under five rate schedules</li>
  <li>Compare results and identify savings opportunities</li>
  <li>Visualize findings in a dashboard backed by a REST API</li>
</ol>


---
<a id="readme-project-structure"></a>

---

## Project structure

---


<pre class="tree-block">TroyBanks_Audit_Demo_VA/           Repository root
├── backend/                       FastAPI REST API (port 8000)
│   ├── main.py                    App entry, CORS, /health
│   ├── calc_service.py            Multi-schedule billing calculations
│   ├── billing_modules.py         Bridge to src billing engine
│   ├── db_usage.py                SQLite usage and bills
│   ├── usage_pipeline.py          Usage normalization on upload
│   └── routes/                    bills, calculate, anomalies, tariffs, export
├── frontend/                      Streamlit UI (port 8501)
│   ├── streamlit3.py              UI entry, routing, theme
│   ├── api_client.py              Backend HTTP client
│   ├── views/                     upload, results, ops, sidebar routers
│   ├── components/                tables, anomalies, analysis, ops
│   └── styles/                    dark/light CSS
├── src/                           Billing engine and batch pipeline
│   ├── va_step1_base.py           Step 1: normalize usage
│   ├── va_step2_anomalies.py      Step 2: YoY and anomalies
│   ├── Billing_Engine/app_new.py  Five schedule calculators
│   ├── riders_table_new.py        Rider rate parsing
│   └── Utils/paths.py             Paths and constants
├── data/                          raw, interim, export, riders
├── tests/                         Pytest suite
├── scripts/                       smoke test, env merge
├── infra/airflow/                 Optional Airflow stack
├── docker-compose.yml             API + UI services
├── FILE_GUIDE.md                  Per-file reference
└── README.md                      This file</pre>


---
<a id="readme-features"></a>

---

## Features

---


<div class="feature-card">
<h3>Data normalization — <code>src/va_step1_base.py</code></h3>
<p class="feature-lead">Load and clean municipal usage history from XLSB.</p>
<ul>
  <li>Parses Excel serial dates, timestamps, and YYYYMMDD strings</li>
  <li>Standardizes columns; filters Virginia accounts; computes billing gaps</li>
</ul>
<dl class="meta-line"><dt>Output</dt><dd><code>data/interim/va_step1_base_new.xlsx</code></dd></dl>
</div>

<div class="feature-card">
<h3>Anomaly analysis — <code>src/va_step2_anomalies.py</code></h3>
<p class="feature-lead">YoY usage, spikes, and 12-month account summaries.</p>
<dl class="meta-line"><dt>Output</dt><dd><code>data/interim/va_step2_anomalies.xlsx</code></dd></dl>
</div>

<div class="feature-card">
<h3>Billing engine — <code>src/Billing_Engine/app_new.py</code></h3>
<p class="feature-lead">Five VEPGA schedule calculators and savings vs. current charges.</p>

<h4>Schedule 120 (VE-120) — small commercial non-demand</h4>
<ul>
  <li>Non-metered only; seasonal ES blend; no demand charge</li>
</ul>

<h4>Schedule 154 (VE-154) — small commercial single-rate</h4>
<ul>
  <li>Metered or unmetered; flat ES rate</li>
</ul>

<h4>Schedule 102 (VE-102) — small commercial tiered</h4>
<ul>
  <li>Unmetered if any month ≤ 49 kWh in last 12 months; otherwise metered</li>
</ul>

<h4>Schedule 100 (VE-100) — large commercial non-demand</h4>
<ul>
  <li>Non-demand if all months &lt; 10,000 kWh; tiered ES buckets; kW riders suppressed</li>
</ul>

<h4>Schedule 110 (VE-110) — large commercial demand</h4>
<ul>
  <li>Demand billing with kW charges; full per-kWh and per-kW riders</li>
</ul>

<dl class="meta-line"><dt>Output</dt><dd>Per schedule: <code>ve{X00}_calculated_amount</code>, <code>ve{X00}_savings</code>, <code>ve{X00}_case_type</code>, plus parameter columns</dd></dl>
</div>

<div class="feature-card">
<h3>Interactive dashboard — <code>frontend/streamlit3.py</code></h3>
<ul>
  <li>PDF bill upload and analysis via FastAPI</li>
  <li>Rate compare and schedule compare tabs; operations hub (tariff, riders, past usage)</li>
  <li>Dark/light themes; Excel export</li>
</ul>
<dl class="meta-line"><dt>Run</dt><dd><code>streamlit run frontend/streamlit3.py</code></dd></dl>
<dl class="meta-line"><dt>Legacy</dt><dd><code>streamlit run src/Web_UI/streamlit.py</code> (local only, no API)</dd></dl>
</div>

<div class="feature-card">
<h3>REST API — <code>backend/</code></h3>
<ul>
  <li>Bill upload, multi-schedule calculation, anomalies, tariff/rider versions</li>
  <li>Usage persistence in SQLite; health check at <code>/health</code></li>
</ul>
</div>


---
<a id="readme-installation"></a>

---

## Installation

---


### Prerequisites

<ul>
  <li>Python 3.10+</li>
  <li>macOS, Linux, or Windows</li>
  <li>Docker (optional, for full stack)</li>
</ul>

### Setup

<ol>
  <li>Clone or navigate to the project:
<pre>cd /path/to/TroyBanks_Audit_Demo_VA</pre>
  </li>
  <li>Create a virtual environment:
<pre>python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate</pre>
  </li>
  <li>Install dependencies:
<pre>pip install -r requirements.txt
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt</pre>
  </li>
</ol>

### Key dependencies

<ul>
  <li><code>pandas</code>, <code>numpy</code> — data and numerics</li>
  <li><code>openpyxl</code>, <code>pyxlsb</code> — Excel I/O</li>
  <li><code>streamlit</code> — dashboard</li>
  <li><code>fastapi</code>, <code>uvicorn</code> — REST API</li>
</ul>


---
<a id="readme-quick-start"></a>

---

## Quick start

---


### Docker (recommended)

<pre>cp .env.example .env
docker compose up --build</pre>

<ul>
  <li>API: <code>http://localhost:8000</code></li>
  <li>UI: <code>http://localhost:8501</code></li>
</ul>

### Local batch pipeline + UI

<p>Ensure inputs exist under <code>data/raw/</code> and <code>data/rider_tables_new/</code>.</p>

<div class="step-block">
<h4>Step 1 — Normalize raw data</h4>
<pre>python src/va_step1_base.py
# → data/interim/va_step1_base_new.xlsx</pre>
</div>

<div class="step-block">
<h4>Step 2 — Analyze usage</h4>
<pre>python src/va_step2_anomalies.py
# → data/interim/va_step2_anomalies.xlsx</pre>
</div>

<div class="step-block">
<h4>Step 3 — Calculate schedules</h4>
<pre>python src/Billing_Engine/app_new.py
# → data/export/usage_savings_output.xlsx</pre>
</div>

<div class="step-block">
<h4>Step 4 — Run API and dashboard</h4>
<pre># Terminal 1
uvicorn backend.main:app --reload --port 8000

# Terminal 2
export BACKEND_URL=http://127.0.0.1:8000
streamlit run frontend/streamlit3.py</pre>
</div>

<p>Dashboard: <code>http://localhost:8501</code></p>

### Tests

<pre>pytest tests/ -q</pre>


---
<a id="readme-data-pipeline"></a>

---

## Data pipeline

---


<pre class="flow-block">Raw input (City VA Beach .xlsb + schedules + riders + PDF bills)
    ↓
va_step1_base.py  →  va_step1_base_new.xlsx
    ↓
va_step2_anomalies.py  →  va_step2_anomalies.xlsx
    ↓
app_new.py  →  usage_savings_output.xlsx
    ↓
frontend/streamlit3.py + backend API  →  upload, compare, export</pre>


---
<a id="readme-configuration"></a>

---

## Configuration

---


<p>Edit <a href="src/Utils/paths.py">src/Utils/paths.py</a> for batch script paths:</p>

<pre>SCHEDULES_XLSX = "path/to/Mini_Edit_VEPGA_Schedules_Compact.xlsx"
USAGE_INT = "path/to/va_step1_base_new.xlsx"
RIDERS_OUT = "path/to/rider_rates.xlsx"
EXPORT_DIR = "path/to/data/export/"</pre>

<p>Typical relative paths:</p>

<pre>data/raw/Mini_Edit_VEPGA_Schedules_Compact.xlsx
data/interim/va_step1_base_new.xlsx
data/rider_tables_new/[rider file]
data/export/</pre>

### Environment variables

<table>
  <thead><tr><th>Variable</th><th>Purpose</th></tr></thead>
  <tbody>
    <tr><td><code>BACKEND_URL</code></td><td>Streamlit → FastAPI (default <code>http://127.0.0.1:8000</code>)</td></tr>
    <tr><td><code>API_HOST_PORT</code></td><td>Docker API host port (default <code>8000</code>)</td></tr>
    <tr><td><code>STREAMLIT_HOST_PORT</code></td><td>Docker UI host port (default <code>8501</code>)</td></tr>
  </tbody>
</table>

<p>Copy <code>.env.example</code> to <code>.env</code> for Docker and Airflow secrets.</p>

### Airflow

<ul>
  <li><code>infra/airflow/config/airflow.cfg</code> — committed defaults</li>
  <li>Secrets in <code>.env</code> (Fernet key, DB URL, broker, Postgres)</li>
</ul>


---
<a id="readme-file-guide"></a>

---

## File guide

---


<p>See <a href="FILE_GUIDE.md">FILE_GUIDE.md</a> for per-file roles, data schemas, Excel layout, and implementation caveats.</p>

<table>
  <thead><tr><th>File</th><th>Role</th></tr></thead>
  <tbody>
    <tr><td><a href="src/va_step1_base.py">src/va_step1_base.py</a></td><td>Normalize XLSB usage data</td></tr>
    <tr><td><a href="src/va_step2_anomalies.py">src/va_step2_anomalies.py</a></td><td>YoY and anomaly analysis</td></tr>
    <tr><td><a href="src/Billing_Engine/app_new.py">src/Billing_Engine/app_new.py</a></td><td>Five schedule calculators</td></tr>
    <tr><td><a href="frontend/streamlit3.py">frontend/streamlit3.py</a></td><td>Current dashboard</td></tr>
    <tr><td><a href="backend/main.py">backend/main.py</a></td><td>FastAPI entry</td></tr>
  </tbody>
</table>


---
<a id="readme-implementation-details"></a>

---

## Implementation details

---


### Billing type logic
<ul>
  <li>VE-102: unmetered if any month in last 12m ≤ 49 kWh</li>
  <li>VE-100 / VE-110: non-demand if all months in last 12m &lt; 10,000 kWh</li>
</ul>

### ES charges
<ul>
  <li>Non-demand: flat per-kWh (seasonal blend where defined)</li>
  <li>Demand: tiered 150 kWh buckets (up to four tiers)</li>
</ul>

### Riders and parameters
<ul>
  <li>Per-kWh riders on all accounts; per-kW only on demand accounts</li>
  <li>Excel lookups use Category, Sub-Category, Item, Condition/Tier — format changes break extraction</li>
</ul>


---
<a id="readme-troubleshooting"></a>

---

## Troubleshooting

---


<div class="feature-card">
<h3>Import errors for <code>src</code></h3>
<ul>
  <li>Ensure <code>src/__init__.py</code> exists</li>
  <li>Run from project root with <code>PYTHONPATH=.</code> or use Docker</li>
</ul>
</div>

<div class="feature-card">
<h3>XLSB read errors</h3>
<ul>
  <li><code>pip install pyxlsb</code></li>
  <li>Verify the file is not corrupted</li>
</ul>
</div>

<div class="feature-card">
<h3>Streamlit not loading</h3>
<ul>
  <li><code>streamlit run frontend/streamlit3.py</code> from project root</li>
  <li>Set <code>BACKEND_URL</code> if the API is not on port 8000</li>
</ul>
</div>

<div class="feature-card">
<h3>API unhealthy in Docker</h3>
<ul>
  <li><code>curl http://localhost:8000/health</code></li>
  <li><code>docker compose logs backend</code></li>
</ul>
</div>


---
<a id="readme-next-steps"></a>

---

## Next steps

---


<ul>
  <li>Expand unit tests for schedule functions</li>
  <li>Batch processing for large municipal extracts</li>
  <li>Additional upload validation and PDF reports</li>
  <li>Forecast and projection features</li>
</ul>


---
<a id="readme-support"></a>

---

## Support

---


<ul>
  <li><a href="FILE_GUIDE.md">FILE_GUIDE.md</a> — file and data-flow reference</li>
  <li><a href="frontend/README.md">frontend/README.md</a> — UI modules and environment</li>
  <li><a href="docs/PROJECT_STATUS_AND_TODO/STEPS.txt">docs/PROJECT_STATUS_AND_TODO/STEPS.txt</a> — launch checklist</li>
  <li>Excel parameter sheets — validate rates before production runs</li>
</ul>
