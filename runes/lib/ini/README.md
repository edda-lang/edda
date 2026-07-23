# ini

INI configuration parsing — the `[section]` / `key = value` format used by
countless tools' config files — into a structured `Ini` you can query by
section and key.

## Install

```
edda add ini
```

Then import the modules you need:

```edda
import ini.parse
import ini.value
```

## Usage

```edda
import ini.parse
import ini.value

function server_host(content: String, allocator: Allocator) -> Option_String
    with {allocator, err: alloc.AllocError}
{
    let cfg = parse.parse(content, allocator)?
    return value.get(cfg, "server", "host")
}
```

`parse.parse` turns the raw file text into an `Ini`. From there `value.get(ini,
section, key)` looks a single entry up (returning `Option_String`), and
`value.sections(ini)` returns every `[Section]` for iterating the whole file.

## Public surface

- **`parse`** — `parse`, which reads a config `String` into an `Ini`.
- **`value`** — the `Ini`, `Section`, and `Pair` types plus the readers
  `get` (section + key lookup) and `sections` (all parsed sections).
