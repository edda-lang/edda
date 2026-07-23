# hermod

An HTTP/1.1 client and wire codec — build requests, send them over a `Network`
capability, and read the response, with the low-level pieces (request/response
encode and decode, chunked transfer coding, URI parsing) exposed underneath the
high-level `fetch` API. The named messenger for talking to HTTP servers.

## Install

```
edda add hermod
```

Then import the modules you need:

```edda
import hermod.fetch.send
import hermod.fetch.response
import hermod.error
```

## Usage

```edda
import hermod.fetch.send
import hermod.fetch.response

function fetch_status(url: String, net: Network, allocator: mutable Allocator) -> u16
    with {
        net,
        allocator,
        err: error.UriError,
        err: alloc.AllocError,
        err: error.TransportError,
        err: error.CodecError,
    }
{
    let resp = send.fetch_get(url, net, mutable allocator)?
    return response.status_code(resp)
}
```

`send.fetch_post(url, body_bytes, net, allocator)` is the POST counterpart, and
`send.fetch_send(req, net, allocator)` sends a pre-built `Request` (from
`hermod.message.request`). The `response` module reads a `Response` back —
`status_code`, `is_success` / `is_redirect` / `is_error`, `body_bytes`,
`body_len`, and `header_bytes_or`. To follow 3xx redirects automatically, use
`redirect.fetch_get_follow(url, max_redirects, net, allocator)` from
`hermod.fetch.redirect`.

## Public surface

- **`fetch.send`** — the high-level client: `fetch_get`, `fetch_post`,
  `fetch_send`.
- **`fetch.response`** — response accessors: `status_code`, `is_success` /
  `is_redirect` / `is_error`, `body_bytes`, `header_bytes_or`.
- **`fetch.redirect`** — `fetch_get_follow`, GET with automatic redirect
  following.
- **`message`** — the `Request` / `Response` / `Body` types and their builders
  (`request_get`, `request_post`, `response_ok`, `body_from_string`).
- **`uri`** — the `Uri` type and `uri_parse` for parsing request targets.
- **`error`** — the `CodecError`, `TransportError`, `UriError`, and
  `RedirectError` enums carried in the effect rows above.
