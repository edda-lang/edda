# money

Fixed-point money — an exact `i64` minor-unit amount plus a decimal `scale`
(e.g. scale `2` for cents), so arithmetic stays penny-accurate with no floating
point. Addition, subtraction, and integer scaling are checked (they raise
`overflow.Overflow` rather than silently wrapping), and same-scale amounts
compare and format for display.

## Install

```
edda add money
```

Then import the module you need:

```edda
import money.money
```

## Usage

```edda
import money.money

function total(price: money.Money, qty: i64) -> money.Money
    with {err: overflow.Overflow}
{
    return money.mul_int(price, qty)?
}
```

Build amounts with `money.from_minor(minor, scale)` (e.g.
`from_minor(1099, 2)` is `10.99`) or `money.zero(scale)`. Combine same-scale
amounts with `add` / `sub` (both raise `overflow.Overflow`), order them with
`compare`, and render with `format`. `parse` reads a decimal string back into a
`Money` at a given scale.

## Public surface

- **`money`**
  - Construct — `from_minor(minor: i64, scale: u8) -> Money`, `zero(scale: u8) -> Money`.
  - Arithmetic — `add` / `sub` (require equal scale; row `{err: overflow.Overflow}`), `mul_int(m, n: i64)`, `neg`.
  - Inspect / order — `is_negative(m) -> bool`, `compare(a, b) -> i8` (requires equal scale).
  - Text — `format(m, allocator) -> String` (row `{allocator, err: alloc.AllocError}`), `parse(s, scale, allocator) -> Option_Money`.
  - `Money` — `{ minor: i64, scale: u8 }`.

`add`, `sub`, and `compare` require both operands share a `scale`; `format`
allocates the rendered string.
