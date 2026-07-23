# toml

A TOML reader for Edda — parse a document into a `Table` and read typed values
out of it by key (strings, integers, floats, booleans, string arrays, nested
tables, and table arrays). Parsing allocates through a caller-supplied
`Allocator`.

## Install

```
edda add toml
```

Then import the modules you need:

```edda
import toml.parse
import toml.value
```

## Usage

```edda
import toml.parse
import toml.value
import std.core.option

function name_from(text: String, allocator: Allocator) -> Option_String
    with {allocator, err: error.ParseError, divergence}
{
    let table = parse.parse(text, allocator)?
    return value.get_string(table, "name")
}
```

Each typed getter — `value.get_integer`, `value.get_float`, `value.get_boolean`,
`value.get_string_array`, `value.get_table`, `value.get_table_array` — returns an
`Option` for the key, while `value.get` returns the raw `Value` sum. Use
`value.has` to test for a key and `value.len` for the entry count.

## Public surface

- **`toml.parse`** — `parse` builds a `Table` from a `String` document.
- **`toml.error`** — the `ParseError` enum (`missing_equals`, `duplicate_key`,
  `unterminated_string`, `bad_number`, …) reported for a malformed document.
- **`toml.value`** — the `Value` / `Table` / `TableEntry` / `TableArray` /
  `StringArray` types plus the reader API: `get` (raw `Value`), the typed
  `get_string` / `get_integer` / `get_float` / `get_boolean` /
  `get_string_array` / `get_table` / `get_table_array` getters, and `has` / `len`.
