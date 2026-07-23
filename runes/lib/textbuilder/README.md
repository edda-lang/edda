# textbuilder

A growable byte buffer for assembling text and binary output incrementally —
push bytes, byte slices, or strings, then hand back a single `[u8]`. The buffer
you want when building up a response body or wire message piece by piece.

## Install

```
edda add textbuilder
```

Then import the module you need:

```edda
import textbuilder.builder
```

## Usage

```edda
import textbuilder.builder

function render(name: String, allocator: Allocator) -> [u8]
    with {allocator, err: alloc.AllocError}
{
    var b = builder.new(allocator)
    builder.push_str(mutable b, "hello, ", allocator)?
    builder.push_str(mutable b, name, allocator)?
    builder.push_byte(mutable b, 0x0a, allocator)?
    return builder.to_bytes(b, allocator)
}
```

`builder.new(allocator)` starts an empty `Builder`. Append with `push_byte`,
`push_bytes` (a `[u8]` slice), or `push_str` (a `String`) — each takes the
builder as `mutable` and the allocator, propagating `err: alloc.AllocError` on
growth. `builder.len(b)` reports the byte count; `builder.to_bytes(b, allocator)`
copies the accumulated content into a fresh `[u8]`.

## Public surface

- **`builder`** — the `Builder` type and `new`.
- **`builder`** — appending: `push_byte`, `push_bytes`, `push_str`.
- **`builder`** — reading out: `len`, `to_bytes`.
