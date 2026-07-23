# uri

RFC 3986 URI parsing — split a URI string into its scheme, authority (userinfo /
host / port), path, query, and fragment, with the percent-encoding codec and
reference-resolution transforms alongside. Absolute URIs and relative references
both parse.

## Install

```
edda add uri
```

Then import the module you need:

```edda
import uri.syntax.parse
import uri.value
import uri.codec.codec
import uri.transform.transform
```

## Usage

```edda
import uri.syntax.parse
import uri.value

function origin(src: String, allocator: Allocator) -> Option_String
    with {allocator, err: error.ParseError}
{
    let u = parse.parse(src, allocator)?
    return value.host(u)
}
```

`parse.parse` returns a `value.Uri`; `parse.parse_reference` accepts a relative
reference and returns a `value.UriReference`. Each raises `error.ParseError` (with
variants such as `empty_host`, `bad_port`, `port_out_of_range`, `bad_percent_encoding`)
through the row. Read the parsed components with the `value` accessors.

## Public surface

- **`syntax.parse`** — entry points `parse` / `parse_bytes` (absolute URI) and `parse_reference` / `parse_reference_bytes` (relative reference).
- **`value`** — the `Uri` / `UriReference` records plus accessors `scheme`, `userinfo`, `host`, `port`, `path`, `query`, `fragment`, and the `has_authority` / `has_scheme` predicates.
- **`error`** — the `ParseError` enum carried in fallible rows.
- **`codec.codec`** — percent-encoding `encode` / `decode` and component-scoped helpers.
- **`transform.transform`** — `normalize`, `remove_dot_segments`, and reference `resolve`.
