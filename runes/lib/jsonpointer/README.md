# jsonpointer

RFC 6901 JSON Pointer resolution — walk a parsed JSON value by a `/`-separated
pointer string, with the `~0` / `~1` token escaping the spec mandates. Pairs with
the `json` rune, whose `JsonValue` it navigates.

## Install

```
edda add jsonpointer
```

Then import the module you need:

```edda
import jsonpointer.resolve
import jsonpointer.escape
```

## Usage

```edda
import std.core.option
import std.mem.alloc
import json.value.core as jvcore
import jsonpointer.resolve

spec std.core.option.Option(jvcore.JsonValue)

function lookup(root: jvcore.JsonValue, pointer: String, allocator: Allocator) -> Option_JsonValue
    with {allocator, err: alloc.AllocError, divergence}
{
    return resolve.resolve(root, pointer, allocator)
}
```

`resolve.resolve` returns `.none` when any token along the pointer is missing or an
array index is out of range. `resolve.has(root, pointer, allocator)` answers the same
walk as a `bool`. Object member names are unescaped per RFC 6901 before matching, so
`/a~1b` addresses the member literally named `a/b`.

## Public surface

- **`resolve`** — `resolve` (pointer walk yielding `Option_JsonValue`) and `has` (existence check). Both take the pointer `String` plus an `Allocator`.
- **`escape`** — token codec: `escape_token` (encode `~`/`/` → `~0`/`~1`), `unescape_token`, and `unescape_bytes`.
