# multipart

A `multipart/form-data` body parser — splits a request body on its boundary and
returns each part with its `Content-Disposition` name, optional filename,
optional content type, and raw content bytes. The parser for HTML file uploads
and multi-field forms.

## Install

```
edda add multipart
```

Then import the module you need:

```edda
import multipart.decode
```

## Usage

```edda
import multipart.decode

function fields(body: [u8], boundary: String, allocator: Allocator) -> [decode.Part]
    with {allocator, err: alloc.AllocError}
{
    return decode.parse(body, boundary, allocator)?
}
```

`decode.parse` takes the boundary string on its own; if you have the raw
`Content-Type` header instead, `decode.parse_with_header(body, header,
allocator)?` pulls the `boundary=` parameter out for you. Each returned `Part`
carries `name: String`, `filename` / `content_type` as `Option_String`, and
`content: [u8]`.

## Public surface

- **`decode`** — `Part`, `parse` (boundary form), `parse_with_header`
  (`Content-Type` form): the parse entry points.
- **`params`** — `extract` / `name_eq_ci`: header-parameter lookup
  (`name="..."`, `filename="..."`) used by the decoder.
- **`scan`** — byte helpers `slice_copy` / `bytes_eq_at` / `find_from` /
  `index_of` / `find_lf` / `trim_ows_left` / `strip_trailing_crlf`: the
  low-level scanning primitives.
