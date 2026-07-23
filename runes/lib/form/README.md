# form

`application/x-www-form-urlencoded` body parsing — splits a POST body into
percent-decoded `name=value` fields and looks them up by name, with typed
accessors that fail loudly when a required field is missing or malformed. The
building block a request handler uses to turn a raw form submission into values.

## Install

```
edda add form
```

Then import the module you need:

```edda
import form.urlencoded
```

## Usage

```edda
import form.urlencoded

function read_name(body: [u8], allocator: Allocator) -> String
    with {allocator, err: alloc.AllocError, err: percent.PercentError, err: FieldError}
{
    let fields = urlencoded.parse(body, allocator)?
    return urlencoded.string_field(fields, "name", allocator)?
}
```

`urlencoded.parse` returns a `[Field]` (each a percent-decoded `name` / `value`
pair). `urlencoded.string_field(fields, name, allocator)` and
`urlencoded.usize_field(fields, name, allocator)` pull a required field out by
name, raising `FieldError` when it is absent (and `str.ParseIntError` on a
non-numeric `usize_field`). For an optional field, `urlencoded.opt_field`
returns a `Lookup` (`found` / `missing`) instead of raising.

## Public surface

- **`urlencoded`** — `parse` (body → `[Field]`), the typed accessors
  `string_field` / `usize_field`, and `opt_field` for optional lookups; plus the
  `Field`, `FieldError`, and `Lookup` types.
