# httpserver

A minimal HTTP/1.1 server built on `hermod` for request/response codec and
`std.net.socket` for transport. Bind a listener, then serve connections with a
handler that maps a `hermod` `Request` to a `Response`. Concurrent variants fan
connections out across an `Executor`.

## Install

```
edda add httpserver
```

Then import the module you need:

```edda
import httpserver.serve
import hermod.message.request
import hermod.message.response
```

## Usage

```edda
import httpserver.serve
import hermod.message.request as request_mod
import hermod.message.response as response_mod
import hermod.error as herr

function run(net: Network, allocator: Allocator) -> ()
    with {net, allocator, divergence, err: herr.TransportError, err: herr.CodecError, err: alloc.AllocError}
{
    var server = serve.bind(net, "127.0.0.1".bytes(), 8080 as u16, allocator)?
    serve.serve_forever(mutable server, handle_request, mutable allocator)
}
```

`serve.bind` opens the listener; `serve.serve_forever` loops accepting
connections and dispatches each to your `handler` — a
`function(request_mod.Request, mutable Allocator) -> response_mod.Response with
{allocator, err: herr.CodecError}`. Use `serve.serve_n` to serve a bounded
number of connections, or `concurrent.serve_concurrent_n` / `_round` (which take
an `Executor`) to handle a window of connections in parallel. `serve.close`
consumes the `Server` when you are done.

## Public surface

- **`serve`** — `Server`, `bind` / `close` / `accept` / `server_port`,
  `serve_forever` / `serve_n` / `serve_connection_quiet`: the sequential serving
  path.
- **`concurrent`** — `serve_concurrent_round` / `serve_concurrent_n` /
  `concurrent_window`: `Executor`-backed parallel serving.
- **`frame`** — request-framing helpers `read_full_request` / `find_header_end`
  / `content_length` / `is_chunked`, plus `default_max_request_bytes` /
  `default_read_timeout_millis`.
