# ulid

ULID identifiers — 128-bit, lexicographically sortable, Crockford-Base32 text —
combining a 48-bit millisecond timestamp with 80 random bits, so keys sort by
creation time yet stay collision-free without a coordinator.

## Install

```
edda add ulid
```

Then import the module you need:

```edda
import ulid.ulid
```

## Usage

```edda
import ulid.ulid

function fresh_id(ms: u64, rand: Random, allocator: Allocator) -> String
    with {rand, allocator, err: alloc.AllocError}
{
    let id = ulid.new(ms, rand, allocator)?
    return ulid.encode(id, allocator)?
}
```

`ulid.new` takes the timestamp in milliseconds explicitly (pass your `Clock`'s
current millis) plus a `Random` for the entropy bits. `ulid.parse(s)` reverses
`encode`, returning `Option_Ulid`, and `ulid.timestamp_ms(id)` reads the
embedded millisecond timestamp back out of a `Ulid`.

## Public surface

- **`ulid`** — the `Ulid` value type plus `new` (construct from `ms` +
  `Random`), `encode` (to Crockford-Base32 `String`), `parse` (back to
  `Option_Ulid`), and `timestamp_ms` (extract the embedded time).
