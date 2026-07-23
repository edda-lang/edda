# envconfig

Typed environment-variable configuration — read a named variable and coerce it to
a `String`, `i64`, `bool`, `u16` port, or a required value, with parse failures and
missing-but-required variables surfaced as errors. Reads the process environment
through `std.os.env`.

## Install

```
edda add envconfig
```

Then import the module you need:

```edda
import envconfig.config
```

## Usage

```edda
import envconfig.config

function port(allocator: Allocator) -> u16
    with {allocator, err: alloc.AllocError}
{
    return match config.get_port("PORT", allocator) {
        case .some(let p) => p
        case .none        => 8080
    }
}
```

The `get_*` readers return an `Option` — `.none` when the variable is unset or fails
to parse. `get_str_or` folds the unset case into a supplied default. `require_str`
raises `ConfigError.missing` through the row when the variable is absent, for values
a program cannot start without.

## Public surface

- **`config`** — readers `get_str`, `get_str_or`, `require_str`, `get_int`, `get_bool`, `get_port`, and the `ConfigError` enum (`missing` / `invalid`) raised by `require_str`.
