# jwt

JSON Web Tokens — the compact, URL-safe `header.payload.signature` bearer
tokens used for stateless authentication — signed and verified with HMAC-SHA256
over a shared secret.

## Install

```
edda add jwt
```

Then import the module you need:

```edda
import jwt.jwt
```

## Usage

```edda
import jwt.jwt

function is_authentic(token: String, secret: [u8], allocator: mutable Allocator) -> bool
    with {allocator, err: alloc.AllocError, divergence}
{
    return match jwt.verify(token, secret, mutable allocator)? {
        case .valid(_)        => true
        case .bad_signature   => false
        case .malformed       => false
    }
}
```

`jwt.verify` recomputes the signature and returns a `Verified` — `valid(claims)`
carrying the decoded payload, `bad_signature`, or `malformed`. To mint a token,
`jwt.sign(take claims, secret, mutable allocator)` serialises a `JsonValue`
claim set and appends the signature. When you only need to read a token without
checking it, `jwt.decode_header` / `jwt.decode_payload` return the parsed
`JsonValue` segments.

## Public surface

- **`jwt`** — `sign` (mint), `verify` (constant-time signature check, yielding
  `Verified`), and `decode_header` / `decode_payload` (parse without verifying).
  Types: `Verified` and `DecodeError`.
- **`base64url`** — the underlying URL-safe Base64 `encode` / `decode` and the
  `Base64UrlError` enum.
