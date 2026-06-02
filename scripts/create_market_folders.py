import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
INGESTION_DATE = "2026-06-02"
SKIP_DIFF_FIELDS = {"id"}  # UUID differs by nature; not meaningful to compare


def load_registry(path: Path) -> tuple[dict, dict]:
    by_name_state_city: dict[tuple[str, str, str], str] = {}
    by_name_state_zip: dict[tuple[str, str, str], str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line.strip())
            state = entry.get("state", "").lower()
            key_city = (entry["name"].lower(), state, entry["city"].lower())
            key_zip = (entry["name"].lower(), state, entry["zip"])
            by_name_state_city[key_city] = entry["id"]
            by_name_state_zip[key_zip] = entry["id"]
    return by_name_state_city, by_name_state_zip


def parse_tags(raw: str) -> list[str]:
    try:
        tags = json.loads(raw)
        return [str(t) for t in tags] if isinstance(tags, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def render_index(row: dict) -> str:
    tags = parse_tags(row.get("tags", "[]"))
    tag_lines = "\n".join(f"- {t}" for t in tags) if tags else ""
    logo = row.get("live_image_url", "").strip() or row.get("image_url", "").strip()
    return f"""# {row['name']}

## Summary
{row.get('description', '').strip()}

## Location
- Address: {row.get('address', '').strip()}
- City: {row.get('city', '').strip()}
- State: {row.get('state', '').strip()}
- ZIP: {row.get('zip', '').strip()}
- Latitude: {row.get('lat', '').strip()}
- Longitude: {row.get('lng', '').strip()}

## Schedule
- Day: {row.get('day_open', '').strip()}
- Hours: {row.get('hours', '').strip()}
- Season: {row.get('dates_open', '').strip()}
- Type: {row.get('indoor_outdoor', '').strip()}

## URL
{row.get('website', '').strip()}

## Logo
{logo}

## Tags
{tag_lines}

## First Created
{row.get('created_at', '').strip()}

## Last Modified
{row.get('updated_at', '').strip()}

## Sources
- Type: backend.csv
- Source: {row.get('source', '').strip()}
- Ingested: {INGESTION_DATE}
"""


def write_duplicates_report(
    duplicates: list[tuple[str, int, dict, int, dict]], out_path: Path
) -> None:
    lines = [
        "# Duplicate Markets Report",
        "",
        f"Generated: {INGESTION_DATE}",
        "",
        f"{len(duplicates)} duplicate market IDs found.",
        "",
    ]
    for market_id, line1, row1, line2, row2 in duplicates:
        lines.append(f"---")
        lines.append("")
        lines.append(f"## {market_id}")
        lines.append("")

        diffs = {
            field: (row1.get(field, ""), row2.get(field, ""))
            for field in row1
            if field not in SKIP_DIFF_FIELDS and row1.get(field, "") != row2.get(field, "")
        }

        if not diffs:
            lines.append("✅ All fields identical.")
        else:
            lines.append(f"| Field | Row 1 (line {line1}) | Row 2 (line {line2}) |")
            lines.append("|---|---|---|")
            for field, (v1, v2) in diffs.items():
                lines.append(f"| {field} | {v1} | {v2} |")

        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main(force: bool = False) -> None:
    registry_path = ROOT / "wiki" / "market_registry.jsonl"
    csv_path = ROOT / "backend.csv"
    markets_dir = ROOT / "wiki" / "markets"

    by_name_state_city, by_name_state_zip = load_registry(registry_path)

    created = 0
    unmatched = 0
    first_seen: dict[str, tuple[int, dict]] = {}
    duplicates: list[tuple[str, int, dict, int, dict]] = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for line_number, row in enumerate(reader, start=2):  # 2: header is line 1
            name = row["name"].strip()
            city = row["city"].strip()
            state = row["state"].strip()
            zip_code = row["zip"].strip()

            market_id = (
                by_name_state_city.get((name.lower(), state.lower(), city.lower()))
                or by_name_state_zip.get((name.lower(), state.lower(), zip_code))
            )
            if not market_id:
                print(f"WARNING: no registry match for '{name}' ({city}, {zip_code})", file=sys.stderr)
                unmatched += 1
                continue

            if market_id in first_seen:
                orig_line, orig_row = first_seen[market_id]
                duplicates.append((market_id, orig_line, orig_row, line_number, row))
                continue

            first_seen[market_id] = (line_number, row)

            folder = markets_dir / market_id
            folder.mkdir(parents=True, exist_ok=True)

            index_path = folder / "index.md"
            if index_path.exists() and not force:
                continue

            index_path.write_text(render_index(row), encoding="utf-8")
            created += 1

    if duplicates:
        report_path = markets_dir / "duplicates.md"
        write_duplicates_report(duplicates, report_path)
        print(f"Duplicates report written to {report_path}")

    print(f"Done: {created} created, {len(duplicates)} duplicates reported, {unmatched} unmatched")


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    main(force=force_flag)
