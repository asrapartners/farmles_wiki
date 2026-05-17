# farmles_wiki

`farmles_wiki` is the curated markdown knowledge base for farmer's market information.

It stores the approved market pages and the global market registry. It is the human/editor reviewed layer between the crawler output and the future strucured data.

## Purpose

use normal Git branches and Pull Requests to safely handle updates from multiple runs and agents.

```
main = approved wiki
branches = proposed changes
Pull Requests = review and merge gate

## Recommended Flow
Start from the latest main.

```bash
 git checkout main
 git pull origin main
```

Then create the branch for import

```bash
 git checkout -b 2026-05-17-00_initial_import
```

Then import the generated wiki output by another tool like crawler.
```bash
  python tools/import_wiki.py <generated_wiki_dir>
```

Review locally using git flow.
```
  git status
  git diff
```

Commit and push the changes
```
  git add .
  git commit -m "imported wiki update"
  git push -u origin 2026-05-17-00_initial-import
```

Open a pull request into main
The editor review the PR in GitHub

The editor can
- approve and merge
- edit files in PR
- close the PR if the import is wrong.

Merging means that the imported wiki changed are approved.

## Key Concepts
The file 'market_registry.jsonl" is the global identify map for approved markets. It assigns a unique market_id and wiki folder to the url.  This file prevents duplicates market folders and keeps market identity stable across repeated imports. 

The folder `markets` stores the approved market pages.
Folder naming rules
```
 markets/{market_slug}_{market_id}/
```

A canonical example is
```
  markets/apex-farmers-market-1/
    index.md
   vendors.md
```

The folder tools contains the wiki side utilities
```
farmles_import_wiki.py <generated_wiki> : Copies over the generated wiki pages into approved market folders using 'market_registry.jsonl'

farmles_export_sql.py : Tool reads approved markdowns from main and export structure data to app specific SQL tables

