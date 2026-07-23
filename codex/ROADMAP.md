# Edda Roadmap

This document is the single linear narrative of where Edda is, what has to land, and what shipping v1.0 means. The earlier phase-based roadmap is archived. Read this alongside the CHARTER and the language docs in `codex/language/`.

The thesis is unchanged: Edda hands the LLM author every piece of context the model could plausibly need to generate correctly, defending against the floor of model behavior rather than relying on the ceiling. Everything that follows is in service of that bet.

(Note: "Where We Are" is a status snapshot — a point-in-time record of self-hosting progress, not a locked-surface record. It is refreshed on its own cadence; the locked language surface lives in the CHARTER and `codex/language/`.)

## Where We Are

The toolchain is mid–self-hosting. Two compilers exist for the one locked language (see [`ARCHITECTURE.md`](ARCHITECTURE.md)), and the cascade gaps the earlier snapshot named have been worked through.

The Rust bootstrap (`dev-bootstrap-rust`) is the current build authority. It runs the full pipeline — parse, resolve, typecheck, comptime evaluation, SMT discharge, codegen to MIR, lowering to LLVM IR, native object emission, and link — in a single `edda build`, and produces runnable native binaries on Windows, Linux, and macOS. The locked surface exercises end-to-end through it: capability-passed allocation, effect handlers and `?` propagation, spec monomorphisation, and closures all lower and execute. The behavioral-test corpus builds and runs each fixture through the bootstrap as the differential oracle; the runtime stub-panics, the `Executor` resolver gap, and the MIR-lowering walls that the earlier snapshot named are resolved.

The native compiler — written in Edda, under `compiler/lib/` — **self-typechecks the workspace**, and its self-hosted toolchain (T1, built from `compiler/lib/edda`) **emits runnable native binaries** through its own backend: MIR → HLIR → LIR → x86-64 → COFF, with no LLVM anywhere in the native pipeline. The typecheck frontier is crossed. What gates full self-compilation now is **the native compiler's performance** — building its heaviest members currently costs more memory than the pipeline should need, and that footprint, not any language or feature gap, is the present wall. Behind it sits the **behavioral-parity** campaign — making T1-built binaries behave exactly like bootstrap-built ones — where the differential corpus and the self-host fixpoint surface miscompiles in the places a young backend earns them (aggregate call-argument conventions, closure environments, the task runtime's ABI, the long tail of by-memory lowering shapes), each closing as a small, tested fix against the same corpus that will eventually certify parity.

The standard library under `std/` parses and typechecks, and is exercised by real consumers — the native compiler is itself the largest such consumer, and the behavioral corpus exercises the stdlib instantiation paths the earlier prototype could not reach.

That is the concrete shape: a bootstrap shipping runnable binaries across the locked surface; a native compiler that self-typechecks the workspace and ships binaries through its own backend; a present gate of **compiler performance** — the memory cost of building the heaviest members — ahead of a codegen-parity campaign, driven by differential testing, as the remaining distance to a retired bootstrap. This is late-cascade — the design locked, the frontend crossed, the work left of the patient kind.

## Bootstrap Completeness

The bootstrap work divided into three groups, and the substance of all three has landed. None of it deferred to v1.0. The bootstrap is the validation vehicle for the thesis; if the language does not work in the bootstrap with everything switched on, native won't work either. The only thing "bootstrap" about the bootstrap is that it's written in Rust.

The first group — closing the cascade gaps — is done. MIR coverage handles the shapes the resolver produces (multi-segment path lookups, non-`FnPtr` indirect callees, projection through arrays of function pointers); the runtime stubs in `edda-rt` have real bodies; the `Executor` resolver gap is filled, with the capability type, alias tracing, and the `with`-clause threading it required.

The second group implemented the locked language features across the bootstrap, and nearly all of them are live: graded effects; stability (`stable function` / `stable type` with contract-hash anchoring); coherence regions; rune-level contract diff (`edda contract-diff`); termination (`decreases <expr>`, with absence implying the divergence effect); refinement-implied PBT (`edda test --properties`); the capability-safe stdlib lint; the derive forms; type-state on capabilities; linear and affine markers; and the compiler-emitted structure map (`edda build` writes `index.toon` directly from the resolver and typechecker, eliminating the drift surface where an external scanner and the compiler could disagree). A known tail remains, tracked per item in the language docs' implementation-status notes rather than here: the per-function contract-diff query, the bidirectional-synthesis surface (`inspect.synthesize` and the `edda synth` verb), the `refinements_of` / `pattern_of` comptime introspection built-ins, and the `target.supports` resolver wiring. One planned item was removed rather than built: doc-as-test died with the comment system — there are no doc comments left to compile, and the compiling-example corpus at `docs/authoring/examples/` fills the role it was meant to serve.

The third group — lifting every diagnostic to the locked discipline (the canonical form of the offending construct, the obligation trace for refinement and effect failures, a counterexample rendered in source form when one exists) — is the least finished of the three: the verification path holds the bar, while parts of the wider surface still emit span-plus-string diagnostics. It remains bootstrap work in the original sense; the native rewrite inherits the discipline, not the mechanism for installing it.

All three groups landed in the Rust bootstrap. There was no "we will do this in the self-hosted version." The self-hosted version reproduces what the bootstrap already does, byte-for-byte.

## Validation Criteria

The six criteria this section originally named were written before the bootstrap reached completeness. They are recorded here as they closed, because how they closed is itself evidence for the thesis.

First, worked examples build and run end-to-end. The compiling example corpus lives at `docs/authoring/examples/` and builds as an ordinary workspace package; `codex/examples/` holds specification illustrations. A deeper scale exercise — a complete multi-phase interpreter pipeline — served as the stress test for this criterion; written against an earlier draft of the surface, it predates the locked language and no longer builds against it, so it sits outside the public example corpus today.

Second, the integration test grew past its original bar. This criterion named a bytecode-VM prototype (`lox-vm`) as the chosen integration test for multi-segment paths, indirect calls through arrays of function pointers, stdlib `Vec` instantiation, and a non-trivial dispatch loop. The native compiler itself — the largest Edda program in existence, exercising every one of those shapes — became the integration test instead, and the bootstrap hosts it end-to-end.

Third, the standard library instantiates against real consumers. It has grown from the originally-planned 22 modules to a workspace of over a hundred packages, its largest consumer is the native compiler, and the behavioral corpus exercises the instantiation paths isolated smoke tests could not reach.

Fourth, the security-port corpus — real-world CVEs re-expressed in Edda to show, by construction or by failed obligation, that the surface would have prevented each bug — was never built as in-tree artifacts. It remains worthwhile thesis-evidence work, but nothing gates on it; the verified compiler and the differential corpus carry the evidentiary weight it was meant to add.

Fifth, every locked feature has a working exercise. The behavioral-diff corpus runs each fixture through both compilers, and the per-feature implementation-status notes in `codex/language/` track the residual gaps precisely — graded-effect bound verification, the synthesis surface, and the introspection tail are the notable open entries.

Sixth, the bootstrap can compile its own self-hosting target — demonstrated in the strongest available form. The original threshold was a rewritten lexer compiling byte-identical through the bootstrap; what actually happened is the bootstrap compiling the entire native compiler, which then type-checks the workspace and emits runnable binaries itself. Bootstrap completeness is closed; the open campaign is native parity, currently gated by the native compiler's performance on its heaviest members.

## Self-Hosting Transition

The Rust bootstrap gets retired. v1.0 is the self-hosted compiler. The transition runs in stages, each with byte-identical output as its exit criterion and a Rust-deletion commit as its closing gate. These are stages of the transition, not phases of the language; the language is locked.

The first stage is the **frontend**. The lexer, AST, and parser are rewritten in Edda. The exit criterion is byte-identical output to the Rust bootstrap on the locked surface — every `.ea` file under `codex/` produces the same token stream and the same AST. The Rust frontend is deleted at stage close.

The second stage is the **resolver and storage layer**. The Edda resolver replaces the Rust resolver; the BLAKE3 content-addressing, manifest emission, and cascade walker move into Edda. Exit criterion is the same: identical resolution output on the corpus. The Rust resolver is deleted.

The third stage is the **type system**. Bidirectional inference, effect checker, SMT discharge — all in Edda. Discharge runs through the native in-tree solver (`compiler/lib/refine/src/solver/` — a CDCL SAT core driving LIA/EUF/array theory solvers; no external Z3 process, no `Subprocess` dependency), which the bootstrap's Z3-backed discharge must match bit-for-bit on obligation verdicts. Exit criterion: identical typecheck output, identical obligation traces, identical refinement results. Rust types deleted.

The fourth stage is **comptime and the spec engine**. The comptime evaluator and spec materialization layer run on Edda. This closes the metaprogramming surface entirely on Edda. Rust comptime and codegen deleted.

The fifth stage is the **native codegen smoke-test deliverable**. The native compiler's `lib/backend/` lands incrementally per the milestone sequence locked in [`ARCHITECTURE.md`](ARCHITECTURE.md): HLIR design lock, LIR design lock, e-graph kernel, boundary verifier, MIR→HLIR lowering, HLIR→LIR lowering, x64 instruction selection, x64 encoder, COFF emission. The smoke-test exit criterion is `function main() -> i32 { return 42 }` lowered MIR → HLIR → LIR → x86-64 → COFF, linked against `dev-bootstrap-rust_rt.lib`, executing and exiting 42 — own-codegen proof-of-life on a single end-to-end path. This is a code-landing stage, not a deletion stage; the bootstrap continues to emit through LLVM.

The sixth stage is **native codegen coverage parity**. Native lowering grows in the locked sequence: arithmetic → control flow → calls → memory → arrays → effect-attribute consumption → discharged-refinement check elision → typestate-aware optimization → e-graph rule corpus → refinement-driven autovec → PGO ingestion. Coverage parity is reached when every locked language feature, every effect-row shape, every discharged refinement category, every linearity pattern, every coherence-region scope, and every spec instantiation kind has a passing differential test against the bootstrap. At that point `edda build` defaults to native and the bootstrap has discharged its purpose: with the frontend self-hosted (stages 1–4) and codegen at parity, the native compiler compiles and validates its own subsequent versions — via refinement-discharged certificates, the corpus, and the self-host fixpoint (per [`ARCHITECTURE.md` §Bootstrap as transitional correctness oracle](ARCHITECTURE.md)). The Rust+LLVM bootstrap is **retired**, kept in version control as the historical validation record, not as a live dependency. The native compiler never links LLVM.

The seventh stage is the **daemon, LSP, and MCP rewrite**. The Edda daemon runs on the sync-core + parking_lot + crossbeam concurrency model (carried over from the Rust daemon's architecture, not reinvented). MCP and LSP transports run on Edda implementations. The Rust daemon, LSP, and MCP crates are deleted.

The eighth and final stage is the **CLI and driver rewrite**. The `edda` CLI binary is Edda. With this stage closed, every Rust crate — frontend, resolver, type system, comptime, codegen, daemon, LSP, MCP, CLI — has been replaced by its Edda counterpart and deleted. The bootstrap is fully retired; the self-hosted compiler is the toolchain.

Each stage that produces a deletion (stages 1–4, 7, 8) gates on byte-identical output. The two codegen stages (5, 6) gate on the architectural milestones in [`ARCHITECTURE.md`](ARCHITECTURE.md) and on differential-test coverage against the bootstrap. There is no overlap mode where two implementations of the same component coexist for convenience; the bootstrap-as-oracle is a transition-phase role that ends when stage 6 reaches parity and the bootstrap retires.

## v1.0 Release Criteria

Shipping v1.0 means a small, hard list.

The compiler is self-hosted and running its own test suite — the behavioral corpus and every regression test compiled by Edda, on Edda.

Native codegen is at coverage parity with the bootstrap on the differential test corpus, and `edda build` defaults to the native backend. With parity reached, the Rust+LLVM bootstrap is retired (per [`ARCHITECTURE.md`](ARCHITECTURE.md)); thereafter the self-hosted compiler builds and validates its own subsequent versions. The native pipeline's milestones — HLIR, LIR, e-graph middle-end, boundary verifier, x64 isel + encoder, COFF emission — are all landed and exercised by the corpus.

The stdlib is fully featured at the locked surface. Its packages are stable, with the items the eighth lock indefinitely defers excluded. Stability is contract-hash-anchored — every public item carries its BLAKE3 contract hash, and breaking changes show up in `edda contract-diff`.

The daemon, MCP, and LSP land at v0.1 wire surface. Multi-client daemon support and Live-Share LSP are explicitly v1.x; the v1.0 daemon is single-client, MCP-and-LSP-only.

Distribution works end-to-end. The rune writer and reader handle the shippable `.rune` pack format. The three-tier cache (local, project, team) round-trips compiled artifacts. The certificate verifier consumes the SMT proofs emitted by the compiler and reproduces verdicts deterministically.

Package management ships as a v1.0 surface. The Mímir client side — `edda add`, `edda update`, `edda audit`, `edda publish`, `edda contract-diff`, `edda why` — is implemented in the self-hosted compiler. Manifest pins (`surface_hash`, `max_effects`, `accept_unstable`, `publisher.key_fingerprint`), the `package.lock.toml` schema with its `lockfile_hash` trailer, and the diagnostic classes `capability_escalation` and `lockfile_tampered` are all locked in [language/08-packages.md](language/08-packages.md). The reference Mímir registry implementation is its own repository on the v1.x roadmap; the v1.0 commit is the client surface and the wire format the registry must serve.

Performance baselines hit: ten-second clean build for the corpus, one-second incremental rebuild, five-hundred-millisecond daemon init.

The public debut is in place: `README.md`, `LICENSE`, the first publish invocation that produces the public mirror with the workflow scaffolding stripped. The publish discipline keeps the private workflow machinery and the risk register out of the public tree.

These are not stretch goals. They are the definition of v1.0. Items not on this list are v1.x or indefinite.

## v1.x and Beyond

Reserved past v1.0, with a one-line rationale for each deferral:

Polynomial graded-effect bounds in the NLA sub-fragment — v1.0 ships constant LIA bounds because the in-tree solver's LIA discharge is robust; nonlinear arithmetic needs more soak time on the obligation surface.

Bitvector and floating-point refinement predicates — V1.0 ships `AUFLIA + extensionality + bounded quantifiers`; bitvector theory (for crypto/wire bit-packing) and FP predicates are *decidable* additions that would shrink the `@trust` surface, deferred for the verification-engineering and counterexample-in-source-form discipline cost (a discharge timeout must count as *fail*, never silent-pass). Unbounded quantifiers and integer nonlinear arithmetic are *undecidable* — they are not roadmapped; they stay behind `@trust`/`@unverified`.

Bitvector theory for crypto and parser refinements — decidable in principle (a well-established SMT theory), but the native in-tree solver does not implement a bitvector theory solver yet; we have not validated the obligation-trace + counterexample-in-source-form discipline against bitvector reasoning.

`old(...)` pre-state references in `ensures` — the locked `ensures` form takes only post-state; `old` requires snapshot semantics across the function body and is best added after the post-state surface has soaked.

Loop invariants as a first-class construct, separate from `decreases` — termination is the v1.0 surface; partial-correctness loop invariants are additive and can ship later without breaking the termination story.

AVX-512, SVE, and RISC-V vector intrinsics — v1.0 ships the AVX2 + NEON intrinsic set through the native isel pattern corpus; the wider vector surfaces need a worked example that justifies them and an extension to the refinement-driven autovec licensing rules.

Cross-module HLIR optimization budgets beyond the per-translation-unit default — v1.0's native pipeline does cross-module e-graph rewriting within a workspace member; ThinLTO-shaped cross-package optimization (HLIR rewriting across the Mímir dependency closure) is additive and waits on the V1.0 PGO surface stabilising first.

Multi-client daemon and Live-Share LSP — v0.1 wire surface is single-client; the multi-client coordination layer is non-trivial and adds little for a single author.

HTTP and S3 team-cache backends — the v1.0 cache is local + project + team-shared-filesystem; remote backends are additive.

Notebook LSP integration — the notebook surface is a separate concern from the source LSP and will land when there is demand.

Daemon-to-daemon federation — single-daemon is enough for v1.0; federation matters when fleets of authors share an in-flight specification surface.

Coherence-region transactional rollback (the relaxed `scope(transactional)` variant) — v1.0 ships `scope(coherence)` as the verified-no-rollback form; the transactional relaxation is a separate, more permissive contract that needs its own design pass.

## Indefinite Holds

These are deferred until a worked example justifies them. Without a real consumer pushing for them, adding surface area inflates the model's perplexity over the language for no gain.

Modes on tuple destructuring patterns — current modes apply on declaration; extending into pattern position has no consumer demand.

Float-theory predicates beyond comparison — equality and ordering are sufficient for the current refinement surface.

Decimal floating-point primitives — IEEE 754 binary covers every example in the corpus; decimal is a niche surface.

Multi-stage programming with typed code as values — comptime covers the metaprogramming bar; staged code as a first-class value is a much bigger surface.

Cross-language obligation reuse — Edda emits SMT proofs; consuming proofs emitted by other tools is a research direction, not a v1.0 commitment.

Trust-by-hash for signed packs — the locked audit-list discipline is sufficient for v1.0; signed-pack trust models are additive and need a security review.

---

This roadmap will be revised when validation criteria close, when self-hosting stages complete, and when v1.0 ships. It will not be revised to add or remove language features; the surface is locked.
