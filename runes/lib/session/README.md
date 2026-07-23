# session

Server-side session storage plus signed session ids — an in-memory `Store`
keyed by opaque session id, per-session key/value data (with a one-shot "flash"
tier), and the HMAC-SHA256 signing/verification a cookie needs so a client
cannot forge its own id. The pieces a web app assembles into a login session.

## Install

```
edda add session
```

Then import the modules you need:

```edda
import session.store
import session.signed
import session.id
```

## Usage

```edda
import session.store

function set_user(sessions: mutable store.Store, sid: String, user: String, allocator: Allocator) -> ()
    with {allocator, err: alloc.AllocError}
{
    store.set(mutable sessions, sid, "user", user, allocator)
}
```

`store.new(allocator)` creates the store; `store.get(sessions, sid, key)`
returns an `Option_String.Option`, and `store.has_session` / `store.remove` /
`store.destroy` manage entries. The flash tier — `store.flash_set`,
`store.flash_get`, `store.flash_sweep` — holds values meant to survive exactly
one request. For the cookie itself, `id.generate(rand, allocator)` mints a fresh
random id, `signed.sign(value, key, allocator)` appends an HMAC-SHA256 tag, and
`signed.unsign(signed, key, allocator)` returns an `Unsigned` verdict (`valid`
/ `tampered` / `malformed`) using a constant-time tag comparison.

## Public surface

- **`store`** — the `Store` and `Session` types; `new`, `get` / `set` /
  `remove` / `destroy`, `has_session`, and the `flash_*` one-shot tier.
- **`signed`** — `sign` / `unsign` for HMAC-signed cookie values, plus the
  `Unsigned` verdict enum.
- **`id`** — `generate`, a random hex session id (needs a `Random` capability).
