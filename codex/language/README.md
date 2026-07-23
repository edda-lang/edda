# Edda — language reference

This directory contains the canonical, authoritative specification for
the Edda language. Read [`CHARTER.md`](../CHARTER.md) first; it states
the thesis, the eight Articles, and the design bets that the rest of
this material implements.

The eight documents below describe what Edda is as of the V1.0 surface
lock, independent of how it was built. Items deferred to post-V1.0 are
noted within each document under "Reserved for post-V1.0" sections; the
authoritative timeline lives in [`ROADMAP.md`](../ROADMAP.md), and the
compilation strategy behind the two compiler trees in
[`ARCHITECTURE.md`](../ARCHITECTURE.md).

## Documents

| File | Scope |
|------|-------|
| [`01-syntax.md`](01-syntax.md) | Lexical surface, declarations, expressions, types, patterns, the no-comment lock, the locked keyword set, hard removals. |
| [`02-modes-effects-refinements.md`](02-modes-effects-refinements.md) | Parameter modes (`let`/`mutable`/`take`/`init`), capability types with type-state, effect rows (including graded effects), refinement clauses (`where`/`requires`/`ensures`/`decreases`), trust hatches. |
| [`03-verification.md`](03-verification.md) | SMT discharge, proof certificates, termination via `decreases`, property-based testing, stability, content-addressed contract diff, diagnostics discipline. |
| [`04-specs-comptime.md`](04-specs-comptime.md) | Spec language (the only generic mechanism), comptime evaluator, derive forms, comptime introspection extensions, recursive types via `Box`. |
| [`05-concurrency-coherence.md`](05-concurrency-coherence.md) | Structured concurrency (`scope(exec)`), coherence regions (`scope(coherence)`), cancellation, type-state on capabilities, linear-flagged types. |
| [`06-tooling.md`](06-tooling.md) | Daemon, MCP, LSP, structural edits, compiler-emitted structmap, reading-discipline structure-map gating, diagnostics format, bidirectional synthesis surface, CLI verbs. |
| [`07-distribution.md`](07-distribution.md) | Content addressing, three-tier cache, certificate verifier, package layout (`package.toml`), the two publish verbs. |
| [`08-packages.md`](08-packages.md) | Mímir registry, rune archive format (`.rune`, tar.zst), the three independent hashes (`rune_hash` / `surface_hash` / `effect_hash`), manifest pins, lockfile + `lockfile_hash` trailer, `edda add` / `update` / `audit` / `publish` / `contract-diff` / `why` CLI, supply-chain security thesis. |

## How to read

If you are an LLM author starting on a task, the boot path is:

1. [`../CHARTER.md`](../CHARTER.md) — what Edda is for, and why.
2. The language doc that scopes your task. The file titles are
   descriptive; skim the index above to pick.
3. [`../ROADMAP.md`](../ROADMAP.md) only if you need to know whether a
   feature is V1.0-current or post-V1.0 roadmap.

For worked material that doesn't fit the language docs, see the
[`../examples/`](../examples/) directory — specification illustrations
exercising the locked surface.
