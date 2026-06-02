
## General Format
The wiki stores the relation
The wiki folder structure is organized as shown below.

```
market_registry.jsonl
vendor_registry.jsonl
   
markets
   <market_id>
      index.md
      vendors.md         
```
## Registries
Each registry assigns a global id to the entity.
It has 4 fields
- id : Unique id of the entity. Cannot be duplicate.

- name: Canonical name of the entity. Can be duplicate across entries.

- aliases: Optional list of alternate names the entity is known by (e.g. slight spelling variations, former names). Empty list if none.

- dedupe_key: Information used by the agent to distinguish entities that have the same name.  
  If the dedupe_key is missing or empty then it means that there are no duplicate name entries. 

The flow for an agent is to search `name` first, then `aliases`, and use `dedupe_key` as the match confirmer.

### market_registry.jsonl
Assigns the unique id to a farmer's market. 
A market match requires:
name match
AND
state match
AND
(city match OR zip match)

Fields:
- `id`: Unique market identifier (snake_case)
- `name`: Market name
- `state`: US state abbreviation (e.g. "NC", "CA") — required for matching
- `city`: City name
- `zip`: ZIP code

```
{"id": "apex_farmers_market", "name": "Apex Farmers Market", "city": "Apex", "state": "NC"},
{"id": "market_nc", "name": "Farmers Market", "zip": "27502", "state": "NC"},
{"id": "market_ga", "name": "Farmers Market", "city": "Atlanta", "state": "GA"},

```

### vendor_registry.jsonl
This is the authoritative source of a vendor identity by assigning a unique id to each vendor. It is possible that 2 vendors have the same name or the same vendor has multiple names.

For example
- The same business appears under slightly different names at different markets:
    - "Green Valley Farm"
    - "Green Valley Farms"
    - "Green Valley Farm LLC"
- The vendor has no website.
- The vendor changes website.

The agent must first search this to discover the vendor before creating a new vendor id.

IDs must be `snake_case` with no spaces. A numeric suffix (`_001`) is appended when needed to disambiguate entries with identical base slugs.
```
{"id": "apex_food_company_001", "name": "Apex Food Company", "aliases": ["Apex Foods", "Apex Food Co."], "dedupe_key": "Located in Apex, NC"},
{"id": "green_valley_farm_001", "name": "Green Valley Farm", "aliases": ["Green Valley Farms", "Green Valley Farm LLC"], "dedupe_key": "www.greenvalleyfarm.com"},
```

## Market Index File
The market's `index.md`  describes the market
The purpose of this is to answer:
```
Where is the market located?
When is the maket open ?
What is the brief description of this market?
```

The format of this file is described below.

```
# <market name>

## Summary
<description in few lines>

## Location

- Address: <address>
- City: <city>
- State: <state>
- ZIP: <zip_code>
- Latitude: <lat>
- Longitude: <long>
  
## Schedule
- Day: <day>
- Hours: <start> - <end>
- Season: <season active>
- Type: <indoor, outdoor, or mixed>
  
## URL
<url>

## Logo
<url of image to use>

## Tags
- <tag1>
- <tag2>
  
## First Created
< time stamp it was created>

## Last Modified
< time it was modified>

## Sources
< description of the last ingestion > 
< description of the last-1 ingestion>
```
 
## Markets Vendor 
The purpose of `vendors.md` purpose is to list the vendors selling in this market.
The purpose of this file is to answer:
```
Who sells at the market ?
What does each vendor sell at the market ?
```
The agent would
- Mark the vendor as status 'inactive' in vendors.md if it does not find it in source. 
The structure of this markets `vendors.md` is described below. Products are free-text; do not normalize them.

```
# Vendors

## <vendor_id1>

Name: <name of the vendor>
Status: <status like active, inactive>

### Products
Products sold at this market
- <item1>
- <item2>
  
### First Created
< time stamp it was created>

### Last Modified
< time it was modified>

### Sources

#### Source 1
< description of the last ingestion >

#### Source 2
< description of the last-1 ingestion >

## <vendor_id2>
.....

## <vendor_id3>
  
```
## Simple Example 1

Say there is  a market "Durham Farmer's Market" with a vendor "Green Valley Farm " selling tomatoes.
- The market registry would assign the market_id. 
```
{"id":"durham_farmers_market_001","name":"Durham Farmers Market","dedupe_key":"durham-nc"},
```

- The vendor registry would assign a unique id to vendor.
```
{"id":"green_valley_farm_001","name":"Green Valley Farm","aliases":["Green Valley Farms","Green Valley Farm LLC"],"dedupe_key":"www.greenvalleyfarm.com"},
```

- The file `markets/durham_farmers_market_001/index.md`
```
# Durham Farmers Market

## Location

- Address: 501 Foster St
- City: Durham
- State: NC
- ZIP: 27701
- Latitude: 35.9940
- Longitude: -78.8986

## Schedule
Saturday
8:00 AM - 12:00 PM

## URL
https://durhamfarmersmarket.com

## Sources 

### Source 1 
- Timestamp: 2026-05-30T18:22:00Z 
- Type: Website 
- URL: https://durhamfarmersmarket.com/vendors 
- Agent: market_ingest_agent - Notes: Confirmed Green Valley Farm listed as vendor. 
  
### Source 2 
- Timestamp: 2026-06-02T14:10:00Z 
- Type: Facebook 
- URL: https://facebook.com/... 
- Agent: social_media_agent 
- Notes: Market schedule updated for summer season.   
```

- The file `markets/durham_farmers_market_001/vendors.md` would containt
```
# Vendors

## green_valley_farm_001

Name: Green Valley Farm
Status: active

### Products
- Tomatoes

### First Created
2026-05-01T00:00:00Z

### Last Modified
2026-05-01T00:00:00Z

### Sources

#### Source 1
- Timestamp: 2026-05-01T00:00:00Z
- Type: Vendor directory page
- Last seen: 2026-05-01
```