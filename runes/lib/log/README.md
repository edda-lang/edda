# log

Leveled logging that writes straight to the capability you hand it — `trace` /
`debug` / `info` go to `Stdout`, `warn` / `error` go to `Stderr`. No ambient
logger, no global state: the output stream is a parameter, so what a function
can log is exactly what its effect row admits.

## Install

```
edda add log
```

Then import the modules you need:

```edda
import log.level
import log.sink
```

## Usage

```edda
import log.sink

function greet(out: Stdout) -> ()
    with {out}
{
    sink.info(out, "server started")
}
```

The level helpers wrap `sink.log`: `sink.trace` / `sink.debug` / `sink.info`
take a `Stdout` and carry `{out}`; `sink.warn` / `sink.error` take a `Stderr`
and carry `{errout}`. Each prints one line prefixed with the level name. For an
explicit level, call `sink.log(out, level.Level.info, msg)` (or `sink.log_err`
for stderr). To filter, compare against a threshold with
`level.should_log(min, l)` before emitting.

## Public surface

- **`level`** — the `Level` enum (`trace` `debug` `info` `warn` `error`) plus
  `level_name`, `level_rank`, and `should_log` for threshold checks.
- **`sink`** — the writers: `trace` / `debug` / `info` (Stdout), `warn` /
  `error` (Stderr), and the underlying `log` / `log_err`.
