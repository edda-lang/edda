# yaml

A YAML reader for Edda — parse a document (block mappings and sequences, flow
collections, quoted and plain scalars) into a `YamlValue` tree and pull typed
values out of it. Parsing allocates through a caller-supplied `Allocator`.

## Install

```
edda add yaml
```

Then import the modules you need:

```edda
import yaml.parse
import yaml.value.core as value
```

## Usage

```edda
import yaml.parse
import yaml.value.core as value
import std.core.option

function name_from(text: String, allocator: Allocator) -> Option_String
    with {allocator, err: error.ParseError, divergence}
{
    let doc = parse.parse(text, allocator)?
    return match doc {
        case .mapping(let m) => value.get_scalar(m, "name")
        case _               => Option_String.none
    }
}
```

`parse.parse_bytes` is the same entry point over a `[u8]` slice. Once you hold a
`Mapping`, the typed getters — `value.get_int`, `value.get_bool`,
`value.get_float`, `value.get_mapping`, `value.get_sequence` — read a key
directly, and the `is_*` / `as_*` helpers inspect any `YamlValue`.

## Public surface

- **`yaml.parse`** — `parse` (from a `String`) and `parse_bytes` (from `[u8]`)
  are the top-level entry points that build a `YamlValue`.
- **`yaml.error`** — the `ParseError` enum (`bad_indentation`, `missing_colon`,
  `tab_indentation`, …) reported when a document is malformed.
- **`yaml.value.core`** — the `YamlValue` / `Mapping` / `Sequence` /
  `MappingEntry` types, scalar tests (`is_int`, `is_mapping`, …) and extractors
  (`as_bool`, `as_int`, `as_str`, …), and mapping access (`get`, `has`, `len`,
  plus the typed `get_scalar` / `get_int` / `get_bool` / `get_mapping` /
  `get_sequence` getters).
- **`yaml.parse.flow`** / **`yaml.parse.scalar`** / **`yaml.parse.scan`** — the
  low-level flow-collection parser, scalar classifier, and byte scanner the
  top-level parse is built on.
