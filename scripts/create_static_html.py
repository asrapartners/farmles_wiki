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

  Steps: convert only the changed .md files to their matching .html paths.
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
# Markdown conversion
# ---------------------------------------------------------------------------

def extract_title(source: str, fallback: str) -> str:
    for line in source.splitlines():
        m = re.match(r"^#\s+(.+)", line)
        if m:
            return m.group(1).strip()
    return fallback


def md_to_html(source: str, title: str) -> str:
    try:
        import markdown as md_lib
    except ImportError:
        sys.exit("[error] The 'markdown' package is not installed. Run: pip install markdown")
    body = md_lib.markdown(source, extensions=["tables", "fenced_code"])
    return (
        "<!doctype html>\n"
        "<html>\n"
        "<head>\n"
        f'  <meta charset="utf-8">\n'
        f"  <title>{title}</title>\n"
        "</head>\n"
        "<body>\n"
        '  <p><a href="../../index.html">← Back to Markets</a></p>\n'
        f"  {body}\n"
        "</body>\n"
        "</html>\n"
    )


def convert_md_file(md_path: Path, html_path: Path) -> None:
    try:
        source = md_path.read_text(encoding="utf-8")
    except OSError as exc:
        sys.exit(f"[error] Cannot read {md_path}: {exc}")
    title = extract_title(source, md_path.stem)
    html = md_to_html(source, title)
    try:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
    except OSError as exc:
        sys.exit(f"[error][exit:2] Cannot write {html_path}: {exc}")


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
        out_market_dir = out_dir / "markets" / market_dir.name
        for md_name, html_name in [("index.md", "index.html"), ("vendors.md", "vendors.html")]:
            md_path = market_dir / md_name
            if md_path.exists():
                convert_md_file(md_path, out_market_dir / html_name)


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
    md_files = [
        p for p in changed_paths
        if p.suffix == ".md" and markets_prefix in p.parents
    ]
    if not md_files:
        print("[info] No market Markdown files in --changed; nothing to do.")
        return

    print(f"[info] Incremental rebuild: {len(md_files)} file(s)")
    for md_path in md_files:
        # Derive output path: input/markets/<id>/foo.md -> out/markets/<id>/foo.html
        rel = md_path.relative_to(input_dir)
        html_path = out_dir / rel.with_suffix(".html")
        convert_md_file(md_path, html_path)
        print(f"[info]   {md_path} -> {html_path}")


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
            "files are market Markdown files, only those files are regenerated "
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
