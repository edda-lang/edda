# Get started with Edda

Edda is built to be written by an LLM. You don't have to learn the language first —
your agent does. This quickstart takes you from nothing to a **built, contract-verified
Edda program** on your machine. Point your agent (Claude Code, Cursor, or any coding
agent) at it and follow along; the whole thing is a ~10‑minute loop.

This is the single source for the quickstart: the site page at `/get-started` and the
starter template's README both render from it. Keep them in sync by editing here.

> **Which compiler am I using?**
> Today you're building with Edda's reference compiler — the Rust bootstrap. The native
> compiler is written in Edda itself, type-checks its own full source, and emits binaries
> through its own backend; we're closing the last behavioral-parity gap before it replaces
> the bootstrap entirely. Same language, same checks, either way — the bootstrap is simply
> the mature path today, and everything you build now carries forward.

A one-line installer downloads a **self-contained toolchain** — the `edda` binary, its
LLVM runtime, and a vendored `std` and `runes` — so there's no Rust, LLVM, or Z3 to
install and no environment variables to set. Windows is available now; if no archive
exists for your platform yet, build from source (see the end of step 1).

---

## 1. Install the toolchain

Run the installer for your platform. It downloads the archive, unpacks it, and puts `edda`
on your `PATH`.

```sh
# Windows (PowerShell)
irm https://raw.githubusercontent.com/edda-lang/edda-bootstrap/main/install.ps1 | iex

# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/edda-lang/edda-bootstrap/main/install.sh | bash
```

Confirm it with:

```sh
edda version
```

The archive is self-contained — it bundles `std` and `runes`, so nothing else to clone and
no `EDDA_STDLIB_ROOT` to set. All you need on the machine is a system linker (`lld-link`/MSVC
on Windows, `ld`/`mold`/`lld` on Linux, `ld64` on macOS).

**Platform status:** Windows x64 (`x86-64-windows-msvc`) is available now and is the
verified platform. Linux and macOS archives are still rolling out through CI — until yours
lands, the installer reports `no release asset for <platform>`. In the meantime, build the
reference compiler from source: clone
[`edda-bootstrap`](https://github.com/edda-lang/edda-bootstrap) and run `cargo xtask build`
(prereqs in its README — a recent **Rust** (2024 edition), **CMake**, **Python**, LLVM 18
dev libraries, and a **C/C++ toolchain with a system linker**; Z3 is vendored), then clone
[`edda`](https://github.com/edda-lang/edda) and set `EDDA_STDLIB_ROOT="$PWD/edda/std"`. If
you're on Linux or macOS, your "it worked" (or a bug report) is the most useful thing you
can send back. See [Contribute](https://github.com/edda-lang/edda).

## 2. Create a project

A package is a `package.toml` plus a `src/` directory. Make a small but *real* one — a
program with one capability and one contract, so the very first build proves something:

`package.toml`
```toml
[package]
name = "hello"
version = "0.1.0"
root_namespace = "hello"

[build]
default_target = "x86-64-linux-gnu"    # your host triple: x86-64-windows-msvc, aarch64-macos-darwin, ...
```

`src/main.ea`
```edda
module hello.main

import std.io.stream

function non_negative(x: i64) -> i64
    requires x >= 0
    ensures result >= 0
{
    return x
}

public function main(out: Stdout) -> ()
    with {out}
{
    let y = non_negative(7)
    out.print_line(f"non_negative(7) = {y}")
}
```

Every capability `main` may use is named in its signature — this program holds only
`Stdout`, so it can only print. `non_negative` carries a contract: `requires` states what
the caller must guarantee, `ensures` what the function guarantees back.

## 3. Build and run

```sh
cd hello
edda check     # fast loop: typecheck (parse + resolve + types)
edda build     # the truth: typecheck, discharge every contract, emit a native binary
edda run       # build, then execute
```

`edda run` prints:

```
non_negative(7) = 7
```

## 4. Break it — watch the build refuse

This is why Edda exists. Delete the `requires x >= 0` line from `non_negative` and build
again:

```sh
edda build
```

The compiler refuses — and hands you the exact input that breaks the contract:

```
error[refinement_unproven]: ensures clause 0: (result >= 0)
 --> src/main.ea:5:5
    note: counter-example:
    note:   result = -1
    note:   x = -1
```

Without the precondition, `non_negative` can no longer guarantee its result is
non-negative — the solver finds `x = -1` and rejects the program before it ever runs. Put
the line back and the build passes again. An agent-introduced bug that violates a contract
fails the build with a concrete counter-example, not a runtime surprise.

---

## Hand it to your agent

The point of Edda is that your agent writes it. Paste this into your coding agent:

```
Read AGENTS.md (the Edda language reference) in the edda repo. Then build me <what you
want> in Edda, in this project. Run `edda build` after every change and fix exactly what
it reports — the build is the source of truth.
```

`AGENTS.md` at the root of the [monolith](https://github.com/edda-lang/edda/blob/main/AGENTS.md)
is the canonical, agent-facing language reference. Edda is not in most models' training
data, so having the agent read it first is what makes the loop work.

### Or: let your agent set itself up

You don't have to paste the reference by hand. Tell your agent:

```
I want to use the Edda language — edda-lang.org
```

Any agent that can browse finds [`/llms.txt`](https://edda-lang.org/llms.txt), reads its
own setup at [`/get-started/agent`](https://edda-lang.org/get-started/agent), places the
reference for your harness (Claude Code, Cursor, Codex, Copilot, Gemini, Windsurf…), and
**asks you before** installing the optional reading-discipline hooks. The same steps are
served machine-readably as a recipe at
[`/get-started/recipe`](https://edda-lang.org/get-started/recipe).

## Using a rune (a package)

The 36 first-party runes (HTTP, JSON, CSS, regex, TLS, and more) live under
`edda/runes/lib/`. Depend on one by adding a `path+` dependency pointing at its directory
in your monolith checkout:

```toml
[[dependencies]]
name = "slug"
version = "0.1.0"
source = "path+/absolute/path/to/edda/runes/lib/slug"
```

```edda
import slug.slugify

let s = slugify.slugify("Hello, Edda World!", allocator)?   # -> "hello-edda-world"
```

`edda add` targets the Mímir registry, which isn't live yet — until it is, add
dependencies by editing `package.toml` as above. Once prebuilt toolchain archives ship,
runes are vendored alongside `std` and the `path+` line points inside the toolchain
instead of your checkout.

## Next

- The language reference: [`/language`](https://edda-lang.org/language) and the canonical
  [`AGENTS.md`](https://github.com/edda-lang/edda/blob/main/AGENTS.md).
- Why the build refuses bad code: [`/verification`](https://edda-lang.org/verification).
- Everything else: [`/docs`](https://edda-lang.org/docs).
- The source: [`edda-lang/edda`](https://github.com/edda-lang/edda) (language, std, runes,
  this site) and [`edda-lang/edda-bootstrap`](https://github.com/edda-lang/edda-bootstrap)
  (the reference compiler).
