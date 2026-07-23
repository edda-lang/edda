# static

Static file serving — read a file off a read-only filesystem and pair its bytes
with a MIME content type inferred from the path extension, ready to hand back as
an HTTP response body. The content-type guess covers the common web types
(HTML, CSS, JavaScript, JSON, images, fonts, and so on).

## Install

```
edda add static
```

Then import the module you need:

```edda
import static.serve
```

## Usage

```edda
import static.serve

function load_asset(rfs: ReadOnlyFilesystem, path: String, allocator: Allocator) -> serve.Served
    with {rfs, allocator, err: serve.StaticError}
{
    let mounted = serve.mount(rfs, "assets")
    return serve.read_file(mounted, path, allocator)?
}
```

The returned `Served` carries `content_type: String`, `bytes: [u8]`,
`content_length: usize`, and `cache_control: String`. Use
`serve.content_type_for(path)` on its own when you only need the MIME string —
it is pure and takes no capability.

`read_file` rejects any path containing a `..` segment with
`StaticError.traversal_rejected` before touching the filesystem. Pair it with
`serve.mount(rfs, root)` — a thin wrapper over `fs.scoped_to` — to sandbox a
directory before serving out of it.

## Public surface

- **`serve`**
  - `read_file(rfs: ReadOnlyFilesystem, path: String, allocator: Allocator) -> Served` — rejects path traversal, then reads the file and tags it with a content type + caching headers; row `{rfs, allocator, err: StaticError}`.
  - `mount(rfs: ReadOnlyFilesystem, root: String) -> ReadOnlyFilesystem` — narrows `rfs` to a directory subtree; row `{rfs}`.
  - `content_type_for(path: String) -> String` — MIME type from the path extension (pure).
  - `has_traversal(path: String) -> bool` — true if `path` contains a `..` segment (pure).
  - `Served` — `{ content_type: String, bytes: [u8], content_length: usize, cache_control: String }`.
  - `StaticError` — `traversal_rejected` / `filesystem(fs.FsError)`.

`read_file` takes a `ReadOnlyFilesystem` capability, so it cannot write or reach
outside the filesystem it is handed.
