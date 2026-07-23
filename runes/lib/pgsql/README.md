# pgsql

A PostgreSQL client speaking the v3 wire protocol directly over a `Network`
socket — connect with SCRAM-SHA-256 (or cleartext) auth, run simple queries,
and drive transactions. Results come back as decoded rows; the extended
(prepared-statement) protocol and per-OID value codecs are exposed for lower-level
work. No C library or external driver: it is Edda talking to the server.

## Install

```
edda add pgsql
```

Then import the modules you need:

```edda
import pgsql.client.session.startup.connect
import pgsql.client.exec.query
import pgsql.client.exec.tx
import pgsql.error
```

## Usage

```edda
import pgsql.client.exec.query

function ping(conn: mutable connect.Connection, allocator: Allocator) -> query.SimpleQueryResult
    with {allocator, err: socket.SocketError, err: alloc.AllocError, err: error.ProtocolError, err: error.QueryError, divergence}
{
    return query.run_simple_query(mutable conn, "SELECT 1".bytes(), allocator)?
}
```

Open the connection first with `connect.connect(net, host, port, username,
password, database, rng, allocator)` — it returns a `linear Connection`, so
consume it with `connect.close(take conn, allocator)` when you are done. `sql`
is `[u8]`; pass a string literal's `.bytes()`. A `SimpleQueryResult` is one of
`rows` (holding a `SimpleQueryRows` with its row description and decoded
`SimpleQueryRow` list), `command` (a command tag for statements like `INSERT`),
or `empty`. Wrap statements in a transaction with `tx.begin` / `tx.commit` /
`tx.rollback` (plus `savepoint` / `release_savepoint` / `rollback_to_savepoint`).

## Public surface

- **`client.session.startup.connect`** — `connect(net: Network, host, port: u16, username: [u8], password: [u8], database: [u8], rng: Random, allocator) -> Connection` (a `linear` handle), `close(take conn, allocator)`.
- **`client.exec.query`** — `run_simple_query(mutable conn, sql: [u8], allocator) -> SimpleQueryResult`; result types `SimpleQueryResult`, `SimpleQueryRows`, `SimpleQueryRow`.
- **`client.exec.tx`** — `begin` / `commit` / `rollback`, and `savepoint` / `release_savepoint` / `rollback_to_savepoint`, each `(mutable conn, ...)`.
- **`extended`** — prepared statements and portals (`PreparedStatement`, `Portal`, `BindArgs`, `PreparedQueryResult`) for the extended-query protocol.
- **`codec`** / **`oid`** — per-type binary encode/decode and PostgreSQL type OIDs.
- **`error`** — `ProtocolError`, `AuthError`, `QueryError`, `EncodingError`, `TransportError`.

`connect` needs a `Network` capability (and a `Random` for SCRAM nonces); query
and transaction calls run on the established `Connection`.
