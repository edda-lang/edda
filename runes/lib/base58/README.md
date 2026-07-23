# base58

Base58 and Base58Check binary-to-text encoding — the compact, ambiguity-free
alphabet (no `0`/`O`, no `I`/`l`) used by Bitcoin addresses, IPFS identifiers,
and other places raw bytes need a copy-pasteable text form.

## Install

```
edda add base58
```

Then import the module you need:

```edda
import base58.codec
```

## Usage

```edda
import base58.codec

function to_text(raw: [u8], allocator: Allocator) -> String
    with {allocator, err: alloc.AllocError}
{
    return codec.encode(raw, allocator)?
}
```

`codec.decode(s, allocator)` reverses it, raising `base58.Base58Error` on an
invalid character. For versioned, checksummed payloads (the Base58Check form
behind addresses) use `codec.encode_check(payload, version, allocator)` and
`codec.decode_check(s, allocator)`, which append and verify a 4-byte SHA-256
checksum.

## Public surface

- **`codec`** — `encode` / `decode` for plain Base58, `encode_check` /
  `decode_check` for Base58Check (checksummed, versioned).
- **`alphabet`** — the `Base58Error` enum (`invalid_char`, `bad_checksum`) plus
  the low-level `radix`, `digit_char`, and `digit_value` primitives.
