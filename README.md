# Edda

Edda is a systems programming language and toolchain built so a codebase stays coherent enough for an LLM to work in it correctly, no matter how large it grows. Every function signature carries its full contract — side effects in a `with { }` row, capabilities (`Filesystem`, `Network`, `Allocator`, …) as unforgeable arguments, `requires`/`ensures` refinements proved at compile time by an in-tree SMT solver — and every build emits a structure map of every directory, derived from the compiler's own checked data, so a model or a person sees what exists and what depends on it before touching a file.

Edda is written in itself: roughly 230,000 lines — a ~178,000-line self-hosting compiler, the standard library, and the package ecosystem — written by LLMs that had never seen the language; there was no Edda to train on. A [Rust bootstrap compiler](https://github.com/edda-lang/edda-bootstrap) is the reference implementation that builds the native compiler; both are public, so the whole chain rebuilds from scratch. The native compiler emits code for x86-64, AArch64, and WebAssembly; Windows is the verified platform today, with Linux and browser-WASM bring-up underway — verifying a platform on your machine is a first contribution that needs no Edda knowledge.

Edda is named after the 13th-century Old Norse codex compiled by Snorri Sturluson — one large upfront effort that later generations built on without redoing. The language follows the same model: the heavy work lives in the compiler, verifier, and standard library, so downstream code carries its full contract on the surface.

## Highlights

- **Structure maps:** every build emits an `index.toon` per source directory — signatures, effect rows, refinements, call graph — derived from type-checker data. A build artifact, not documentation; it cannot drift from the source.
- **Effects in signatures:** I/O, allocation, and divergence are listed in a function's `with { }` row; `?` propagates typed errors (`err: T`) and nothing else.
- **Capabilities as values:** `Filesystem`, `Network`, `Allocator`, and 15 other capability types arrive as arguments and narrow one-way — a signature names the maximum authority a function can exercise.
- **Refinements proved, not hoped:** `requires` / `ensures` / `decreases` and built-in obligations (overflow, bounds, division-by-zero) lower to SMT and discharge at compile time.
- **Specs, not generics:** no `<T>` parameters and no traits; reuse is `spec` templates, content-addressed and monomorphised per instantiation.
- **No comments:** the lexer rejects them. Claims about code live in effect rows, refinements, and attributes — places the compiler checks — never in prose that can drift.

## Example

```edda
public function main(out: Stdout) -> () with {out} {
    out.print_line(f"clamped: {clamp(42, 0, 10)}")
}

function clamp(value: i32, lo: i32, hi: i32) -> i32
    requires lo <= hi
    ensures  result >= lo
    ensures  result <= hi
{
    return if value < lo { lo } else if value > hi { hi } else { value }
}
```

`main` receives a `Stdout` capability and declares it in `with {out}`; `clamp` carries a contract the compiler proves before the program runs. Drop `requires lo <= hi` and the `ensures` bounds no longer discharge — the build fails rather than the program.

## Repository layout

```
compiler/   the self-hosting compiler — an Edda workspace of 44 members
std/        the std.* standard library — 113 packages: core, collections, io, os, math, net, crypto, text, time, …
runes/      36 ecosystem packages from the Mímir registry — HTTP, TLS, JSON, SQL, templating, …
web/        first-party Edda applications; the flagship is the language website, itself a verified Edda program
codex/      the language specification and design notes
```

## Install

The prebuilt toolchain is a self-contained archive — the `edda` binary, its LLVM runtime, and a vendored `std` and `runes` — with no Rust, LLVM, or Z3 to install. The installer downloads and unpacks it and puts `edda` on your `PATH`.

**Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/edda-lang/edda-bootstrap/main/install.ps1 | iex
```

**Linux / macOS**:

```sh
curl -fsSL https://raw.githubusercontent.com/edda-lang/edda-bootstrap/main/install.sh | bash
```

Windows (`x86-64-windows-msvc`) is available now and is the verified platform. Linux and macOS archives are still rolling out through CI — until yours lands, the script reports `no release asset for <platform>`; build [from source](#build-from-source) in the meantime.

The archive is self-contained, so `edda` needs no environment variables — only a system linker (MSVC Build Tools on Windows, `lld`/`mold` on Linux, the Xcode Command Line Tools on macOS). From a workspace in this repository (`compiler/`, `std/`, `runes/`, or `web/`):

```sh
edda version   # confirm the toolchain is on PATH
edda build     # type-check + refinement discharge + codegen
edda check     # type-check only
edda run       # build, link, and execute
```

The compile pipeline, target matrix, and per-verb status are in [`compiler/README.md`](compiler/README.md).

## Build from source

The whole chain rebuilds from source: the [Rust bootstrap compiler](https://github.com/edda-lang/edda-bootstrap) produces an `edda` binary, and that binary builds the native compiler and everything else in this tree. This is the path to use where no prebuilt archive exists yet, or when hacking on the bootstrap itself.

```sh
git clone https://github.com/edda-lang/edda-bootstrap
cd edda-bootstrap && cargo build --release
```

Building the bootstrap needs a recent Rust (2024 edition), CMake, Python, and a C/C++ toolchain with a system linker; it links against LLVM 18 development libraries, so set `LLVM_SYS_180_PREFIX` to your LLVM 18 install. Z3 is vendored and statically linked. The bootstrap's own prerequisites and build steps are in its README. A from-source build resolves `std`/`runes` from this repository — set `EDDA_STDLIB_ROOT` to this checkout's `std/` when building outside it.

## Working with agents

The workflow that built Edda ships with it:

- [`AGENTS.md`](AGENTS.md) is the machine-facing language reference — the same document the models that wrote this repository worked from. Point your agent at it before it writes any Edda.
- Agents read the `index.toon` structure-map chain top-down before opening source, which keeps the context needed for any one change bounded at any project size. A fresh clone has no maps yet — run `edda build` once to materialize them.
- [`docs/authoring/guide.md`](docs/authoring/guide.md) covers the special-operations surface: verification tooling, property-based testing, comptime introspection, capability typestate, and distribution.

## Status

Pre-1.0. The bootstrap compiler builds the whole tree — the native compiler included — to runnable binaries across the locked V1.0 surface. The native compiler, written in Edda, type-checks its own full source and compiles through its own backend (no LLVM); reaching full self-compilation is currently gated by the native compiler's performance — chiefly the memory it needs to build its heaviest members. The language surface is locked — the two compilers target the same feature set, with no deferrals between them. There is no LSP or debugger yet.

## Documentation

- [edda-lang.org](https://edda-lang.org) — the language site (served by `web/lib/website`).
- [`codex/CHARTER.md`](codex/CHARTER.md) — the thesis, the eight Articles, and the locked design bets.
- [`codex/ROADMAP.md`](codex/ROADMAP.md) — current state and the path to v1.0.
- [`codex/language/`](codex/language/) — the eight-document reference: syntax; modes, effects, and refinements; verification; specs and comptime; concurrency; tooling; distribution; packages.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first issues are labelled on the issue tracker; community links are on [edda-lang.org](https://edda-lang.org).

## License

Edda is licensed under either of [Apache License, Version 2.0](LICENSE-APACHE) or [MIT license](LICENSE-MIT), at your option (`SPDX-License-Identifier: MIT OR Apache-2.0`). Contributions are dual-licensed under the same terms, with no CLA (inbound = outbound); see [CONTRIBUTING.md](CONTRIBUTING.md) and [COPYRIGHT](COPYRIGHT).
