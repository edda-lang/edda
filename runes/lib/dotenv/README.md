# dotenv

`.env` file parsing — the `KEY=value` convention for pulling configuration and
secrets out of source and into the environment, with `export ` prefixes and
surrounding quotes stripped so a file written for a shell loads unchanged.

## Install

```
edda add dotenv
```

Then import the module you need:

```edda
import dotenv.lib
```

## Usage

```edda
import dotenv.lib

function db_url(fs: ReadOnlyFilesystem, allocator: Allocator) -> Option_String
    with {fs, allocator, err: alloc.AllocError, err: fs.FsError}
{
    let pairs = lib.load(fs, ".env", allocator)?
    return lib.get(pairs, "DATABASE_URL")
}
```

`lib.load` reads and parses a file in one step; `lib.parse(content, allocator)`
does the same over an in-memory `String` you already hold. Both yield a
`[Pair]`, and `lib.get(pairs, key)` looks a single key up, returning
`Option_String`.

## Public surface

- **`lib`** — `load` (read + parse a file via `ReadOnlyFilesystem`), `parse`
  (parse a `String`), and `get` (key lookup over the parsed `[Pair]`), plus the
  `Pair` record (`key` / `value`).
