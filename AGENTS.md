# AGENTS.md - APEX Knowledge Graph Project

## Quick Start

```bash
cd code

# MetaQA (pre-generated queries, fastest)
python main.py --kg MetaQA --method apex apex-n --percent-triples 0.0001 --n_users 1

# DBpedia / YAGO (requires large datasets, see README for download)
python main.py --kg DBpedia --method apex apex-n --save-queries --percent-triples 0.000001 --n_users 1
python main.py --kg YAGO --method apex apex-n --save-queries --percent-triples 0.000001 --n_users 1
```

## Key Files

- **Entry point**: `code/main.py`
- **Path config**: `code/src/path.py` (relative paths to PKG_EXP datasets)
- **Core algorithms**: `code/src/apex.py`, `code/src/base.py`

## Important Quirks

- **`--save-queries` triggers pdb prompt**: The script calls `pdb.set_trace()` and asks "是否继续？" (continue?). Hit `c` + Enter to proceed.
- **MetaQA auto-loads queries**: `args.save_queries = False` and `args.load_queries = True` are forced.
- **Datasets not included**: DBpedia and YAGO require manual download (see README for links).
- **Results in log.log**: Check for "Ave Time on Each Training Log" and "Ave Ave F1 on Each Training Log".
- **No test suite**: No pytest/unit tests in this repo.