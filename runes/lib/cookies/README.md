# cookies

HTTP cookie parsing for Edda — read a `Set-Cookie` response header into a
`Cookie` (name, value, and every standard attribute), and walk a `Cookie:`
request header's `name=value` pairs one at a time. `Set-Cookie` parsing
allocates through a caller-supplied `Allocator`.

## Install

```
edda add cookies
```

Then import the modules you need:

```edda
import cookies.parse
import cookies.value
import cookies.request
```

## Usage

```edda
import cookies.parse
import cookies.value

function session_id(header: String, allocator: Allocator) -> String
    with {allocator, err: error.ParseError}
{
    let c = parse.parse_set_cookie(header, allocator)?
    return value.value(c)
}
```

`parse.parse_set_cookie_bytes` is the same over a `[u8]` slice. The accessors in
`cookies.value` read each field of a `Cookie` — `name`, `value`, `expires`,
`max_age`, `domain`, `path`, `secure`, `http_only`, `same_site`. To read an
incoming `Cookie:` request header (many `name=value` pairs), drive the
`cookies.request` iterator: `cookie_count` totals the pairs, and repeated
`cookie_advance(value, from)` calls return a `CookieAdvance` cursor until
`cookie_done` reports the end.

## Public surface

- **`cookies.parse`** — `parse_set_cookie` / `parse_set_cookie_bytes` build a
  `Cookie` from a `Set-Cookie` header (a `String` or `[u8]`).
- **`cookies.value`** — the `Cookie` and `SameSite` types plus per-field
  accessors: `name`, `value`, `expires`, `max_age`, `domain`, `path`, `secure`,
  `http_only`, `same_site`.
- **`cookies.request`** — the `CookieAdvance` cursor and its iterator over a
  `Cookie:` request header: `cookie_advance`, `cookie_done`, `cookie_count`.
- **`cookies.error`** — the `ParseError` enum (`empty_input`, `missing_equals`,
  `empty_name`, `allocation_failed`).
