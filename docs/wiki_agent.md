# WikiKarpathy Agent

## Purpose
Your purpose is to read source evidence from a source folder and write a clean, organized, entity shaped representation under output folder 'wiki'. The source folder contains the canonical urls from which the information was extracted. The URL may refer to a single market or can be an aggregate that refers to multiple markets.

## Core Mental Model
You want to collect knowledge about farmer's market, their location, timing, vendors and their products.
The information you need is
- Farmers Market Name
- Address
- City
- Latitude
- Longitude
- Timing  
- zip code
- Website
- Description
- Type : Can be indoor, outdoor, mixed
- Tags: Like "producer_only", "historic", etc
- Notes: For example ["Address not found" , "Hours not found"]

It should link to vendors with attributes like
- Vendor Name
- Description
- Products

In general a farmer market has many vendors. A vendor can be in multiple markets. A vendor has many products.

## Input Format
The input source folder has the general structure. 
```text
{source_slug}/
   source_metadata.json
   index.md
   about/
     index.md
```

The 'source_metadata.json' has the field "final_url" that points to the url that was crawled to generat the folder.

## Output Format
The agent in the `wiki` folder will create the following structure.
- Each market should have a cononical folder under `markets` represented by {market_slug}
- Each vendor should have a canonical folder under `vendors` represented by {vendor_slug} 

Each market has link to the vendors that operate in that market. Store products in two places
- in the vendor folder for what the vendor generally sells.
- in the markets folder for what the vendors sells at a specific market.


```
{source_slug}/
   index.md

   markets/
     {market_slug}/
       index.md
       vendors.md

    vendors/
       {vendor_slug}/
         index.md
         products.md
         markets.md
    

Marpet page links to vendors. Vendors page link back to markets.

if the source folder is an aggregator then it will have multiple markets.
For example a source_slug of src_agg with 2 markets `a` and `b` will be
```
src_agg/
  index.md

  markets/
    a/
      index.md
      vendors.md
    b/
      index.md
      vendors.md
  vendors/
  ```


### Example Market index.md format

AN example market md file is 
```
# Pleasanton Farmers Market

## Basic Info

| Field | Value |
|---|---|
| Farmers Market Name | Pleasanton Farmers Market |
| Address | 46 W Angela Street |
| City | Pleasanton |
| State | CA |
| Zip Code | 94566 |
| Latitude | null |
| Longitude | null |
| Timing | Saturdays, 9:00 AM – 1:00 PM |
| Website | https://example.com/pleasanton-farmers-market |
| Type | outdoor |
| Tags | producer_only, historic |
| Status | active |

# Vendors

| Vendor | Products | Notes |
|---|---|---|
| [Smith Farm](../../vendors/smith-farm/index.md) | Vegetables, eggs | Confirmed from source |
| [Blue Ridge Bakery](../../vendors/blue-ridge-bakery/index.md) | Bread, pastries | Confirmed from source |
| [All Farm](../../vendors/all-farm/index.md) | Same as vendor profile: [products](../../vendors/all-farm/products.md) | `sources/.../pleasanton.md` |

## Description

Pleasanton Farmers Market is a weekly outdoor farmers market serving the Pleasanton community. The market includes local farms, food vendors, and seasonal products.

## Location

- Address: 46 W Angela Street, Pleasanton, CA 94566
- Latitude: unknown
- Longitude: unknown

## Timing

- Day: Saturday
- Hours: 9:00 AM – 1:00 PM
- Season: Year-round

## Vendors

See: [vendors.md](vendors.md)

## Notes

- Latitude not found
- Longitude not found
- Vendor list incomplete

## Source Evidence

- Source: `sources/pcfma-org/pages/pleasanton.md`
- Source URL: https://example.com/pleasanton-farmers-market
``` 

## Ingest Notes

### Purpose

During ingestion the agent MUST write a `_ingest_notes.json` file alongside `index.md` in each entity folder. This file records machine-readable signals about data quality, provenance, and gaps so that post-processing scripts can queue remediation work without re-parsing prose text.

Run `python3 tools/process_ingest_notes.py wiki/` to get a summary report across all entities.

### When to write notes

Write a note for each of the following situations:

| Situation | Note type | Remediation |
|---|---|---|
| A field in the Basic Info table is `null`, `unknown`, or absent | `gap` | see field rules below |
| A field value was derived indirectly (parsed URL, inferred from context) | `provenance` | `null` unless verification needed |
| The agent filled a value based on an unconfirmed assumption | `assumption` | `manual_verify` |
| The source mentions an entity (market or vendor) with no wiki slug yet | `unresolved_reference` | `cross_reference` |

**Field-level remediation rules for gaps:**

| Field | Condition | Remediation |
|---|---|---|
| `vendor_list` | Page requires JavaScript to render | `js_crawl` |
| `latitude` / `longitude` | Address is known | `geo_lookup` |
| `latitude` / `longitude` | No address available | `manual_verify` |
| anything else | — | `manual_verify` |

### File location

Always write `_ingest_notes.json` inside the entity folder, even when `notes` is empty — an empty array is a positive signal that the agent found no gaps.

```
wiki/markets/{market_slug}/_ingest_notes.json
wiki/vendors/{vendor_slug}/_ingest_notes.json
```

### Schema

```json
{
  "schema_version": "1",
  "entity_type": "market | vendor",
  "entity_slug": "<slug>",
  "ingested_at": "<ISO-8601 UTC, e.g. 2026-05-25T00:00:00Z>",
  "notes": [
    {
      "type": "gap | provenance | assumption | unresolved_reference",
      "field": "<field name, or '*' for entity-level>",
      "message": "<human-readable prose — mirrors the ## Notes section of index.md>",
      "remediation": "js_crawl | geo_lookup | manual_verify | cross_reference | null",

      "severity": "blocking | minor",        // gap only — blocking if entity is incomplete without it
      "method": "<how value was derived>",   // provenance only
      "source_url": "<URL or null>",         // provenance only
      "assumed_value": "<value used>",       // assumption only
      "referenced_name": "<raw name>",       // unresolved_reference only
      "reference_context": "<source text>"   // unresolved_reference only
    }
  ]
}
```

### Rules

1. Always write `_ingest_notes.json` even if `notes` is empty.
2. `ingested_at` must be UTC ISO-8601 with Z suffix.
3. `message` should match what appears in `## Notes` of `index.md`. The duplication is intentional — prose for humans, JSON for scripts.
4. Use `severity: "blocking"` only when the entity is fundamentally incomplete without the field (e.g., no vendor entries at all for a market).
5. `remediation` is always present; use `null` explicitly when no automated fix applies.

