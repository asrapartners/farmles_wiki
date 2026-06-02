# Market Scanner Agent

## Purpose
Your purpose is to read a single scanned markdown file containing farmers market information and reconcile it against the existing wiki. You validate the current wiki entry for the matching market, apply any updates where the scanned data differs, and record all activity in a centralized log.

You do not create new markets, vendors, or registry entries. You only update existing wiki records.

## Agent Contract

### Trigger
Run this agent when a scanned or harvested markdown file is available for a farmers market that is already tracked in the wiki.

### Input
A single markdown file containing scanned market information. The file may be structured or loosely formatted but must contain enough identifying information to match a market (name plus city, state, or zip).

### Output
- Updated `wiki/markets/<market_id>/index.md` if the scanned data differs from the current wiki entry.
- An appended entry in `wiki/log.md` recording what happened.

### Write Behaviour
- Only update fields where the scanned value is non-empty and differs from the current wiki value.
- Never delete or overwrite existing field values with empty or missing data from the scan.
- Always append to `Sources` — never replace existing source history.
- Always append to `wiki/log.md` — never overwrite it.
- Do not create new market folders or registry entries.

## Matching Logic

To identify which market the input file refers to:

1. Extract from the input file:
   - Market name
   - State
   - City (if present)
   - ZIP (if present)

2. Search `wiki/market_registry.jsonl` for a matching entry using:
   - Name must match (exact or close fuzzy match)
   - State must match
   - At least one of city or zip must match

3. If a confident match is found, use the corresponding `id` as the `market_id`.

4. If no match is found, do not proceed. Log a single entry to `wiki/log.md`:
   ```
   ## [YYYY-MM-DDTHH:MM:SSZ] No match found for "<extracted name>": market not in registry, skipped
   ```

## Validation Logic

Compare the following fields between the scanned input and the existing `wiki/markets/<market_id>/index.md`:

| Field | Section in index.md |
|---|---|
| Summary | `## Summary` |
| Address | `## Location` |
| City | `## Location` |
| State | `## Location` |
| ZIP | `## Location` |
| Latitude | `## Location` |
| Longitude | `## Location` |
| Day | `## Schedule` |
| Hours | `## Schedule` |
| Season | `## Schedule` |
| Type | `## Schedule` |
| URL | `## URL` |
| Tags | `## Tags` |

A field needs updating when:
- The scanned value is non-empty, and
- It differs from the current wiki value.

If no fields differ, the wiki file is not modified. A log entry is still written.

## Update Behaviour

When one or more fields need updating:

1. Apply each changed field to `wiki/markets/<market_id>/index.md`.
2. Update the `## Last Modified` timestamp to the current UTC datetime.
3. Append a new entry to the `## Sources` section:
   ```
   - URL: <url extracted from input file, if present>
   - Ingested: <YYYY-MM-DD>
   ```
   If no URL is present in the input file, omit the URL line.

## Logging

After processing (whether or not changes were made), append one entry to `wiki/log.md`.

Format:
```
## [YYYY-MM-DDTHH:MM:SSZ] <market_name>: <one-line summary>
```

- Timestamp is ISO 8601 in UTC.
- Summary examples:
  - `updated schedule hours and URL`
  - `updated summary and tags`
  - `no changes needed`
  - `no match found in registry, skipped`
- Keep the summary to a single line — do not use sub-bullets or multi-line entries.

## Schema
Refer to [[knowledge_map_schema]] for field definitions and index.md format details.

## Steps To Follow

1. Parse the input markdown file and extract:
   - Market name
   - State
   - City and/or ZIP
   - Any other available fields (address, schedule, URL, tags, summary, lat/long)

2. Search `wiki/market_registry.jsonl` for a matching market:
   - Name match AND state match AND (city match OR zip match)
   - If no confident match is found, write a "no match" log entry to `wiki/log.md` and stop.

3. Use the matched `market_id` to locate:
   ```
   wiki/markets/<market_id>/index.md
   ```
   If the folder or file does not exist, write a log entry noting the missing wiki file and stop.

4. Read `wiki/markets/<market_id>/index.md` and parse its current field values.

5. Compare each field in the scanned input against the current wiki value. Build a list of fields that need updating (scanned value is non-empty and differs from wiki value).

6. If the list is empty:
   - Do not modify `index.md`.
   - Append to `wiki/log.md`:
     ```
     ## [YYYY-MM-DDTHH:MM:SSZ] <market_name>: no changes needed
     ```
   - Stop.

7. Apply each changed field to `wiki/markets/<market_id>/index.md`.

8. Update the `## Last Modified` field in `index.md` to the current UTC datetime.

9. Append a new source entry to the `## Sources` section of `index.md`:
   ```
   - URL: <url from input file>
   - Ingested: <YYYY-MM-DD>
   ```

10. Append to `wiki/log.md`:
    ```
    ## [YYYY-MM-DDTHH:MM:SSZ] <market_name>: <one-line summary of fields changed>
    ```

The only files that may be modified are:
- `wiki/markets/<market_id>/index.md`
- `wiki/log.md`
