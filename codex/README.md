# Edda

A low-level systems language for the LLM era. Total control over hardware, zero-cost abstractions, capability-based effects with refinement-discharged contracts, and a structural surface (modes, effect rows, refinements on every signature) chosen for high-density LLM-readable code.

Edda is named after the 13th-century Old Norse codex compiled by Snorri Sturluson — one massive upfront effort that captured a body of mythology so completely that every subsequent generation has built on it without recovering it from scratch. The language follows the same model: maximum pre-work in the compiler, runtime, and standard library, so downstream code stays clean, fast, and correct.

## Design thesis

Edda provides the LLM author with all the context the model could possibly need to generate correctly. The bet is not that future models will be perfect; even with capable models, generation quality is bounded by context signal density. Verbose, explicit, locally-readable code with effects, modes, refinements, and capabilities on every signature is the highest-signal-density representation of "what this code does and what it requires" we can give a generator. The language defends against the floor of model behavior, not the ceiling.

A human reads the same signature and gets the same information. Edda is a dual-audience language — the LLM is the *distinguishing* constraint, but no design choice is made at the human author's expense.

## Status

The language surface is locked; the specification below describes it in full. The Rust bootstrap compiler implements the full pipeline (`parse → resolve → typecheck → codegen → MIR → LLVM → link`) and builds the whole monorepo — the native compiler included — to runnable binaries on Windows, Linux, and macOS. The native compiler — written in Edda — type-checks its own full source and emits runnable binaries through its own backend (no LLVM); reaching full self-compilation is currently gated by the native compiler's performance — chiefly the memory it needs to build its heaviest members. Bootstrap and native target the same locked feature set — there are no "v1.0 deferrals" of language features. Full details in [`ROADMAP.md`](ROADMAP.md).

## Documents

- **[`CHARTER.md`](CHARTER.md)** — the thesis, the eight founding Articles, the locked design bets, the hard removals.
- **[`ROADMAP.md`](ROADMAP.md)** — current state and the linear path to v1.0.
- **[`ARCHITECTURE.md`](ARCHITECTURE.md)** — how Edda is compiled: the two compiler trees, the native codegen pipeline, and the verified-at-every-boundary discipline.
- **[`language/`](language/)** — the eight-doc canonical language specification. Start with [`language/README.md`](language/README.md).
  - [`01-syntax.md`](language/01-syntax.md) — lexical, declarations, expressions, types, patterns
  - [`02-modes-effects-refinements.md`](language/02-modes-effects-refinements.md) — parameter modes, capability types, effect rows, refinement clauses
  - [`03-verification.md`](language/03-verification.md) — SMT discharge, certificates, termination, PBT, stability, contract diff
  - [`04-specs-comptime.md`](language/04-specs-comptime.md) — specs, comptime, derive forms, comptime introspection
  - [`05-concurrency-coherence.md`](language/05-concurrency-coherence.md) — scope(exec), scope(coherence), type-state, linear types
  - [`06-tooling.md`](language/06-tooling.md) — daemon, MCP, LSP, structural edits, compiler-emitted structmap
  - [`07-distribution.md`](language/07-distribution.md) — content addressing, runes (`.rune` packs), three-tier cache, certificate verifier
  - [`08-packages.md`](language/08-packages.md) — Mímir package management, three-hash SemVer, manifest pins, lockfile
- **[`examples/`](examples/)** — worked examples exercising the locked surface
- **[`tools/`](tools/)** — editor support (the `vscode-edda` extension)

## License

MIT OR Apache-2.0, like the rest of the repository — see the root
[`LICENSE-MIT`](../LICENSE-MIT) and [`LICENSE-APACHE`](../LICENSE-APACHE).
