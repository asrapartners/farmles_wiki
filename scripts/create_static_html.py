#!/usr/bin/env python3
"""
Generate a static HTML site from the Farmless wiki/ folder.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

EPILOG = """
REBUILD MODES
-------------
Full rebuild (default):
  Triggered when any of the following are true:
    - --changed is not provided
    - --changed is an empty list
    - --changed includes <input>/market_registry.jsonl
    - --changed includes <input>/vendor_registry.jsonl
    - <out>/index.html does not exist
    - <out>/market_registry.json does not exist

  Steps: delete <out>/, recreate it, write market_registry.json,
  write index.html, convert all market Markdown files.

Incremental rebuild:
  Triggered only when --changed lists market Markdown files exclusively
  and the required output files already exist.

  Steps: regenerate all HTML files for each affected market directory.
  Registry and landing page are left untouched.

EXIT CODES
----------
  0  Success
  1  Input error (missing file, invalid JSON, missing required field,
     unreadable Markdown)
  2  Output write failure

GITHUB ACTIONS INTEGRATION
---------------------------
Pass changed files from the push diff so the script can decide the
rebuild mode automatically:

  - name: Install dependencies
    run: pip install -r requirements.txt

  - name: Build static site
    run: |
      CHANGED=$(git diff --name-only ${{ github.event.before }} HEAD | tr '\\n' ' ')
      python scripts/create_static_html.py \\
        --input wiki --out public \\
        --changed $CHANGED

  - name: Deploy to GitHub Pages
    uses: peaceiris/actions-gh-pages@v3
    with:
      github_token: ${{ secrets.GITHUB_TOKEN }}
      publish_dir: ./public

Notes:
  - On first deploy (or after structural changes), omit --changed to force
    a full rebuild.
  - If market_registry.jsonl or vendor_registry.jsonl appears in CHANGED,
    a full rebuild is triggered automatically.
  - The public/ folder must be excluded from git (add it to .gitignore).
"""

REQUIRED_MARKET_FIELDS = ("id", "name", "city", "zip")
PAGE_SIZE = 10


def get_git_commit() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def load_market_registry(registry_path: Path) -> list[dict]:
    if not registry_path.exists():
        sys.exit(f"[error] Missing required file: {registry_path}")
    markets = []
    try:
        lines = registry_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        sys.exit(f"[error] Cannot read {registry_path}: {exc}")
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.exit(f"[error] Invalid JSON on line {i} of {registry_path}: {exc}\n  Content: {line!r}")
        for field in REQUIRED_MARKET_FIELDS:
            if field not in entry:
                sys.exit(f"[error] Missing field '{field}' in entry on line {i} of {registry_path}: {entry}")
        markets.append(entry)
    return markets


def write_market_registry_json(markets: list[dict], out_path: Path) -> None:
    try:
        out_path.write_text(json.dumps(markets, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        sys.exit(f"[error][exit:2] Cannot write {out_path}: {exc}")


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

def extract_title(source: str, fallback: str) -> str:
    for line in source.splitlines():
        m = re.match(r"^#\s+(.+)", line)
        if m:
            return m.group(1).strip()
    return fallback


def render_markdown(source: str) -> str:
    try:
        import markdown as md_lib
    except ImportError:
        sys.exit("[error] The 'markdown' package is not installed. Run: pip install markdown")
    return md_lib.markdown(source, extensions=["tables", "fenced_code"])


# ---------------------------------------------------------------------------
# Vendor parsing
# ---------------------------------------------------------------------------

def parse_vendors(source: str) -> list[dict]:
    """Parse vendors.md into a list of vendor dicts.

    Each vendor block starts with a '## vendor_id' heading and contains
    inline 'Name:' / 'Status:' fields and a '### Products' subsection.
    """
    vendors: list[dict] = []
    current: dict | None = None
    section: str | None = None

    for line in source.splitlines():
        if line.startswith("## "):
            if current:
                vendors.append(current)
            current = {"id": line[3:].strip(), "name": "", "status": "active", "products": []}
            section = None
        elif current is None:
            continue
        elif line.startswith("### "):
            section = line[4:].strip().lower()
        elif section is None:
            if line.startswith("Name:"):
                current["name"] = line[5:].strip()
            elif line.startswith("Status:"):
                current["status"] = line[7:].strip()
        elif section == "products" and line.startswith("- "):
            current["products"].append(line[2:].strip())
        # Sources and other subsections are intentionally skipped

    if current:
        vendors.append(current)

    return [v for v in vendors if v["name"]]  # drop malformed entries


# ---------------------------------------------------------------------------
# Market index page (index.md -> index.html)
# ---------------------------------------------------------------------------

def preprocess_market_markdown(source: str) -> str:
    """Convert raw URL and logo values to markdown links/images before rendering."""
    # ## URL\n<bare url>  →  ## URL\n[url](url)
    source = re.sub(
        r'(^## URL[ \t]*\n)(https?://\S+)',
        lambda m: m.group(1) + f'[{m.group(2)}]({m.group(2)})',
        source, flags=re.MULTILINE,
    )
    # ## Logo\n<bare url>  →  ## Logo\n![logo](url)
    source = re.sub(
        r'(^## Logo[ \t]*\n)(https?://\S+)',
        lambda m: m.group(1) + f'![logo]({m.group(2)})',
        source, flags=re.MULTILINE,
    )
    return source


def generate_market_index_html(source: str, vendor_count: int) -> str:
    title = extract_title(source, "Market")
    body = render_markdown(preprocess_market_markdown(source))
    vendors_label = f"Vendors ({vendor_count})" if vendor_count else "Vendors"
    return (
        "<!doctype html>\n"
        "<html>\n"
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{title}</title>\n"
        "  <style>\n"
        "    body { font-family: sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }\n"
        "    nav { margin-bottom: 1.5rem; font-size: 0.9rem; }\n"
        "    nav a { color: #1a73e8; text-decoration: none; }\n"
        "    nav a:hover { text-decoration: underline; }\n"
        "    nav .sep { color: #999; margin: 0 0.4rem; }\n"
        "    img { max-width: 220px; max-height: 160px; display: block; margin: 0.5rem 0 1rem; border: 1px solid #ddd; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <nav>\n"
        '    <a href="../../index.html">&#8592; Markets</a>\n'
        '    <span class="sep">|</span>\n'
        f'    <a href="vendors.html">{vendors_label}</a>\n'
        "  </nav>\n"
        f"  {body}\n"
        "</body>\n"
        "</html>\n"
    )


# ---------------------------------------------------------------------------
# Vendor page (vendors.md -> vendors.html)
# ---------------------------------------------------------------------------

VENDORS_HTML_TEMPLATE = """\
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Vendors — {market_name}</title>
  <style>
    body { font-family: sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
    nav { margin-bottom: 1.5rem; font-size: 0.9rem; }
    nav a { color: #1a73e8; text-decoration: none; }
    nav a:hover { text-decoration: underline; }
    nav .sep { color: #999; margin: 0 0.4rem; }
    h1 { margin-bottom: 0.25rem; }
    #search { width: 100%; padding: 0.5rem; font-size: 1rem; margin: 1rem 0; box-sizing: border-box; }
    #count { color: #555; font-size: 0.9rem; margin-bottom: 1rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; }
    .card { border: 1px solid #ddd; border-radius: 6px; padding: 1rem; }
    .card h2 { margin: 0 0 0.4rem; font-size: 1rem; }
    .badge { display: inline-block; font-size: 0.75rem; padding: 0.1rem 0.4rem;
             border-radius: 3px; margin-bottom: 0.5rem; }
    .badge.active { background: #e6f4ea; color: #1e7e34; }
    .badge.inactive { background: #fce8e6; color: #c5221f; }
    .products { margin: 0; padding-left: 1.2rem; font-size: 0.9rem; color: #333; }
    .products li { margin-bottom: 0.15rem; }
    #no-match { display: none; color: #888; font-style: italic; margin-top: 1rem; }
    #empty-msg { color: #888; font-style: italic; }
  </style>
</head>
<body>
  <nav>
    <a href="../../index.html">&#8592; Markets</a>
    <span class="sep">|</span>
    <a href="index.html">{market_name}</a>
  </nav>
  <h1>Vendors — {market_name}</h1>
{body_content}
  <script>
const VENDORS = {vendors_json};

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function renderCards(list) {
  if (!list.length) {
    document.getElementById('no-match').style.display = 'block';
    document.getElementById('grid').innerHTML = '';
    document.getElementById('count').textContent = '0 vendors';
    return;
  }
  document.getElementById('no-match').style.display = 'none';
  document.getElementById('count').textContent = list.length + ' vendor' + (list.length !== 1 ? 's' : '');
  document.getElementById('grid').innerHTML = list.map(v => {
    const badgeClass = v.status === 'active' ? 'active' : 'inactive';
    const products = v.products.length
      ? '<ul class="products">' + v.products.map(p => '<li>' + escHtml(p) + '</li>').join('') + '</ul>'
      : '';
    return '<div class="card">'
      + '<h2>' + escHtml(v.name) + '</h2>'
      + '<span class="badge ' + badgeClass + '">' + escHtml(v.status) + '</span>'
      + products
      + '</div>';
  }).join('');
}

document.getElementById('search').addEventListener('input', function() {
  const q = this.value.toLowerCase().trim();
  const filtered = q
    ? VENDORS.filter(v =>
        v.name.toLowerCase().includes(q) ||
        v.products.some(p => p.toLowerCase().includes(q))
      )
    : VENDORS;
  renderCards(filtered);
});

renderCards(VENDORS);
  </script>
</body>
</html>
"""


def generate_vendors_html(vendors: list[dict], market_name: str) -> str:
    if not vendors:
        body_content = '  <p id="empty-msg">No vendors on record for this market.</p>\n'
        return (
            VENDORS_HTML_TEMPLATE
            .replace("{market_name}", market_name)
            .replace("{body_content}", body_content)
            .replace("{vendors_json}", "[]")
        )

    body_content = (
        '  <input id="search" type="search" placeholder="Search by name or product&hellip;" aria-label="Search vendors">\n'
        '  <p id="count"></p>\n'
        '  <p id="no-match">No vendors match your search.</p>\n'
        '  <div id="grid" class="grid"></div>\n'
    )
    vendors_json = json.dumps(vendors, ensure_ascii=False)
    return (
        VENDORS_HTML_TEMPLATE
        .replace("{market_name}", market_name)
        .replace("{body_content}", body_content)
        .replace("{vendors_json}", vendors_json)
    )


# ---------------------------------------------------------------------------
# Per-market directory conversion
# ---------------------------------------------------------------------------

def convert_market_dir(market_dir: Path, out_market_dir: Path) -> None:
    out_market_dir.mkdir(parents=True, exist_ok=True)

    vendors_md_path = market_dir / "vendors.md"
    vendors: list[dict] = []
    if vendors_md_path.exists():
        try:
            vendors_source = vendors_md_path.read_text(encoding="utf-8")
        except OSError as exc:
            sys.exit(f"[error] Cannot read {vendors_md_path}: {exc}")
        vendors = parse_vendors(vendors_source)

    index_md_path = market_dir / "index.md"
    if index_md_path.exists():
        try:
            index_source = index_md_path.read_text(encoding="utf-8")
        except OSError as exc:
            sys.exit(f"[error] Cannot read {index_md_path}: {exc}")
        market_name = extract_title(index_source, market_dir.name)
        html = generate_market_index_html(index_source, len(vendors))
        try:
            (out_market_dir / "index.html").write_text(html, encoding="utf-8")
        except OSError as exc:
            sys.exit(f"[error][exit:2] Cannot write {out_market_dir / 'index.html'}: {exc}")
    else:
        market_name = market_dir.name

    vendors_html = generate_vendors_html(vendors, market_name)
    try:
        (out_market_dir / "vendors.html").write_text(vendors_html, encoding="utf-8")
    except OSError as exc:
        sys.exit(f"[error][exit:2] Cannot write {out_market_dir / 'vendors.html'}: {exc}")


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

LANDING_PAGE_TEMPLATE = """\
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Farmer's Market Database</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: monospace; max-width: 860px; margin: 0 auto; padding: 0 0 3rem; background: #fff; color: #000; }

    /* Banner */
    .banner { background: #000; color: #fff; padding: 1.4rem 1.5rem 1.2rem; display: flex; justify-content: space-between; align-items: flex-end; }
    .banner h1 { margin: 0; font-size: 1.5rem; font-family: monospace; font-weight: 700; letter-spacing: 0.02em; }
    .banner-right { text-align: right; }
    .banner-sub { font-size: 0.8rem; color: #aaa; margin: 0.2rem 0 0; }
    .commit-badge { font-size: 0.75rem; color: #888; display: block; margin-top: 0.15rem; }

    /* Content area */
    .content { padding: 1.2rem 1.5rem 0; }

    /* Top states strip */
    .top-states { display: flex; align-items: center; flex-wrap: wrap; gap: 0; margin-bottom: 1rem; border: 1px solid #000; }
    .state-chip { background: #fff; border: none; border-right: 1px solid #000; padding: 0.3rem 0.8rem;
                  font-size: 0.82rem; font-family: monospace; cursor: pointer;
                  display: inline-flex; align-items: center; gap: 0.4rem; color: #000; font-weight: 700; }
    .state-chip:hover, .state-chip.active { background: #000; color: #fff; }
    .state-chip span { font-weight: 400; color: #555; }
    .state-chip:hover span, .state-chip.active span { color: #aaa; }
    #chip-all { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
    .more-link-wrap { margin-left: auto; border-left: 1px solid #000; }
    .more-link { display: block; padding: 0.3rem 0.8rem; font-size: 0.82rem;
                 font-family: monospace; color: #000; text-decoration: none; font-weight: 700; }
    .more-link:hover { background: #000; color: #fff; }

    /* Search */
    #search { width: 100%; padding: 0.55rem 0.7rem; font-size: 0.95rem; font-family: monospace;
              margin-bottom: 0; border: 1px solid #000; border-top: none; background: #fff;
              display: block; }
    #search:focus { outline: 2px solid #000; outline-offset: -2px; }

    /* Results */
    #results { list-style: none; padding: 0; margin: 0; border: 1px solid #000; border-top: none; }
    #results li { padding: 0.55rem 0.7rem; border-top: 1px solid #ddd; font-size: 0.88rem; }
    #results li:first-child { border-top: none; }
    #results li a { font-weight: 700; text-decoration: none; color: #000; }
    #results li a:hover { text-decoration: underline; }
    .meta { color: #555; }

    /* Pagination */
    #pagination { margin-top: 0; border: 1px solid #000; border-top: none; display: flex; align-items: center; }
    #pagination button { padding: 0.4rem 0.9rem; cursor: pointer; border: none; border-right: 1px solid #000;
                          background: #fff; font-family: monospace; font-size: 0.85rem; }
    #pagination button:hover:not(:disabled) { background: #000; color: #fff; }
    #pagination button:disabled { color: #bbb; cursor: default; }
    #page-info { font-size: 0.82rem; color: #555; padding: 0 0.7rem; }
    #next-btn { border-right: none; border-left: 1px solid #000; margin-left: auto; }

    /* Results toolbar */
    .results-toolbar { display: flex; justify-content: space-between; align-items: center;
                       padding: 0.3rem 0.7rem; border: 1px solid #000; border-top: none;
                       font-size: 0.8rem; background: #f4f4f4; font-family: monospace; }
    #result-count { color: #555; }
    #page-size { font-family: monospace; font-size: 0.8rem; border: 1px solid #888;
                 padding: 0.1rem 0.3rem; background: #fff; cursor: pointer; }
  </style>
</head>
<body>
  <header class="banner">
    <h1>Farmer's Market Database</h1>
    <div class="banner-right">
      <p class="banner-sub">{summary_text}</p>
      <span class="commit-badge">commit: {git_commit}</span>
    </div>
  </header>

  <div class="content">
    <div class="top-states">
      <button id="chip-all" class="state-chip active" onclick="clearState()">All States</button>
      {top_states_html}
    </div>
    <input id="search" type="search" placeholder="Search name, city, state, ZIP&hellip;" aria-label="Search markets">
  </div>
  <div class="results-toolbar">
    <span id="result-count"></span>
    <label for="page-size">Show:
      <select id="page-size" oninput="pageSize=parseInt(this.value);currentPage=0;render()">
        <option value="10" selected>10</option>
        <option value="25">25</option>
        <option value="50">50</option>
        <option value="0">All</option>
      </select>
    </label>
  </div>
  <ul id="results"></ul>
  <div id="pagination" hidden>
    <button id="prev-btn" onclick="changePage(-1)">&#8592; Prev</button>
    <span id="page-info"></span>
    <button id="next-btn" onclick="changePage(1)">Next &#8594;</button>
  </div>

  <script>
    let pageSize = {page_size};
    let allMarkets = {markets_json};
    let filtered = [];
    let currentPage = 0;

    const _stateParam = new URLSearchParams(window.location.search).get('state');
    if (_stateParam) { selectState(_stateParam.toUpperCase()); } else { filtered = [...allMarkets].sort(byName); render(); }

    function clearState() {
      document.getElementById('search').value = '';
      document.querySelectorAll('.state-chip').forEach(c => c.classList.remove('active'));
      document.getElementById('chip-all').classList.add('active');
      filtered = [...allMarkets].sort(byName);
      currentPage = 0;
      render();
    }

    function selectState(state) {
      const input = document.getElementById('search');
      const already = input.value === state;
      if (already) { clearState(); return; }
      input.value = state;
      document.querySelectorAll('.state-chip').forEach(c => c.classList.remove('active'));
      document.querySelectorAll(`.state-chip[data-state="${state}"]`).forEach(c => c.classList.add('active'));
      applySearch(state);
    }

    function applySearch(q) {
      q = q.toLowerCase().trim();
      if (!q) { filtered = [...allMarkets].sort(byName); currentPage = 0; render(); return; }
      const isStateCode = /^[a-z]{2}$/.test(q);
      if (isStateCode) {
        filtered = allMarkets.filter(m => (m.state || '').toLowerCase() === q);
      } else {
        filtered = allMarkets.filter(m =>
          m.name.toLowerCase().includes(q) ||
          m.city.toLowerCase().includes(q) ||
          String(m.zip).toLowerCase().includes(q)
        );
      }
      filtered = filtered.slice().sort(byName);
      currentPage = 0;
      render();
    }

    function byName(a, b) { return a.name < b.name ? -1 : a.name > b.name ? 1 : 0; }

    document.getElementById('search').addEventListener('input', function() {
      document.querySelectorAll('.state-chip').forEach(c => c.classList.remove('active'));
      document.getElementById('chip-all').classList.toggle('active', !this.value.trim());
      applySearch(this.value);
    });

    function changePage(delta) {
      const maxPage = pageSize ? Math.ceil(filtered.length / pageSize) - 1 : 0;
      currentPage = Math.max(0, Math.min(currentPage + delta, maxPage));
      render();
    }

    function render() {
      const list = document.getElementById('results');
      const pag = document.getElementById('pagination');
      const showAll = pageSize === 0;
      const start = showAll ? 0 : currentPage * pageSize;
      const slice = showAll ? filtered : filtered.slice(start, start + pageSize);

      list.innerHTML = slice.length
        ? slice.map(m =>
            `<li>
              <a href="markets/${m.id}/index.html">${escHtml(m.name)}</a>
              <span class="meta"> &mdash; ${escHtml(m.city)}, ${escHtml(m.state || '')}, ${escHtml(String(m.zip))}</span>
            </li>`
          ).join('')
        : '<li>No markets found.</li>';

      document.getElementById('result-count').textContent =
        `${filtered.length} result${filtered.length !== 1 ? 's' : ''}`;
      const totalPages = showAll ? 1 : (Math.ceil(filtered.length / pageSize) || 1);
      pag.hidden = showAll || totalPages <= 1;
      document.getElementById('page-info').textContent =
        `Page ${currentPage + 1} of ${totalPages}`;
      document.getElementById('prev-btn').disabled = currentPage === 0;
      document.getElementById('next-btn').disabled = currentPage >= totalPages - 1;
    }

    function escHtml(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
  </script>
</body>
</html>
"""

STATES_PAGE_TEMPLATE = """\
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Farmer's Market By State</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: monospace; max-width: 560px; margin: 0 auto; padding: 0 0 3rem; background: #fff; color: #000; }
    .banner { background: #000; color: #fff; padding: 1.2rem 1.5rem; display: flex; justify-content: space-between; align-items: center; }
    .banner h1 { margin: 0; font-size: 1.2rem; font-weight: 700; }
    .banner a { color: #aaa; text-decoration: none; font-size: 0.82rem; }
    .banner a:hover { color: #fff; }
    table { border-collapse: collapse; width: 100%; }
    th { text-align: left; padding: 0.5rem 1rem; border-bottom: 2px solid #000;
         cursor: pointer; user-select: none; background: #f4f4f4; font-size: 0.85rem; font-family: monospace; }
    th:hover { background: #e8e8e8; }
    td { padding: 0.45rem 1rem; border-bottom: 1px solid #ddd; font-size: 0.88rem; }
    tbody tr:hover { background: #f8f8f8; }
    td a { color: #000; font-weight: 700; text-decoration: none; }
    td a:hover { text-decoration: underline; }
    .count { font-variant-numeric: tabular-nums; font-weight: 700; }
  </style>
</head>
<body>
  <div class="banner">
    <h1>Farmer's Market By State</h1>
    <a href="index.html">&#8592; Back</a>
  </div>
  <table>
    <thead><tr>
      <th id="th-state" onclick="sortTable('state')">STATE</th>
      <th id="th-count" onclick="sortTable('count')">TOTAL MARKETS ▼</th>
    </tr></thead>
    <tbody id="tbody"></tbody>
  </table>
  <script>
    const STATES = {states_json};
    let sortCol = 'count';
    let sortDir = -1;

    renderTable();

    function sortTable(col) {
      if (sortCol === col) { sortDir *= -1; } else { sortCol = col; sortDir = -1; }
      renderTable();
    }

    function renderTable() {
      const sorted = [...STATES].sort((a, b) => {
        const av = sortCol === 'state' ? a.state : a.count;
        const bv = sortCol === 'state' ? b.state : b.count;
        return av < bv ? -sortDir : av > bv ? sortDir : 0;
      });
      document.getElementById('tbody').innerHTML = sorted.map(r =>
        `<tr><td><a href="index.html?state=${escHtml(r.state)}">${escHtml(r.state)}</a></td><td class="count">${r.count.toLocaleString()}</td></tr>`
      ).join('');
      document.getElementById('th-state').textContent =
        'STATE' + (sortCol === 'state' ? (sortDir === 1 ? ' ▲' : ' ▼') : '');
      document.getElementById('th-count').textContent =
        'TOTAL MARKETS' + (sortCol === 'count' ? (sortDir === 1 ? ' ▲' : ' ▼') : '');
    }

    function escHtml(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
  </script>
</body>
</html>
"""


def write_landing_page(out_dir: Path, markets: list[dict], git_commit: str) -> None:
    state_counts = Counter(m.get("state", "") for m in markets if m.get("state"))
    top5 = state_counts.most_common(5)
    top_states_html = "".join(
        f'<button class="state-chip" data-state="{s}" onclick="selectState(\'{s}\')">'
        f'{s} <span>{c:,}</span></button>'
        for s, c in top5
    )
    top_states_html += '<span class="more-link-wrap"><a class="more-link" href="states.html">More &#8594;</a></span>'
    summary_text = f"{len(markets):,} markets &middot; {len(state_counts):,} states"
    markets_json = json.dumps(markets, ensure_ascii=False)
    html = (
        LANDING_PAGE_TEMPLATE
        .replace("{page_size}", str(PAGE_SIZE))
        .replace("{markets_json}", markets_json)
        .replace("{git_commit}", git_commit)
        .replace("{summary_text}", summary_text)
        .replace("{top_states_html}", top_states_html)
    )
    dest = out_dir / "index.html"
    try:
        dest.write_text(html, encoding="utf-8")
    except OSError as exc:
        sys.exit(f"[error][exit:2] Cannot write {dest}: {exc}")


def write_states_page(out_dir: Path, markets: list[dict]) -> None:
    state_counts = Counter(m.get("state", "") for m in markets if m.get("state"))
    states_data = [{"state": s, "count": c} for s, c in state_counts.items()]
    states_json = json.dumps(states_data, ensure_ascii=False)
    html = STATES_PAGE_TEMPLATE.replace("{states_json}", states_json)
    dest = out_dir / "states.html"
    try:
        dest.write_text(html, encoding="utf-8")
    except OSError as exc:
        sys.exit(f"[error][exit:2] Cannot write {dest}: {exc}")


# ---------------------------------------------------------------------------
# Build logic
# ---------------------------------------------------------------------------

def convert_all_markets(input_dir: Path, out_dir: Path) -> None:
    markets_dir = input_dir / "markets"
    if not markets_dir.is_dir():
        return
    for market_dir in sorted(markets_dir.iterdir()):
        if not market_dir.is_dir():
            continue
        convert_market_dir(market_dir, out_dir / "markets" / market_dir.name)


def ui_rebuild(input_dir: Path, out_dir: Path) -> None:
    if not out_dir.exists():
        sys.exit(f"[error] Output directory does not exist: {out_dir} — run a full build first")
    print(f"[info] UI rebuild: regenerating index.html and states.html")
    git_commit = get_git_commit()
    registry_path = input_dir / "market_registry.jsonl"
    markets = load_market_registry(registry_path)
    write_landing_page(out_dir, markets, git_commit)
    write_states_page(out_dir, markets)
    print("[info] Done.")


def full_rebuild(input_dir: Path, out_dir: Path) -> None:
    print(f"[info] Full rebuild: {input_dir} -> {out_dir}")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    git_commit = get_git_commit()
    registry_path = input_dir / "market_registry.jsonl"
    markets = load_market_registry(registry_path)
    write_market_registry_json(markets, out_dir / "market_registry.json")
    write_landing_page(out_dir, markets, git_commit)
    write_states_page(out_dir, markets)
    convert_all_markets(input_dir, out_dir)
    print(f"[info] Done. {len(markets)} market(s) processed.")


def incremental_rebuild(input_dir: Path, out_dir: Path, changed_paths: list[Path]) -> None:
    markets_prefix = (input_dir / "markets").resolve()
    # Collect unique market dirs that have changed files
    affected: set[Path] = set()
    for p in changed_paths:
        if p.suffix == ".md" and markets_prefix in p.parents:
            affected.add(p.parent)

    if not affected:
        print("[info] No market Markdown files in --changed; nothing to do.")
        return

    print(f"[info] Incremental rebuild: {len(affected)} market dir(s)")
    for market_dir in sorted(affected):
        out_market_dir = out_dir / "markets" / market_dir.name
        convert_market_dir(market_dir, out_market_dir)
        print(f"[info]   {market_dir.name}")


def needs_full_rebuild(
    input_dir: Path,
    out_dir: Path,
    changed: list[str] | None,
) -> bool:
    if changed is None or len(changed) == 0:
        return True
    registry_files = {
        (input_dir / "market_registry.jsonl").resolve(),
        (input_dir / "vendor_registry.jsonl").resolve(),
    }
    if any(Path(c).resolve() in registry_files for c in changed):
        return True
    if not (out_dir / "index.html").exists():
        return True
    if not (out_dir / "market_registry.json").exists():
        return True
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="create_static_html.py",
        description="Generate a static HTML site from the Farmless wiki/ folder.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    parser.add_argument(
        "--input",
        default="wiki",
        metavar="DIR",
        help="Path to the wiki input folder (default: wiki)",
    )
    parser.add_argument(
        "--out",
        default="public",
        metavar="DIR",
        help="Path to the output folder (default: public)",
    )
    parser.add_argument(
        "--changed",
        nargs="*",
        metavar="FILE",
        default=None,
        help=(
            "Optional list of changed file paths. When provided and all changed "
            "files are market Markdown files, only those markets are regenerated "
            "(incremental rebuild). Including a registry file forces a full rebuild."
        ),
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        default=False,
        help="Only regenerate index.html and states.html (fast UI-only rebuild).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_dir = Path(args.input).resolve()
    out_dir = Path(args.out).resolve()

    if not input_dir.is_dir():
        sys.exit(f"[error] Input directory not found: {input_dir}")

    if args.ui:
        ui_rebuild(input_dir, out_dir)
        return

    if needs_full_rebuild(input_dir, out_dir, args.changed):
        full_rebuild(input_dir, out_dir)
    else:
        changed_paths = [Path(p).resolve() for p in args.changed]
        incremental_rebuild(input_dir, out_dir, changed_paths)


if __name__ == "__main__":
    main()
