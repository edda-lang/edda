# css

A CSS stylesheet builder — chain rules, declarations, and media queries into a
`Sheet` and render it to bytes. Comes with a `Color` type and helpers (`rgb` /
`rgba` / `hex`, `lighten` / `darken` / `mix`, WCAG contrast). For generating
stylesheets from Edda code instead of hand-writing `.css`.

## Install

```
edda add css
```

Then import the module you need:

```edda
import css.sheet
import css.tokens
```

## Usage

```edda
import css.sheet

function stylesheet(allocator: Allocator) -> [u8]
    with {allocator, err: alloc.AllocError}
{
    var s = sheet.new(allocator)?
    s = sheet.rule(s, "body", allocator)?
    s = sheet.decl(s, "margin", "0", allocator)?
    s = sheet.decl(s, "font-size", "16px", allocator)?
    s = sheet.end_rule(s, allocator)?
    return sheet.render(s, allocator)?
}
```

Each builder step consumes the `Sheet` and returns the next one, so rebind as
you go. `media` / `end_media` wrap a block in a media query, `sheet.dot(name)`
prefixes a class selector, and `tokens` builds colors (`rgb`, `rgba`, `hex`,
`lighten` / `darken`, `contrast_ratio`) for use as declaration values.

## Public surface

- **`sheet`** — `Sheet`, `new`, `rule` / `decl` / `end_rule`, `media` /
  `end_media`, `render` (to `[u8]`), `dot` (class-selector helper).
- **`tokens`** — `Color`, `rgb` / `rgba` / `white` / `black`, `mix` / `lighten`
  / `darken` / `alpha`, `hex` / `rgba_str`, unit helpers `px` / `rem` / `space`,
  and `luminance` / `contrast_ratio` / `contrast_at_least`.
