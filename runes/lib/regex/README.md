# regex

A regular-expression engine — compile a pattern once, then match, search,
iterate, split, and substitute over UTF-8 byte input. Patterns lower to a
bytecode program run on a backtracking VM, with capture groups (positional and
named) recorded as byte spans.

## Install

```
edda add regex
```

Then import the modules you need:

```edda
import regex.api
import regex.api.compile
import regex.api.find
```

## Usage

```edda
import regex.api
import regex.api.compile
import regex.api.find

function matches(pattern: String, text: String, allocator: mutable Allocator) -> bool
    with {allocator, err: api.RegexError, divergence}
{
    let re = compile.compile(pattern, mutable allocator)?
    return find.is_match(re, text.bytes(), mutable allocator)?
}
```

`compile.compile` builds a `Regex` (use `compile.compile_with_flags` for
case-insensitivity and other `mode.Flags`); matching functions all take the
compiled `Regex` plus the input as `[u8]`. `find.find` returns the first
`Option_Match`, `find.find_at` starts from an offset, and `iter.find_iter` /
`iter.find_iter_next` walk every non-overlapping match. `api.find_all` collects
all matches at once and `api.split` splits input on the pattern.

Given a `Match`, read capture groups with `api.group_span` / `api.group_bytes`
by index or `api.group_span_named` by name; `api.group_count` reports how many
groups a match holds and `api.whole_match` gives the overall span.
`replace.replace_all` / `replace.replace_first` substitute matches, expanding
`$name` / group references in the replacement template.

## Public surface

- **`api.compile`** — `compile` and `compile_with_flags`, the entry points that
  turn a pattern `String` into a `Regex`.
- **`api.find`** — `is_match`, `find`, and `find_at` for single matches.
- **`api.iter`** — `find_iter` / `find_iter_next` over the `FindIter` cursor for
  every match.
- **`api.replace`** — `replace_all` / `replace_first` with template expansion.
- **`api`** — the `Regex`, `SpanPair`, `RegexError`, and `FindIter` types, the
  bulk `find_all` / `split` operations, and the group accessors
  (`whole_match`, `group_span`, `group_bytes`, `group_count`,
  `group_index_by_name`, `group_span_named`).
