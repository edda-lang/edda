# runes

The Edda ecosystem packages — 36 runes under `lib/<name>/`, distributed through the Mímir registry as `.rune` archives. A rune is imported by its root namespace (`import json.value`, `import httpserver.router`) and declared as a `[[dependencies]]` entry in `package.toml`.

Packages: `base58`, `cli`, `cookies`, `csrf`, `css`, `dotenv`, `envconfig`, `form`, `hermod`, `html`, `httpserver`, `ini`, `json`, `jsonpointer`, `jwt`, `linalg`, `log`, `markdown`, `money`, `multipart`, `pgsql`, `regex`, `router`, `session`, `slug`, `static`, `textbuilder`, `tinysql`, `tls`, `toml`, `totp`, `ulid`, `uri`, `uuid`, `validate`, `yaml`.

The archive format, content addressing, and the three-hash versioning scheme are specified in [`../codex/language/08-packages.md`](../codex/language/08-packages.md).
