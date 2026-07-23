# json

A JSON reader and writer for Edda — parse a document into a `JsonValue` tree,
walk it with typed accessors, and encode any tree back to compact or
pretty-printed text. Everything allocates through a caller-supplied `Allocator`,
so the library never reaches for ambient memory.

## Install

```
edda add json
```

Then import the modules you need:

```edda
import json.parse.parser
import json.value.core as value
import json.encode.encoder
```

## Usage

```edda
import json.parse.parser
import json.value.core as value
import std.core.option

function port_from(text: String, allocator: mutable Allocator) -> Option_i64
    with {allocator, err: parser.ParseError, divergence}
{
    let doc = parser.parse_string(text, mutable allocator)?
    return match value.obj_get(doc, "port") {
        case .some(let v) => match value.as_num(v) {
            case .some(let n) => Option_i64.some(n as i64)
            case .none        => Option_i64.none
        }
        case .none => Option_i64.none
    }
}
```

`parser.parse_bytes` takes a `[u8]` slice instead of a `String`, and
`parser.parse` accepts a pre-lexed token stream from `lexer.lex`. To go the
other direction, `encoder.encode_to_string(take v, mutable allocator)` renders a
tree to compact JSON, `encoder.encode_to_bytes` returns `[u8]`, and
`encoder.encode_pretty(take v, indent, mutable allocator)` indents by `indent`
spaces per level.

## Public surface

- **`json.parse.parser`** — `parse_string` / `parse_bytes` / `parse` build a
  `JsonValue` from text, a byte slice, or a token stream; the `ParseError` enum
  reports where a document is malformed.
- **`json.parse.lexer`** — `lex` tokenises raw bytes into `[Token]`; `Token` and
  `LexError` are the low-level scanning surface behind `parse`.
- **`json.value.core`** — the `JsonValue` / `JsonObjectEntry` types plus the
  reader API: constructors (`null_v`, `bool_v`, `num_v`, `str_v`), tests
  (`is_num`, `is_obj`, …), extractors (`as_bool`, `as_num`, `as_str`), object
  and array access (`obj_get`, `obj_has_key`, `arr_at`, `arr_len`, `get_path`),
  and structural `equals`.
- **`json.value.arr`** / **`json.value.obj`** — builders for array and object
  values (`arr_of`, `arr_empty`, `obj_of`, `obj_empty`, …).
- **`json.encode.encoder`** — `encode_to_string` / `encode_to_bytes` /
  `encode_pretty` serialise a tree; `EncodeError` reports a write failure.
