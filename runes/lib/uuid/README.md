# uuid

UUIDs as a compact 128-bit value with the canonical text form — nil, random
`v4`, and time-ordered `v7`, plus byte and string round-trips. Reach for it
wherever you need a stable, copy-pasteable identifier.

## Install

```
edda add uuid
```

Then import the module you need:

```edda
import uuid.uuid
```

## Usage

```edda
import uuid.uuid

function new_id(rand: Random, allocator: Allocator) -> String
    with {rand, allocator, err: alloc.AllocError}
{
    let id = uuid.v4(rand, allocator)?
    return uuid.format(id, allocator)?
}
```

`uuid.v4` draws a random UUID from a `Random` capability; `uuid.v7` takes a
millisecond timestamp first (`uuid.v7(ms, rand, allocator)`) for time-ordered
ids. `uuid.parse(s, allocator)` and `uuid.from_bytes(b)` both return an
`Option_Uuid.Option` — `.none` on malformed input — and `uuid.is_valid(s, allocator)`
is the boolean shortcut.

## Public surface

- **`uuid`** — the `Uuid` type and its constructors: `nil`, `v4`, `v7`.
- **`uuid`** — text and bytes: `format` (canonical hyphenated string),
  `parse`, `to_bytes`, `from_bytes`.
- **`uuid`** — inspection: `version`, `is_valid`.
