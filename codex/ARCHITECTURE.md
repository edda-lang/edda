# Edda Compiler Architecture

This document is the V1.0 lock on **how** Edda is compiled — the implementation strategy of the two compiler trees, the boundary between them, the structure of the native codegen pipeline, and the load-bearing rationale for each. It is sibling to the CHARTER (principles) and ROADMAP (status): principles say *what Edda is*, this document says *how it is built*.

## Two compilers, one language

The Edda toolchain ships **two** compilers for the same language during the self-hosting transition. They produce byte-identical artifacts from byte-identical source — that equivalence is the self-hosting gate — but they are built differently and live in different places.

- **`edda-bootstrap`** (a separate repo) — the **bootstrap** compiler. Written in Rust. Lowers Edda MIR to LLVM IR, drives LLVM in-process for native object emission, and hands off to a system linker. Exists to validate the language, to compile the native compiler from `.ea` source, and to serve as the correctness oracle for native codegen via differential testing **during the transition**.
- **`compiler/`** (the native-compiler subtree of this monorepo) — the **native** compiler. Written in Edda itself. Ships its own end-to-end code generator at `compiler/lib/backend/` and produces native object files without depending on LLVM at all. Exists as the V1.0 production toolchain.

The bootstrap is **transitional scaffolding**. It validates the language and compiles the native compiler from `.ea` source until the native compiler can compile itself; once native self-hosts and reaches codegen coverage parity, the bootstrap **retires**. Its validation-vehicle and differential-oracle roles last only for the duration of the transition, not as a permanent fixture. After retirement the self-hosted compiler compiles its own newer versions — a compiler that can build itself once can build itself indefinitely — and the Rust+LLVM bootstrap is kept in version control as the historical validation record, not as a live toolchain dependency. This is the conventional self-hosting endgame (cf. Rust, Go).

## Why the bootstrap uses LLVM

The bootstrap's job is to *validate the language*, not to demonstrate codegen prowess. Every passing program through the bootstrap is empirical evidence that the language design holds — that the resolver disambiguates correctly, that the type checker accepts the locked surface, that the SMT discharge proves what it claims to prove, that the effect-row tracking carries through, that monomorphisation produces stable artifacts. Validation throughput is the metric; codegen is one pass among many.

Writing a custom backend in Rust would consume validation-throughput effort on work that is not on the validation critical path. LLVM is well-understood, has Rust bindings, accepts a textual IR, and emits native object files for every target Edda will care about in V1.0. Lowering to LLVM IR and driving LLVM in-process gets the bootstrap to "produces working executables" weeks faster than writing a Rust-side native backend would.

What the bootstrap *does not* do is exploit Edda's static information beyond what survives LLVM IR translation. Effect rows, discharged refinements, capability nominality, and linearity are encoded as best-effort LLVM function attributes and metadata, but LLVM's optimizer treats most of those as hints rather than proofs. The bootstrap's emitted code is correct but conservative — it pays for safety guarantees that the language has already proved unnecessary. That is acceptable for a validation vehicle. It is not acceptable for V1.0 production.

## Why the native compiler ships its own codegen

The native compiler at `compiler/lib/backend/` is the V1.0 production toolchain. It exists because **four** commitments cannot be discharged through LLVM. The first three are necessary; the fourth is what scopes the codegen ambition above "Cranelift-class."

### First — language-thesis legibility

Edda's identity is "the language whose every property is visible at the surface." A compiler that hands its IR to a black-box optimizer written in another language has an opaque step in its pipeline. The same source, on the same target, with the same compiler version, must produce the same machine code — and that determinism must be inspectable end-to-end. A native backend written in Edda is grep-able all the way to byte emission. Article III ("inspectable over clever") applies to the compiler itself, not only to user code.

### Second — fact survival across the lowering boundary

Five categories of static information are proved at MIR time. They are the **floor** the codegen pipeline must preserve, not the ceiling of what it does with them.

1. **Per-function attributes from effect rows.** An empty effect row proves the function is `pure` — globally CSE-able, hoist-out-of-loop-eligible, deduplicable across modules. LLVM has `readnone`/`nounwind`/`nofree`/`willreturn` but treats them as caller-supplied hints subject to interprocedural confirmation. Edda has already discharged the obligation; the native backend acts on the proof without re-checking.

2. **Per-operation flags from discharged refinements.** When the SMT discharge proves `i < xs.len()` at a slice index site, the bounds branch is not needed — the load is unconditional. When it proves `a + b` cannot overflow, the trap branch is not needed — the add is plain. LLVM has no mechanism to consume "this specific op is proven safe"; the bootstrap emits the safe-form instruction (with the trap branch) and relies on LLVM's range analysis to eliminate the branch as a separate optimisation pass. The native backend emits the cheap instruction directly, with no re-derivation.

3. **Alias classes from capability nominality.** Each nominal capability (`Filesystem`, `Allocator`, `Network`, ...) defines its own alias class. Pointers reachable from one capability provably do not alias pointers reachable from another. LLVM's `noalias` is per-pointer and conservatively assumes aliasing without it; expressing capability-class alias proofs through LLVM's TBAA / scoped-noalias metadata is possible but lossy. The native backend treats capability classes as primitives in its alias analysis.

4. **Drop schedule from linearity.** Every `linear T` and `affine T` value has a single deterministic free point computed at MIR-construction time. The schedule arrives in HLIR and survives into LIR as explicit destructor calls — no escape analysis, no liveness inference, no reference counting. LLVM would re-derive the same information through escape analysis at much higher cost and lower confidence.

5. **Spec mangling done by the frontend.** `Stack_i32.push` arrives at codegen as a fully mangled, content-addressed symbol. There is no monomorphisation work for the backend to do. Both bootstrap and native exploit this, but the native backend is the place where the absence of generic dispatch becomes architecturally visible — there are no template instantiation passes in the codegen pipeline because there is nothing to instantiate.

These five facts ride as side tables on both HLIR and LIR. Lowering between them is a refinement-discharged contract: a lowering pass that drops or invalidates any of the five is rejected by the boundary verifier (see §Verified-at-every-boundary).

### Third — toolchain self-sufficiency

A native compiler that depends on LLVM ties Edda's release cycle to LLVM's release cycle, ties Edda's supported targets to LLVM's supported targets, and ties Edda's bug surface to LLVM's bug surface. None of those couplings serve the language's V1.0 commitments. Owning the codegen end-to-end means a new ISA is a new subdirectory under `lib/backend/`, not a wait on upstream.

### Fourth — the compiler as load-bearing self-application

Edda's bet is that the locked surface is sufficient for arbitrary systems work. The native compiler — the largest, most refinement-heavy, most optimization-sensitive program the project will host — is the empirical answer to "can Edda express its own most demanding workload within the locked surface?" Switching to LLVM for codegen would mean the answer was "no, we hand off the hard part."

This is what scopes codegen above Cranelift-class. A backend whose sole purpose is "lower MIR to machine code with the five facts preserved" can be small. A backend that has to demonstrate Edda's sufficiency for arbitrary systems work has to actually *do* the hard things: a real optimizer, a real instruction selector, a real register allocator, real PGO, real cross-build deduplication. The four commitments together imply the codegen scope; the fourth alone determines its ceiling.

## The codegen pipeline

The native pipeline is two intermediate representations between MIR and machine code, each with a locked invariant set and a refinement-discharged contract on entry and exit.

```
Edda source → HIR → MIR → HLIR → (e-graph) → HLIR → LIR → machine code
                              ↑                          ↑
                              │                          │
                              five facts as side tables on both HLIR and LIR
                              │                          │
                              boundary verifier checks every pass
```

- **HIR** and **MIR** are frontend IRs (resolved AST, then an SSA-form mid-level IR with refinement-discharge points). They are produced by the frontend and consumed by `lib/backend/`. Their lock lives in `language/`.
- **HLIR** (High-Level codegen IR) is arch-independent SSA with block parameters. Its term shape is amenable to e-graph rewriting (every operation has a canonical form, every value has a hash). HLIR is where the middle-end runs: e-graph saturation, equivalence-preserving rewrites, cost-driven extraction.
- **LIR** (Low-level IR) is machine-IR-shaped: still SSA, still arch-independent at the opcode level, but isel-ready. Register classes, calling conventions, and frame layout become explicit at the HLIR → LIR boundary. LIR is what regalloc, instruction selection, and the per-ISA encoders consume.
- **Machine code** is what the per-ISA encoders emit, packaged for the platform object format (COFF in V1.0).

Each lowering boundary is a contract: the lowering pass declares the invariants its input must satisfy and the invariants its output guarantees. The boundary verifier checks both at runtime against the side-table fact set. A pass that breaks an invariant fails the build, not silently degrades the next pass.

## HLIR — the e-graph middle-end

HLIR's design is what admits the e-graph optimizer. Every value is a hash-consed node; every operation has a canonical encoding; every fact (effect row attr, discharged-refinement flag, alias class, drop point, mangled symbol) is keyed on the node hash. Equivalence classes (e-classes) over HLIR nodes are the unit of rewriting.

Optimisation is expressed as a corpus of equivalence-preserving rewrite rules over the e-graph. Each rule:

- Names the pattern it matches (a sub-graph in canonical form).
- Names the replacement (another sub-graph in canonical form).
- Carries a correctness obligation discharged against `lib/refine` — the rule's claim that left and right are equivalent under the surrounding context.
- Declares the side-table facts it requires (e.g., a strength-reduction rule may require an overflow-discharge flag on the multiply node).

The engine saturates the e-graph against the rule corpus, then extracts a minimum-cost program via a cost function that integrates instruction count, register pressure, predicted cache behaviour, and PGO data when available. Saturation is bounded by a configurable time/space budget; the cost function is the tiebreaker when the budget closes.

No production compiler is built this way today. egglog and the equality-saturation literature have demonstrated the technique on research compilers; the design bet here is that egglog's production maturity is far enough along — and the obligation surface small enough — that the technique scales to V1.0 production. The project's risk register records this as a load-bearing frontier-research integration.

## Verified-at-every-boundary

Two layers of mechanical verification run inside the codegen pipeline.

**Inter-pass invariant verification.** Every pass within an IR declares a pair of invariant sets:

- *Pre*-conditions: invariants the pass requires on its input (SSA shape, block-parameter discipline, side-table integrity for the facts it consumes).
- *Post*-conditions: invariants the pass guarantees on its output (the same shape lock, plus any new facts the pass adds).

The pass manager runs an invariant checker between every pair of passes. A pass whose post-conditions don't match the next pass's pre-conditions is a hard error, not a runtime ICE later. The checker is small, written against the IR's declarative shape, and serves as the structural-correctness floor for every native pass.

**Refinement-discharged rewrite correctness.** Every e-graph rewrite rule's equivalence claim is a refinement obligation discharged at compile time via the same `lib/refine` machinery that discharges user-program refinements. A rule that drops to disk without a discharged certificate cannot run. The certificate cache (`.edda/cache/certificates/`) records each rule's discharge keyed by rule hash + side-table-fact-set hash.

CompCert has demonstrated rewrite-rule correctness at small scale; the design bet here is that the certificate-cache discipline plus refinement discharge scales the same property to an LLVM-comprehensive surface.

## Side-table-driven optimizations

The five facts in §Second above are necessary for codegen correctness — without them, the native backend would have to re-derive what the frontend already proved. With them, several optimizations that LLVM has to perform conservatively become local and free.

### Typestate-aware optimization

Capability typestate (`Allocator: open → closed`, `Network: dialing → connected → closing → closed`) is *temporal* information that survives into HLIR as a side table. Conventional compilers have no equivalent fact source: they can observe pointer flow but not the temporal predicate "this allocator is currently open."

The optimizer hoists allocations into open windows, sinks them out of closed windows, and fuses adjacent open windows into a single arena. Coherence regions (`scope(coherence) { ... }`) emit the minimum fence set computed at refinement-discharge time, not the conservative maximum LLVM would have to assume in the absence of the proof.

### Refinement-driven auto-vectorization

A loop `for i in 0..<n` whose body is pure and whose iterations are independent under the loop's refinement clauses is trivially vectorizable. LLVM's vectorizer proves loop-independence from scratch each compile via scalar evolution, an expensive analysis. In Edda the refinements that prove independence (`where xs.len() >= n`, `requires !aliased(xs, ys)`, etc.) are discharged at the frontend and ride as side-table facts into HLIR.

The vectorizer becomes a consumer of refinements, not a derivation engine. It checks the side-table facts that license vectorization, emits the vector form when present, falls through to the scalar form when absent.

### Spec-mangling-aware cross-build deduplication

Spec instantiations are content-addressed via BLAKE3 over canonical inputs (qualified spec name + canonical args + canonical body bytes + transitive nested invocation hashes). The codegen artifact for `Stack_i32.push` from project A is byte-identical to the same instantiation in project B if the inputs hash the same.

The native codegen dedupes across packages, workspace members, and (with Mímir trust-roots) across the entire registry. A spec instantiation that has been compiled once on a given target need not be compiled again anywhere — the cache hit is a network hit. This is impossible in LLVM-backed pipelines because LLVM's symbol identity does not preserve the spec-instantiation invariants the frontend establishes.

### Per-layer PGO

Profile-guided optimization in the native backend is a continuous loop, not a `-fprofile-use` build mode. Each layer of the codegen pipeline consumes PGO data from the bootstrap corpus, the active workspace, and the cached stdlib:

- Inlining heuristics in the HLIR middle-end weight by observed call frequency.
- Regalloc spill costs weight by observed register-pressure profiles per function class.
- Instruction-selection pattern priorities weight by observed pattern frequency per ISA.
- E-graph cost functions weight by observed runtime-cost per node kind.

The PGO data is itself versioned by spec-mangling hash and per-target, so a stale measurement on an outdated spec instantiation is detected mechanically rather than poisoning the cost function.

## Compiler-as-service from day one

Every phase of the codegen pipeline is exposed as a public library API. The daemon model from `language/06-tooling.md` is first-class: the same `lib/backend/` that `edda build` calls is what the daemon's `build.codegen` MCP operation calls, what the LSP's compile-on-save flow calls, and what synthesis-server consumers call when they need a costed lowering for a candidate program.

Incremental compilation is keyed at every IR layer via BLAKE3 content addressing plus spec mangling. A single function edit recompiles only that function and its refinement-dependent callers; HLIR-level caches, LIR-level caches, and per-ISA encoded-bytes caches all participate. rustc spent a decade bolting incremental compilation on after the fact; designing for it from the first commit is the easier path when the IR layers are already content-addressed for the cache-key reasons above.

## Internal layout — `lib/backend/`

The native codegen is a single workspace member, not multiple. Per-ISA variants live as subdirectories *inside* `lib/backend/src/`, not as sibling workspace crates. This matches Edda's "directory tree IS the namespace" rule and keeps the shared layers (HLIR, e-graph engine, LIR, regalloc, isel framework, object-file emission) physically adjacent to the per-target lowering they serve.

```
lib/backend/
  package.toml                # root_namespace = "backend"
  src/
    lib.ea                    # contract: locks the four commitments, module map, smoke-test plan
    lower.ea                  # MIR → HLIR lowering — first contract surface
    hlir/                     # arch-independent SSA, e-graph term form
      core.ea                 #   node kinds, value types, blocks, block params
      attrs.ea                #   side tables: effect attrs, refinement flags, alias classes, drop schedule, spec symbols
      hash.ea                 #   canonical hashing for e-graph node identity
      invariants.ea           #   the HLIR pre/post invariant set, machine-readable
    egraph/                   # e-graph rewriting engine
      core.ea                 #   e-class union-find, rebuilding, saturation loop
      extract.ea              #   cost-driven minimum-cost extraction
      rules/                  #   the rewrite-rule corpus, organised by category
        arith.ea              #     algebraic identities (strength reduction, constant folding)
        memory.ea             #     load/store equivalences under alias-class proofs
        control.ea            #     branch reordering, jump threading
        refine.ea             #     rewrites licensed by side-table refinement flags
    verify/                   # inter-pass invariant checker + refinement-bridge for rules
      passmgr.ea              #   pre/post checking around every pass
      cert.ea                 #   rewrite-rule certificate cache lookup
    lower_lir.ea              # HLIR → LIR lowering — second contract surface
    lir/                      # ISA-agnostic low-level IR (machine-IR-shaped)
      core.ea                 #   opcode set, value types, basic blocks
      attrs.ea                #   side tables (mirrored from HLIR, narrowed to LIR-relevant facts)
      invariants.ea           #   the LIR pre/post invariant set
    regalloc/                 # ISA-agnostic register allocation (linear scan in V1.0; SSA-based GC frame-aware)
    isel/                     # ISA-agnostic instruction-selection framework
    pgo/                      # PGO data ingestion, per-layer weighting, version-keyed staleness check
    x64/                      # x86-64 specific (V1.0 first and only target)
      isel.ea                 #   pattern rules: LIR op → x64 instruction
      regs.ea                 #   register class definitions
      abi.ea                  #   Microsoft x64 ABI — shadow space, arg regs, alignment
      emit.ea                 #   final byte emission
      encoding/               #   per-instruction-family tables, split to dodge
                              #   `structure_map_too_dense`
    arm64/                    # reserved for V1.1
    object/                   # COFF emission (Windows). ELF/Mach-O are future siblings.
```

The `codegen` namespace itself is reserved at the manifest level for the per-package build-output directory (`<pkg>/codegen/`). The workspace member is therefore named `backend`, the conventional compiler term and the umbrella under which per-target lowering lives.

## First target: x86-64-windows-msvc

V1.0 ships one target. The smoke-test deliverable is `function main() -> i32 { return 42 }` lowered MIR → HLIR → LIR → x86-64 → COFF, linked against `dev-bootstrap-rust_rt.lib`, executing and exiting 42. That single end-to-end path forces every cross-cutting concern — symbol mangling, Microsoft x64 calling convention, stack frame, prologue/epilogue, RET, section emission, linker hand-off — to be solved at the trivial scale before any complexity is added.

The path from "no codegen" to the smoke-test deliverable traverses these milestones in order:

1. **HLIR design lock.** Node kinds, side-table layout, canonical hashing, per-pass invariant set. Documented as a sibling design doc; reviewed before any HLIR code lands.
2. **LIR design lock.** Same shape as the HLIR lock, narrowed to machine-IR-relevant facts. Documents the regalloc and isel framework's input contract.
3. **E-graph kernel.** Union-find, rebuilding, saturation loop with budget control, cost-driven extraction. Empty rule corpus initially — the kernel must run on zero rules and emit identity-extracted HLIR before any rewrite is admitted.
4. **Boundary verifier.** Pre/post invariant checker, refinement-bridge for rule certificates. Wired into the pass manager before the first lowering pass lands.
5. **MIR → HLIR lowering.** First lowering pass. Smallest possible MIR fragment (a single `return 42`) lowered to HLIR with the five facts populated.
6. **HLIR → LIR lowering.** Second lowering pass. The identity-extracted HLIR fragment lowered to LIR with side tables narrowed appropriately.
7. **x64 instruction selection.** LIR opcodes matched to x64 instructions via the isel pattern corpus. Smallest possible corpus initially — `ret` and integer-constant materialization.
8. **x64 encoder.** Per-instruction-family encoding tables, emitted as machine bytes.
9. **COFF emission.** Section layout, symbol table, relocations, hand-off to the system linker via `dev-bootstrap-rust_rt.lib`.
10. **Smoke-test execution.** End-to-end `function main() -> i32 { return 42 }` builds, links, runs, exits 42.

Subsequent growth follows the locked order: arithmetic → control flow → calls → memory → arrays → effect-attribute consumption → discharged-refinement check elision → typestate-aware optimization → e-graph rule corpus growth → refinement-driven autovec → PGO ingestion. ARM64 lands as the V1.1 target, exercising the ISA-agnostic shared layers (HLIR, e-graph, LIR, regalloc, isel framework, object format) for the first time and validating that the abstraction lines are in the right places.

## Bootstrap as transitional correctness oracle

For as long as native codegen lacks coverage parity with the bootstrap, the bootstrap is the **empirical oracle** for every native pass. Both compilers consume the same `mir.MirFile` envelope and produce equivalent `.o` artifacts; the test harness compiles every fixture through both, runs each binary, and asserts identical stdout/stderr/exit-code triples on the corpus.

The corpus is comprehensive: every `.ea` file under `codex/examples/`, every stdlib module's test fixtures, every rune in the `runes/` subtree, and every fixture that lands in the differential-test harness over the project's lifetime. A divergence is by definition a native-codegen bug, because LLVM has had two decades to find every edge case the corpus might exercise.

This empirical oracle composes with the refinement-discharged rewrite-rule certificates from §Verified-at-every-boundary. The pairing is:

- **Empirical validation:** the bootstrap's behavior is the ground truth for "what does this Edda program do?" Native codegen that diverges on the corpus is wrong by definition.
- **Formal validation:** every e-graph rewrite carries a refinement-discharged correctness certificate. A rule whose certificate fails discharge cannot fire, even if the empirical oracle does not happen to cover the case.

When coverage parity is reached — defined as "every locked language feature, every effect-row shape, every discharged refinement category, every linearity pattern, every coherence-region scope, every spec instantiation kind has a passing differential test" — `edda build` defaults to native and the bootstrap has discharged its purpose. With the frontend self-hosted and codegen at parity, the native compiler compiles its own subsequent versions and validates them via refinement-discharged certificates, the corpus/test suite, and the self-host fixpoint (native compiles native → byte-identical across rebuilds). The Rust+LLVM bootstrap is **retired** — kept in version control as the historical validation record, not as a live dependency, and re-runnable only if a future maintainer wants an independent cross-check on a specific fixture.

## Risk posture

Three load-bearing risks are recorded in the project's risk register under the codegen-architecture heading:

- **Frontier-research integration.** The e-graph middle-end depends on egglog's production maturity scaling to V1.0 production. The bet is that the per-rule certificate discipline reduces the surface area enough that the technique works; the risk is that some rewrite categories require obligation shapes outside the locked decidable fragment.
- **Coherence at scale.** A backend with two IRs, an e-graph optimizer, typestate-aware passes, refinement-driven autovec, per-layer PGO, and cross-build deduplication has many interacting subsystems. Edda's surface and the LLM-author discipline reduce the per-pass complexity, but emergent behavior across the full pipeline is a structural risk that the boundary verifier mitigates rather than eliminates.
- **Transitional oracle coupling.** While the bootstrap is the differential oracle (pre-parity), an LLVM bug it hits poisons the oracle for the affected fixture until LLVM is patched or the fixture is removed from the oracle set. This coupling is **bounded** — it ends at parity, when the bootstrap retires. Post-retirement the native codegen has no permanent external oracle to couple against; it self-validates via refinement-discharged certificates, the corpus/test suite, and the self-host fixpoint. The cost of that independence is that the beyond-LLVM codegen carries its own correctness burden after retirement — which is why the verified-at-every-boundary discipline is load-bearing, not optional.

These risks are not solved by the architecture; the architecture is structured so that each is addressable in isolation rather than mixed into the same surface.

## What this document is not

It is not the V1.0 language specification — that lives in `language/01-syntax.md` through `language/08-packages.md`. The language semantics are identical under both backends.

It is not a roadmap — that lives in `ROADMAP.md`. Status, sequencing, and deliverable dates belong there.

It is not the daemon / MCP / LSP surface — that lives in `language/06-tooling.md`. The compiler-as-service is independent of which backend it emits through.

It is the lock on **the two-tree compiler structure**, **the bootstrap-uses-LLVM rationale**, **the four commitments that scope the native codegen**, **the two-IR pipeline with e-graph middle-end**, **the verified-at-every-boundary discipline**, **the five facts that survive every lowering**, and **the bootstrap-as-continuous-oracle pairing**. Subsequent codegen design documents that reference this lock should cite it; deviations from it require revising this document, not local exceptions.
