# validate

Small, allocation-free validators for user input — the boundary checks a form
handler or config loader reaches for before trusting a string: is this an
email, a URL, a UUID, an integer; is it ASCII, alphanumeric, non-empty, or the
right length; is this number in range.

## Install

```
edda add validate
```

Then import the module you need:

```edda
import validate.text
import validate.number
import validate.pattern
```

## Usage

```edda
import validate.text

function is_valid_username(s: String) -> bool {
    return !text.is_empty(s) && text.is_alphanumeric(s) && text.len_between(s, 3, 32)
}
```

Most predicates are pure and take only the value — `text.is_int(s)`,
`text.is_uuid(s)`, `text.is_ascii(s)`, and `number.in_range_i64(n, lo, hi)`
never allocate. The two pattern checks, `pattern.is_email(s, mutable allocator)`
and `pattern.is_url(s, mutable allocator)`, compile a regex under the hood, so
they take a `mutable Allocator` and carry `err: regex_api.RegexError` in their
row.

## Public surface

- **`text`** — string predicates: `is_empty`, `len_between`, `is_ascii`,
  `is_alphanumeric`, `is_int`, `is_uuid`.
- **`number`** — `in_range_i64` for bounded-integer checks.
- **`pattern`** — `is_email` / `is_url`, the regex-backed validators that need a
  `mutable Allocator`.
