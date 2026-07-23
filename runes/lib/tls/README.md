# tls

A TLS 1.3 implementation in Edda — dial a host, run the handshake, and read and
write application data over an encrypted `Connection`, all through capabilities
you pass in. Certificate verification, the AEAD record layer, and the key
schedule live behind a small high-level surface; errors surface as a single
`TlsError` in the effect row.

## Install

```
edda add tls
```

Then import the modules you need:

```edda
import tls.config
import tls.client
import tls.conn
```

## Usage

```edda
import std.crypto.x509.chain as x509_chain
import tls.config
import tls.client
import tls.conn
import tls.error

function connect(
    network: Network,
    random: Random,
    trust_store: x509_chain.TrustStore,
    host: String,
    now: i64,
    allocator: mutable Allocator,
) -> conn.Connection
    with {network, random, allocator, err: error.TlsError}
{
    let cfg = config.client_config_new(host, trust_store, now)
    return client.open(network, random, host, 443, cfg, mutable allocator)?
}
```

`config.client_config_new(server_name, trust_store, now_unix_seconds)` builds a
`ClientConfig`; `client.open` uses the `Network` capability to dial `host:port`,
drives the handshake with `Random`, verifies the peer chain against the config's
trust store, and returns a live `conn.Connection`. From there, `conn.send(mutable conn, data, mutable allocator)`
writes application bytes and `conn.recv(mutable conn, mutable buf, mutable allocator)`
reads them; `conn.close(take conn, mutable allocator)` sends `close_notify` and
tears the connection down. For the accepting side, `server.accept(take tcp, config, random, allocator)`
completes a server handshake over an already-dialed socket using a `ServerConfig`
(from `config.server_config_new`).

## Public surface

- **`config`** — `ClientConfig` / `ServerConfig` and their constructors
  `client_config_new` / `server_config_new`.
- **`client`** — `open`: dial + handshake, returning a `Connection`.
- **`server`** — `accept`: server-side handshake over an existing socket.
- **`conn`** — the `Connection` type and its I/O: `send`, `recv`, `close`.
- **`error`** — `TlsError`, the single error enum threaded through every
  fallible call (`invalid_server_name`, `certificate_not_trusted`,
  `bad_record_mac`, `alert_received`, and the rest).
- **`alert`** — the `AlertLevel` / `AlertDescription` enums and their wire
  encodings, plus `alert_to_error`.
