# slug

URL slug generation — collapse an arbitrary title into a lowercase,
hyphen-separated, ASCII-alphanumeric identifier suitable for a path segment
(`"Hello, World!"` becomes `hello-world`). Non-alphanumeric runs fold to a
single hyphen and leading/trailing hyphens are trimmed.

## Install

```
edda add slug
```

Then import the module you need:

```edda
import slug.slugify
```

## Usage

```edda
import slug.slugify

function make_slug(title: String, allocator: Allocator) -> String
    with {allocator, err: alloc.AllocError}
{
    return slugify.slugify(title, allocator)?
}
```

`slugify.slugify_max(s, max_len, allocator)` produces the same slug but caps its
length, cutting on a hyphen boundary so the result never ends mid-word.

## Public surface

- **`slugify`**
  - `slugify(s: String, allocator: Allocator) -> String` — the full slug.
  - `slugify_max(s: String, max_len: usize, allocator: Allocator) -> String` — length-bounded, trimmed on a word boundary.

Both allocate, so they carry `with {allocator, err: alloc.AllocError}`.
