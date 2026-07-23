# web

First-party Edda applications, each a workspace member under `lib/<member>/` consuming `../runes/` packages by path dependency. One member today: [`lib/website`](lib/website/).

## `lib/website`

The [edda-lang.org](https://edda-lang.org) site — a server-rendered Edda program. `main` takes `Network`, `Stdout`, `ReadOnlyFilesystem`, and `Allocator` capabilities; `serve.ea` accepts connections directly over `std.net.socket` and decodes/encodes each request through `hermod`'s wire codec, using only `httpserver`'s frame reader to find request boundaries (the accept loop is hand-rolled, not `httpserver.serve`). Routes, page layout, and copy are all verified Edda source, with no client-side framework.

`route.dispatch` maps a request path to one of `home`, `start`, `language` (with a syntax reference split into functions/types/modes/effects/refinements/specs subpages), `concurrency`, `verification`, `distribution`, `tooling`, `design`, `build` (with `cli`/`servers`/`wasm`/`embedded` variants), `docs`, or `notfound`. `layout.ea` wraps every page in shared nav/footer chrome; `ui/` holds the HTML component helpers (`card`, `link`, `page_head`, ...) pages build with; `style/` assembles the site's CSS through the `css` rune.

## Building and running

```bash
cd lib/website
edda run
```

The built binary serves the site at `127.0.0.1:8080`.

## Layout

```
lib/website/src/
  server/       entry point main(net, out, rfs, allocator), socket accept loop + request/response codec, path -> page dispatch
  layout.ea     shared nav + footer chrome
  ui/           shared HTML component helpers
  style/        CSS stylesheet, assembled via the css rune
  pages/        one directory per route, each a page.ea with render(h, allocator)
```
