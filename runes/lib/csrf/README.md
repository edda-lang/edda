# csrf

Cross-site-request-forgery tokens. `csrf.token` mints a random token and
compares a submitted value against it in constant time. `csrf.session` binds a
token to a `session.Store` entry, consumes it on verification (single-use),
and renders the hidden `<input>` field for a form.

## Install

```
edda add csrf
```

Then import the module you need:

```edda
import csrf.token
import csrf.session
```

## Usage

Stateless, caller-held token:

```edda
import csrf.token

function issue(rand: Random, allocator: Allocator) -> String
    with {rand, allocator, err: alloc.AllocError}
{
    return token.generate(rand, allocator)?
}
```

Session-bound, single-use token:

```edda
import csrf.session

function render_form(store: mutable session_store.Store, id: String, rand: Random, allocator: Allocator) -> String
    with {rand, allocator, err: alloc.AllocError}
{
    let value = session.token(mutable store, id, rand, allocator)?
    return session.hidden_field_html(value, allocator)?
}

function accept_submission(store: mutable session_store.Store, id: String, submitted: String, allocator: Allocator) -> bool
    with {allocator, err: alloc.AllocError}
{
    return session.verify(mutable store, id, submitted, allocator)?
}
```

`token.generate` draws 32 random bytes from a `Random` capability and returns
them hex-encoded. `token.verify(expected, provided)` compares two tokens in
constant time (backed by `std.crypto.subtle`), so it does not leak a match
position through timing.

`session.token` stores the generated token under the session's `_csrf_token`
key; `session.verify` looks it up, checks it against the submission, and
removes it either way — a token verifies at most once. `session.validate_form`
does the same starting from parsed `form.urlencoded.Field`s, returning `false`
outright if the field is missing.

## Public surface

- **`token`** — `generate` (mint a fresh token) / `verify` (constant-time
  equality check).
- **`session`**
  - `field_name() -> String` — the session/form key the helpers below use (`_csrf_token`).
  - `token(store: mutable Store, id: String, rand: Random, allocator: Allocator) -> String` — mints a token and binds it to the session; row `{rand, allocator, err: alloc.AllocError}`.
  - `verify(store: mutable Store, id: String, submitted: String, allocator: Allocator) -> bool` — checks and consumes the session's token (single-use); row `{allocator, err: alloc.AllocError}`.
  - `hidden_field_html(token_value: String, allocator: Allocator) -> String` — renders `<input type="hidden" name="_csrf_token" value="...">`; row `{allocator, err: alloc.AllocError}`.
  - `validate_form(store: mutable Store, id: String, fields: [urlencoded.Field], allocator: Allocator) -> bool` — extracts the hidden field from parsed form fields and verifies it; row `{allocator, err: alloc.AllocError}`.
