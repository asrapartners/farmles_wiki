# Wiki Agent

## Purpose
Your purpose is to read source evidence from a source folder and write a clean, organized, entity shaped representation under output folder 'wiki'.

At a high level the core relation is Market <-> Vendor with products as details on the relation.

```
Market has many Vendors
Vendor can appear in many Markets
Vendor sells Products within a specific Market
```

The wiki is the authoritative source of information in human readable format. Queries to it are market-centric.   

## Agent Contract

### Trigger
Run this agent when new source evidence is available for one or more farmers market and the wiki needs to be created or modfied.

### Input 
The agent receives one of the following
- `source root`: Folder containing source evidence files from a scraper or harvester.
- csv file: File lists all the available markets with their meta information.
- `wiki_root` existing wiki folder to read and update.
### Output
The agent updates the files under `wiki_root`:
- `market_registry.jsonl` for looking up and adding new market.
- `vendor_registry.jsonl` for looking up and adding new vendors.
### Write Behaviour
- Match existing markets before creating new market_id in `market_registry.jsonl`
- Match existing vendors before creating new vendor_id in `vendor_registry.jsonl`
- Append source evidence to `sources`
- Do not delete existing source history
## Entities

### Market
You want to collect knowledge about farmer's market, their location, timing, vendors and their products.

The information you need is
- Farmers Market Name
- Address (may be "Address not found")
- City
- Latitude (leave empty if not found)
- Longitude (leave empty if not found)
- Timing (may be "Hours not found")
- ZIP (leave empty if not found)
- URL
- Description
- Type : Can be indoor, outdoor, mixed
- Logo : URL of the market's logo image (optional)
- Tags: Like "producer_only", "historic", etc
- Notes: Collect all "not found" signals here, e.g. ["Address not found", "Hours not found"]

In general a farmer market has many vendors. A vendor can be in multiple markets. A vendor has many products.

### Vendor

A vendor represents a business, farm, producer, artisan, food maker, or seller that participates in one or more farmers markets.

The vendor is a global entity within the wiki and is identified by a unique `vendor_id` stored in `vendor_registry.jsonl`.

Purpose:

- Provide a stable identity for a seller across all markets.
- Allow multiple markets to reference the same vendor.
- Prevent duplicate vendor records when the same vendor appears at multiple markets.
- Support market-centric queries such as:
    - Which vendors sell at a market?
    - What products does a vendor sell at a market?
- Support vendor-centric queries by scanning all selected market `vendors.md` files (like near me):
    - Which markets does a vendor attend? (requires scanning all nearby markets)

Identity Rules:

- A vendor represents the business or organization itself, not a specific market participation.
- A vendor may sell at multiple markets.
- A vendor retains the same `vendor_id` across all markets.
- Vendors with the same name may exist and are distinguished using the `dedupe_key`.
- The registry is the authoritative source of vendor identity.

Examples:

- A farm selling produce.
- A baker selling bread and pastries.
- A meat producer.
- A honey producer.
- A prepared-food vendor.
- A craft or artisan seller.

Examples of vendor identities:

- Green Valley Farm
- Apex Food Company
- Smith Family Orchards
- Carolina Honey Co.
- Sunrise Bakery

Market-specific information such as products sold at a particular market is stored in that market's `vendors.md` file rather than in the vendor registry.

### Product

The `Products` list contains free-text descriptions of products sold by the vendor at this market.

Purpose:

- Capture what the vendor sells without requiring a global product taxonomy.
- Preserve information that may be lost during normalization.
- Provide enough context for future agents and users to understand the offering.

Rules:

- Products are stored as free text.
- Product names should be descriptive enough for an agent to understand the item being sold.
- Do not attempt to normalize products into canonical product ids.
- Preserve useful qualifiers when available.
- Avoid overly generic entries when a more specific description is known.

Good examples:

```
- Red tomatoes
- Heirloom tomatoes
- Cherry tomatoes
- Fresh pasture-raised eggs
```

## Schema
Refer to [[knowledge_map_schema]] for more details.

## Steps To Follow

1. Read the source evidence and identify all farmers markets described in the source.

2. For each market to be considered it must have a name and a `city` or `zip` where it is located. If name + one of address attribute  is missing then the market must be skipped.
   - Search `market_registry.jsonl` for a matching market using:
	1. Compare the source market name against:
	   - `name`

	2. A market is considered a match only if the name matches and at least one location field also matches:
		   - `city`
		   - `zip`

	3.  If the name matches but neither `city` nor `zip` matches, do not treat it as the same market.
	   
3. If no confident match is found, create a new market entry.
     - `name`
     - `id`
     - `city`, `zip`
   - If a matching market is found, use the existing `market_id`.
   - If no matching market is found, create a new entry in `market_registry.jsonl` and assign a new `market_id`.
     
4. Use the `market_id` to locate the market folder:

   ```
   wiki/markets/<market_id>
   ```

   Create the folder if it does not already exist.

5. Extract all market information available from the source evidence and create or update:

   ```
   wiki/markets/<market_id>/index.md
   ```

   using the schema defined in `knowledge_map_schema`.

6. Extract all vendors associated with the market.

7. For each vendor:
   - Search `vendor_registry.jsonl` for a matching vendor using:
     - `name`
     - `aliases`
     - `dedupe_key`
   - If a matching vendor is found, use the existing `vendor_id`.
   - If no matching vendor is found, create a new entry in `vendor_registry.jsonl` and assign a new `vendor_id`.

7. For each vendor, extract:
   - Vendor name
   - Vendor status (if known)
   - Products sold at this market
   - Supporting source evidence

8. Create or update:

   ```
   wiki/markets/<market_id>/vendors.md
   ```

   using the schema defined in `knowledge_map_schema`.

9. Record all source evidence used to support the extracted information in the appropriate `Sources` section.

10. Write all updates back to the wiki. The only files that may be modified are:

    - `market_registry.jsonl`
    - `vendor_registry.jsonl`
    - `wiki/markets/<market_id>/index.md`
    - `wiki/markets/<market_id>/vendors.md`

