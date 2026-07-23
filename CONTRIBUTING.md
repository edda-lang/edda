# Contributing to Edda

Thanks for your interest in improving Edda. Contributions of every kind are
welcome — bug reports, fixes, standard-library and ecosystem packages,
specification clarifications, and documentation.

## Licensing of contributions

Edda is dual-licensed under [MIT](LICENSE-MIT) and
[Apache-2.0](LICENSE-APACHE), at the user's option
(`SPDX-License-Identifier: MIT OR Apache-2.0`). Contributions are accepted
under the same dual grant:

> Unless you explicitly state otherwise, any contribution intentionally
> submitted for inclusion in the work by you, as defined in the Apache-2.0
> license, shall be dual licensed as above, without any additional terms or
> conditions.

There is **no Contributor License Agreement (CLA)** and **no Developer
Certificate of Origin (DCO) sign-off** to complete. By opening a pull request
you license your contribution under the dual MIT OR Apache-2.0 grant; inbound
contributions are licensed identically to outbound distribution
(inbound = outbound). You retain copyright in your work.

If a contribution incorporates or is derived from externally licensed code,
say so in the pull request so its provenance can be recorded in
[COPYRIGHT](COPYRIGHT). This repository otherwise contains only original Edda
source.

## Commit authorship

Author your commits under your own identity — a real name or handle with an
email that resolves to your account (a GitHub `…@users.noreply.github.com`
address links commits to your profile without publishing a personal email).
This is how you are credited, so use an identity you want associated with the
work; contributions are not folded under a shared placeholder author.

Credit the account, not the model. Across the Edda projects, AI assistance is
assumed rather than disclosed — contributions are understood to be produced
with AI tooling under human direction, so which model was used carries no
meaningful information and is not recorded. Do not add `Co-Authored-By:`
trailers for AI tools or models; the responsible account is the author. The
copyright holder-of-record line in the LICENSE files ("The Edda Authors") is a
collective legal umbrella only — it is not a commit author, and individual
authors retain copyright in their own contributions.

## Before you write code

Edda is not a language you can guess your way through by analogy to another —
the syntax and the effect/capability/refinement model are specific and locked.
Read the specification first:

- **[`codex/CHARTER.md`](codex/CHARTER.md)** — the thesis, the Articles, and
  the locked design bets.
- **[`codex/language/`](codex/language/)** — the reference: syntax, effects and
  refinements, verification, specs and comptime, concurrency, tooling, and
  packages.
- **[`codex/ROADMAP.md`](codex/ROADMAP.md)** — current state and the path to
  v1.0.

If an agent writes your Edda, point it at **[`AGENTS.md`](AGENTS.md)** first —
the machine-facing language reference, the same document the models that wrote
this repository worked from.

A few conventions worth knowing up front:

- **Read the structure maps before source.** The compiler emits an `index.toon`
  per source directory — signatures, effect rows, refinements, call graph.
  Read the chain from the workspace root down to the directory you're changing
  before opening `.ea` files; it tells you what exists and what depends on it.
  A fresh clone has no maps yet — run `edda build` once to materialize them.
- **Edda source admits no comments.** Claims about code live in effect rows,
  refinements, and attributes; descriptions are derived by the compiler into
  the `index.toon` structure maps. Do not add prose to source.
- **Contracts are proved, not hoped.** `requires` / `ensures` / `decreases`
  and the built-in obligations discharge at compile time — a change that breaks
  a contract fails the build.
- **Effects and capabilities are explicit.** New authority a function exercises
  belongs in its `with { }` row and its parameter list, never ambient.

## Finding something to work on

Issues labelled **`good first issue`** are self-contained: each states the
problem, names the directory (and structure map) to start from, and says what
`edda build` or `edda test` must show when it's done. The lowest-friction entry
points are `runes/` packages and `std/` gaps; compiler and verifier internals
(`compiler/lib/refine/`, codegen parity) suit contributors who want the deep
end.

## Submitting changes

1. Open an issue describing the bug or proposal before large changes, so the
   design can be discussed.
2. Keep each pull request focused on a single, self-contained change.
3. Make sure the workspace builds and its contracts discharge (`edda build`)
   before you submit — a clean `edda check` alone does not discharge
   refinement obligations.

By submitting, you agree to license the contribution as described above.
