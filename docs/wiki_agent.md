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

## Entities

### Market
You want to collect knowledge about farmer's market, their location, timing, vendors and their products.

The information you need is
- Farmers Market Name
- Address
- City
- Latitude
- Longitude
- Timing  
- ZIP
- URL
- Description
- Type : Can be indoor, outdoor, mixed
- Logo : URL of the market's logo image (optional)
- Tags: Like "producer_only", "historic", etc
- Notes: For example ["Address not found" , "Hours not found"]

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
- Support vendor-centric queries by scanning all market `vendors.md` files:
    - Which markets does a vendor attend? (requires scanning all markets)

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
