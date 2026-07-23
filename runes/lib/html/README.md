# html

Streaming HTML builder — open elements, set attributes, and emit text through a
chained, always-well-formed API that escapes content and attribute values for you.
Backed by `textbuilder`, so the output accumulates into a byte buffer with no
intermediate allocations per node.

## Install

```
edda add html
```

Then import the module you need:

```edda
import html.markup
```

## Usage

```edda
import html.markup

function greeting(name: String, allocator: Allocator) -> [u8]
    with {allocator, err: alloc.AllocError, err: htmlescape.HtmlEscapeError}
{
    let h = markup.new(allocator)?
    let h = markup.el(h, "p", allocator)?
    let h = markup.attr(h, "class", "greeting", allocator)?
    let h = markup.text(h, name, allocator)?
    let h = markup.end(h, allocator)?
    return markup.render(h, allocator)
}
```

Each of `el` / `attr` / `text` / `raw` / `end` consumes the builder (`take`) and returns
a fresh `Html`, so rebind through the chain. `text` and `attr` escape their input; `raw`
emits pre-trusted markup verbatim. `end` closes the innermost open element, and `render`
produces the finished document as `[u8]`.

## Public surface

- **`markup`** — the `Html` builder: `new` (construct), `el` (open element), `attr` (set attribute), `text` (escaped content), `raw` (verbatim markup), `end` (close element), and `render` (emit bytes).
