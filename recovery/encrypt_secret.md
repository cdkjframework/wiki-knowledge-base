# encrypt_secret.py (Recovered)

## Purpose

Encrypt a plain text secret and print:

- `KEY=<fernet_key>`
- `CIPHER=<encrypted_text>`

Intended usage says: `Encrypt secrets for config.json`.

## CLI Arguments

- `--text` (required): plain text to encrypt.
- `--key` (optional, default empty string): existing Fernet key.

If `--key` is empty after trim, the script generates a new key via `generate_key()`.

## Runtime Behavior

1. Adds `<current_dir>/src` to `sys.path` if missing.
2. Imports from `secret_cipher`:
- `encrypt_text`
- `generate_key`
3. Resolves key:
- use provided `--key` if non-empty
- otherwise auto-generate
4. Encrypts using `encrypt_text(args.text, key)`.
5. Prints key and cipher to stdout.

## Example

```bash
python encrypt_secret.py --text "my_password"
python encrypt_secret.py --text "my_password" --key "base64_fernet_key_here"
```

## Dependencies

- Local module: `src/secret_cipher.py`
- Expected functions:
- `generate_key() -> str`
- `encrypt_text(text: str, key: str) -> str`

