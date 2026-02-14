# knowledge-base (Recovered)

Recovered from available bytecode and session history.

## Files

- `encrypt_secret.py`: encrypt plain text for config usage.
- `tune_threshold.py`: sweep retrieval threshold with eval JSONL dataset.
- `src/secret_cipher.py`: Fernet helpers.
- `src/knowledge_base.py`: lightweight lexical retrieval backend.

## Quick Start

```bash
venv\Scripts\python.exe encrypt_secret.py --text "my_secret"
venv\Scripts\python.exe tune_threshold.py --dataset eval_dataset.example.jsonl
```

## Dataset Format (for tune_threshold.py)

JSONL, one item per line:

```json
{"query":"reset password","positive_filenames":["account_guide.md"]}
```

Accepted positive filename fields:

- `positive_filenames` (list[str])
- `expected_filenames` (list[str])
- `expected_filename` (str)
- `filename` (str)

