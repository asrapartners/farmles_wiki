import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


def slugify(text: str) -> str:
    text = text.lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", "_", text.strip())
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def build_registry():
    csv_path = ROOT / "backend.csv"
    out_path = ROOT / "wiki" / "market_registry.jsonl"

    seen: dict[str, int] = {}  # slug -> count of uses
    rows = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["name"].strip()
            city = row["city"].strip()
            state = row["state"].strip()
            zip_code = row["zip"].strip()

            base_slug = slugify(name)
            if base_slug not in seen:
                market_id = base_slug
            else:
                market_id = f"{base_slug}_{slugify(city)}"

            # If still a collision after appending city, add a counter
            if market_id in seen:
                seen[market_id] = seen.get(market_id, 0) + 1
                market_id = f"{market_id}_{seen[market_id]}"

            seen[base_slug] = seen.get(base_slug, 0) + 1
            seen[market_id] = 1

            rows.append({"id": market_id, "name": name, "city": city, "state": state, "zip": zip_code})

    with open(out_path, "w", encoding="utf-8") as f:
        for entry in rows:
            f.write(json.dumps(entry) + "\n")

    print(f"Written {len(rows)} entries to {out_path}")


if __name__ == "__main__":
    build_registry()
