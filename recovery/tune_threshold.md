# tune_threshold.py (Recovered)

## Purpose

Sweep multiple `relevance_threshold` values and evaluate retrieval quality for a knowledge base search pipeline.

The script reports:

- `hit@k`
- `mrr` (mean reciprocal rank)
- `avg_results`
- recommended threshold

## Input Dataset Format

JSONL (UTF-8), one sample per line.

Required logical fields:

- `query` (non-empty string)
- positives (at least one filename), accepted aliases:
- `positive_filenames` (list[str])
- `expected_filenames` (list[str])
- `expected_filename` (str)
- `filename` (str)

Blank lines and lines beginning with `#` are ignored.

Example:

```json
{"query":"how to reset password","positive_filenames":["account_guide.pdf"]}
{"query":"refund policy","expected_filename":"policy.docx"}
```

## CLI Arguments

- `--dataset` (required): path to JSONL file.
- `--thresholds` (optional, default `0.8,1.0,1.2,1.4,1.6`): comma-separated floats.
- `--k` (optional, default `3`): top-k retrieval.
- `--persist-dir` (optional): pass-through to `KnowledgeBase`.
- `--dimension` (optional): pass-through to `KnowledgeBase`.

## Core Logic

1. Parse thresholds, trim blanks, cast to float, deduplicate, sort.
2. Load dataset and validate each line.
3. Build KB instance:
- `KnowledgeBase(dimension=args.dimension, persist_dir=args.persist_dir)`
4. For each threshold:
- call `kb.search(query, k=args.k, relevance_threshold=threshold)`
- compute per-sample hit@k and reciprocal rank
- aggregate average metrics
5. Choose recommended threshold with score:

```text
score = hit@k * 1000 + mrr * 10 - avg_results
```

Selection priority encoded by score:

- maximize `hit@k`
- then maximize `mrr`
- then prefer smaller `avg_results`

## Metric Definitions

- `hit@k`: `1.0` if any returned filename is in positives, else `0.0`.
- `reciprocal_rank`: `1 / rank` of first relevant filename in results, else `0.0`.
- `mrr`: average reciprocal rank over all samples.
- `avg_results`: average count of returned results per sample.

## Output Format

Console output includes:

- dataset size and threshold candidates
- table header: `threshold\thit@k\tmrr\tavg_results`
- one row per threshold
- final recommendation:
- `[RECOMMENDED] relevance_threshold=<value>`
- detail line about selection rule

## Error Conditions

- Dataset path missing: `FileNotFoundError`.
- Dataset empty after filtering: `ValueError("Dataset is empty")`.
- Invalid JSON line: `ValueError("Invalid JSON at line ...")`.
- Missing `query`: `ValueError("Missing query at line ...")`.
- Missing positives: `ValueError("Missing positives at line ...")`.
- Invalid/empty thresholds: `ValueError("No valid thresholds provided")`.

