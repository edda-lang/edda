# cli

Command-line argument parsing — declare the flags and options a program
accepts, then parse an `argv` slice into a `Parsed` you query by name. Flags are
boolean (`--verbose` / `-v`); options take a value (`--output x` or
`--output=x`); everything else collects as positionals. Each spec has a long and
a short form, and an unknown argument or a missing option value raises
`error.CliError`.

## Install

```
edda add cli
```

Then import the modules you need:

```edda
import cli.parser
import cli.error
```

## Usage

```edda
import cli.parser

function verbose_flag(argv: [String], allocator: Allocator) -> bool
    with {allocator, err: alloc.AllocError, err: error.CliError}
{
    var p: parser.Parser = parser.new(allocator)?
    parser.add_flag(mutable p, "--verbose", "-v", allocator)?
    let parsed = parser.parse(p, argv, allocator)?
    return parser.flag(parsed, "--verbose")
}
```

Register value-taking options with `parser.add_option(mutable p, "--output",
"-o", allocator)`; after `parse`, read them with `parser.option(parsed,
"--output") -> Option_String` and collect the leftover arguments with
`parser.positionals(parsed) -> [String]`.

## Public surface

- **`parser`**
  - `new(allocator) -> Parser` — an empty parser.
  - `add_flag(mutable p, long, short, allocator)` / `add_option(mutable p, long, short, allocator)` — register a boolean flag or a value option; row `{allocator, err: alloc.AllocError}`.
  - `parse(p, argv: [String], allocator) -> Parsed` — row `{allocator, err: alloc.AllocError, err: error.CliError}`.
  - Query a `Parsed` — `flag(parsed, long) -> bool`, `option(parsed, long) -> Option_String`, `positionals(parsed) -> [String]`.
  - Types — `Parser`, `Parsed`, `Spec`, `OptEntry`.
- **`error`**
  - `CliError` — `unknown_argument` / `missing_value`, raised by `parse`.
