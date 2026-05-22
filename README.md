# farmles_wiki

`farmles_wiki` is the Git-reviewed knowledge repository for farmers market source evidence and curated market data.

It receives generated source markdown from `farmles_harvester`, stores it under stable source paths, and later supports extraction, review, and export of approved market information to the app database.

## Purpose

`farmles_wiki` separates two things:

```text
sources/
= what we crawled and observed

markets/
= approved real-world farmers market entities

farmles_harvester crawls websites and produces source-level markdown:
generated_wiki/
  sources/
    apexfarmersmarket-com/
      source_metadata.json
      pages/
        index.md
        vendors.md
        visit.md


farmles_wiki imports that output into the same stable structure:
farmles_wiki/
  sources/
    apexfarmersmarket-com/
      source_metadata.json
      pages/
        index.md
        vendors.md
        visit.md

Because paths are stable, Git can show clean diffs across repeated crawler runs.
```

## Source evidence

Source evidence lives under:
`sources/{source_slug}/`

Example
```
sources/apexfarmersmarket-com/
  source_metadata.json
  pages/
    index.md
    vendors.md
    visit.md
```

`source_metadata.json` contains only stable source identity fields:

```json
{
  "source_slug": "apexfarmersmarket-com",
  "input_url": "https://www.apexfarmersmarket.com/",
  "normalized_url": "https://www.apexfarmersmarket.com/",
  "final_url": "https://www.apexfarmersmarket.com/"
}
```

## Market Data

Approved market entities will live under `markets/{market_slug}_{market_id}/`

Example

```
markets/apex-farmers-market_mkt-1/
  index.md
  vendors.md
  visit.md
  market_profile.json
```

Market folders are not created directly by the crawler. They should be created through another import script.

## Registry

The file `market_registry.jsonl` is the global identity map for approved markets. It assigns a unique market_id and wiki folder to the url. This file prevents duplicate market folders and keeps market identity stable across repeated imports.

## Git Review Flow

Crawler output should be imported into `sources/` on a branch.

```
harvester output
   ↓
farmles_wiki/sources/
   ↓
git diff
   ↓
Pull Request
   ↓
human review
   ↓
merge into main
```

If regenerated source markdown is identical to what is already in main, Git shows no diff and no PR is needed.

## Tools

The folder `tools` contains the wiki side utilities.

`farmles_import_wiki.py <generated_wiki>` — Copies over the generated wiki pages into approved market folders using `market_registry.jsonl`

`farmles_export_sql.py` — Reads approved markdowns from main and exports structured data to app-specific SQL tables
