# totp

RFC 4226 HOTP and RFC 6238 TOTP one-time passwords — the six-digit codes behind
authenticator apps and two-factor login. Derives a code from a shared secret and
a moving factor (a counter for HOTP, the current time for TOTP), formats it with
leading zeros, and verifies a submitted code with a constant-time comparison over
a configurable time window.

## Install

```
edda add totp
```

Then import the module you need:

```edda
import totp.otp
```

## Usage

```edda
function current_code(secret: [u8], unix_seconds: u64, allocator: Allocator) -> u32
    with {allocator, err: alloc.AllocError}
{
    return otp.totp(secret, unix_seconds, 30, 6, allocator)?
}
```

`otp.totp_b32(secret_b32, unix_seconds, period, digits, allocator)` takes a
Base32-encoded secret string instead of raw bytes (adding
`err: base32.Base32Error`). `otp.hotp(secret, counter, digits, allocator)` is the
counter-based variant. `otp.format_code(code, digits, allocator)` renders a code
as a zero-padded `String`, and `otp.verify(secret, unix_seconds, code, period,
digits, window, allocator)` checks a submitted code against `window` steps on
either side in constant time. `period` must be greater than zero.

## Public surface

- **`otp`** — `totp` / `totp_b32` (time-based), `hotp` (counter-based),
  `format_code` for display, and `verify` for constant-time validation with a
  drift window.
