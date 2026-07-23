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

---

## 1. Install the toolchain

One line installs a self-contained toolchain — the `edda` binary, its runtime, and a
vendored `std` and `runes`. There's no Rust, LLVM, or Z3 to install and **no environment
variable to set**; the only external requirement is a system linker (MSVC Build Tools on
Windows, `lld`/`mold` on Linux, the Xcode Command Line Tools on macOS).

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/edda-lang/edda-bootstrap/main/install.ps1 | iex
```

```sh
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/edda-lang/edda-bootstrap/main/install.sh | bash
```

The installer downloads the release archive for your platform, unpacks it (to
`~/.edda-bootstrap`), and adds `edda` to your PATH. **Your current shell won't see it yet** —
open a new shell, or call the binary by its full path for the first check:

```sh
edda version                        # new shell
~/.edda-bootstrap/bin/edda version  # same shell (edda.exe on Windows)
```

You should see `edda (bootstrap-rust) <version>` and your host target.

**Platform status:** Windows x64 (`x86-64-windows-msvc`) is the verified platform today.
Linux and macOS archives are rolling out through CI — until yours lands, the installer
reports `no release asset for <platform>`; in the meantime build the reference compiler
from source (see the [`edda-bootstrap`](https://github.com/edda-lang/edda-bootstrap) README
for the current prerequisites and `cargo xtask build`) and point `EDDA_STDLIB_ROOT` at a
[monolith](https://github.com/edda-lang/edda) checkout's `std`. If you're on Linux or macOS,
your "it worked" (or a bug report) is the most useful thing you can send back — see
[Contribute](https://github.com/edda-lang/edda).

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
default_target = "x86-64-windows-msvc"    # your host triple; see the note below
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

Set `default_target` to your host triple in **dash form**: `x86-64-windows-msvc`,
`x86-64-linux-gnu`, `aarch64-macos-darwin`, … `edda version` prints the same target with
**underscores** (`x86_64-windows-msvc`) — it's the same triple; `package.toml` takes the
dash form.

Every capability `main` may use is named in its signature — this program holds only
`Stdout`, so it can only print. `non_negative` carries a contract: `requires` states what
the caller must guarantee, `ensures` what the function guarantees back.

> **Run it from a neutral directory** — not as a sibling of a local `edda-stdlibs` or
> monolith checkout. The compiler auto-discovers a stdlib checkout sitting next to your
> project and will use *that* worktree instead of the bundled `std`, which can quietly
> change what you're building against.

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

You now have a clean, contract-verified project — copy this directory as the starting point
for your next Edda program, or re-run these steps for a fresh one.

---

## Hand it to your agent

The point of Edda is that your agent writes it. Paste this into your coding agent:

```
Read AGENTS.md (the Edda language reference) in this project. Then build me <what you
want> in Edda, here. Run `edda build` after every change and fix exactly what it
reports — the build is the source of truth.
```

`AGENTS.md` at the root of the [monolith](https://github.com/edda-lang/edda/blob/main/AGENTS.md)
is the canonical, agent-facing language reference. Edda is not in most models' training
data, so having the agent read it first is what makes the loop work.

### Or: let your agent set itself up

You don't have to install anything by hand. Tell your agent:

```
I want to use the Edda language — edda-lang.org
```

Any agent that can browse finds [`/llms.txt`](https://edda-lang.org/llms.txt) and follows
the canonical setup recipe at [`/get-started/agent.txt`](https://edda-lang.org/get-started/agent.txt):
it installs the toolchain, places the language reference for your harness (Claude Code,
Cursor, Codex, Copilot, Gemini, Windsurf…), installs the Edda skill, **asks you before**
enabling the optional reading-discipline hooks, and scaffolds this exact contract example.
The human-readable twin of that recipe is [`/get-started/agent`](https://edda-lang.org/get-started/agent).

## Using a rune (a package)

The first-party runes (HTTP, JSON, CSS, regex, TLS, and more) ship inside the toolchain
archive. Depend on one by adding a `path+` dependency pointing at its directory in the
vendored `runes/` (or, if you built from source, your monolith checkout):

```toml
[[dependencies]]
name = "slug"
version = "0.1.0"
source = "path+/absolute/path/to/runes/lib/slug"
```

```edda
import slug.slugify

let s = slugify.slugify("Hello, Edda World!", allocator)?
```

`slugify` returns `"hello-edda-world"`. `edda add` targets the Mímir registry, which isn't
live yet — until it is, add dependencies by editing `package.toml` as above.

## Next

- The language reference: [`/language`](https://edda-lang.org/language) and the canonical
  [`AGENTS.md`](https://github.com/edda-lang/edda/blob/main/AGENTS.md).
- Why the build refuses bad code: [`/verification`](https://edda-lang.org/verification).
- Everything else: [`/docs`](https://edda-lang.org/docs).
- The source: [`edda-lang/edda`](https://github.com/edda-lang/edda) (language, std, runes,
  this site) and [`edda-lang/edda-bootstrap`](https://github.com/edda-lang/edda-bootstrap)
  (the reference compiler).
