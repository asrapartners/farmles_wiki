#!/usr/bin/env python3
"""
Generate a static HTML site from the Farmless wiki/ folder.
"""

import argparse
import json
import os
import re
import shutil
import sys
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

def generate_market_index_html(source: str, vendor_count: int) -> str:
    title = extract_title(source, "Market")
    body = render_markdown(source)
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
  <title>Farmless Markets</title>
  <style>
    body { font-family: sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }
    h1 { margin-bottom: 0.5rem; }
    #search { width: 100%; padding: 0.5rem; font-size: 1rem; margin: 1rem 0; box-sizing: border-box; }
    #results { list-style: none; padding: 0; margin: 0; }
    #results li { padding: 0.6rem 0; border-bottom: 1px solid #eee; }
    #results li a { font-weight: bold; text-decoration: none; color: #1a73e8; }
    #results li a:hover { text-decoration: underline; }
    .meta { color: #555; font-size: 0.9rem; }
    #pagination { margin-top: 1rem; display: flex; align-items: center; gap: 0.5rem; }
    #pagination button { padding: 0.4rem 0.8rem; cursor: pointer; }
    #pagination button:disabled { opacity: 0.4; cursor: default; }
    #page-info { font-size: 0.9rem; color: #555; }
    #status { color: #888; font-style: italic; }
  </style>
</head>
<body>
  <h1>Farmless Markets</h1>
  <input id="search" type="search" placeholder="Search by name, city, or ZIP&hellip;" aria-label="Search markets">
  <p id="status">Loading&hellip;</p>
  <ul id="results"></ul>
  <div id="pagination" hidden>
    <button id="prev-btn" onclick="changePage(-1)">&#8592; Prev</button>
    <span id="page-info"></span>
    <button id="next-btn" onclick="changePage(1)">Next &#8594;</button>
  </div>

  <script>
    const PAGE_SIZE = {page_size};
    let allMarkets = [];
    let filtered = [];
    let currentPage = 0;

    fetch('market_registry.json')
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); })
      .then(data => {
        allMarkets = data;
        filtered = data;
        document.getElementById('status').textContent = '';
        render();
      })
      .catch(err => {
        document.getElementById('status').textContent = 'Failed to load market data: ' + err.message;
      });

    document.getElementById('search').addEventListener('input', function() {
      const q = this.value.toLowerCase().trim();
      filtered = q
        ? allMarkets.filter(m =>
            m.name.toLowerCase().includes(q) ||
            m.city.toLowerCase().includes(q) ||
            String(m.zip).toLowerCase().includes(q)
          )
        : allMarkets;
      currentPage = 0;
      render();
    });

    function changePage(delta) {
      const maxPage = Math.ceil(filtered.length / PAGE_SIZE) - 1;
      currentPage = Math.max(0, Math.min(currentPage + delta, maxPage));
      render();
    }

    function render() {
      const list = document.getElementById('results');
      const pag = document.getElementById('pagination');
      const start = currentPage * PAGE_SIZE;
      const slice = filtered.slice(start, start + PAGE_SIZE);

      list.innerHTML = slice.map(m =>
        `<li>
          <a href="markets/${m.id}/index.html">${escHtml(m.name)}</a>
          <span class="meta"> &mdash; ${escHtml(m.city)}, ${escHtml(String(m.zip))}</span>
        </li>`
      ).join('');

      if (filtered.length === 0) {
        list.innerHTML = '<li>No markets found.</li>';
      }

      const totalPages = Math.ceil(filtered.length / PAGE_SIZE) || 1;
      pag.hidden = totalPages <= 1;
      document.getElementById('page-info').textContent =
        `Page ${currentPage + 1} of ${totalPages} (${filtered.length} result${filtered.length !== 1 ? 's' : ''})`;
      document.getElementById('prev-btn').disabled = currentPage === 0;
      document.getElementById('next-btn').disabled = currentPage >= totalPages - 1;
    }

    function escHtml(s) {
      return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
  </script>
</body>
</html>
"""


def write_landing_page(out_dir: Path) -> None:
    html = LANDING_PAGE_TEMPLATE.replace("{page_size}", str(PAGE_SIZE))
    dest = out_dir / "index.html"
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


def full_rebuild(input_dir: Path, out_dir: Path) -> None:
    print(f"[info] Full rebuild: {input_dir} -> {out_dir}")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    registry_path = input_dir / "market_registry.jsonl"
    markets = load_market_registry(registry_path)
    write_market_registry_json(markets, out_dir / "market_registry.json")
    write_landing_page(out_dir)
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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_dir = Path(args.input).resolve()
    out_dir = Path(args.out).resolve()

    if not input_dir.is_dir():
        sys.exit(f"[error] Input directory not found: {input_dir}")

    if needs_full_rebuild(input_dir, out_dir, args.changed):
        full_rebuild(input_dir, out_dir)
    else:
        changed_paths = [Path(p).resolve() for p in args.changed]
        incremental_rebuild(input_dir, out_dir, changed_paths)


if __name__ == "__main__":
    main()
