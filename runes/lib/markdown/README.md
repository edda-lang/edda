# markdown

A small Markdown-to-HTML renderer — headings, paragraphs, lists, blockquotes,
fenced code, and inline emphasis — with HTML output escaped as it is written.
Reach for it when a server needs to turn a Markdown string into safe HTML.

## Install

```
edda add markdown
```

Then import the module you need:

```edda
import markdown.render.blocks
```

## Usage

```edda
import markdown.render.blocks

function page(md: String, allocator: Allocator) -> String
    with {allocator, err: alloc.AllocError}
{
    return blocks.to_html(md, allocator)?
}
```

`blocks.to_html` splits the input into lines, walks the block structure, and
returns an escaped HTML `String`. For finer control, the escaping string
builder is exposed directly: `sink.new(allocator)`, then `push_raw` /
`push_byte` / `push_escaped` / `push_escaped_bytes`, and `finish` to collect a
`String`.

## Public surface

- **`render.blocks`** — `to_html` (the top-level entry point).
- **`render.inline`** — `render`: inline emphasis/code spans into a `Sink`.
- **`escape.sink`** — `Sink`, `new`, `push_raw` / `push_byte` / `push_escaped` /
  `push_escaped_bytes`, `finish`: the HTML-escaping output builder.
- **`lines.scan`** — `Line` plus classifiers `split` / `is_blank` / `is_fence` /
  `is_hr` / `heading_level` / `is_ul_item` / `is_ol_item` / `is_blockquote` /
  `content`: the line-level scanner underneath the block renderer.
