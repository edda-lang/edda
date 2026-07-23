# Edda Language Charter

## Preamble — the thesis

Edda exists to provide the LLM author with all the context the model could possibly need to generate correct code on the first attempt. Every other design decision in this document is downstream of that single commitment.

The thesis is not a forecast about model capability. It is a thesis about *context signal density*. A function's correctness, under any generator, is bounded by what that generator can see at the call site, at the definition site, and in the surrounding module. Hidden ambient authority, inferred effects, generic dispatch resolved elsewhere, lifetimes inferred from use, and contracts that exist only in prose all reduce signal density. They force the generator to guess. Guessing produces plausible-looking code that is wrong in ways the surface does not reveal.

Edda's bet is that verbose, explicit, locally-readable code — with effects, parameter modes, refinements, and capabilities written on every signature — is the highest-signal-density representation of "what this code does and what it requires" that a language can offer. The redundancy that systems programmers traditionally regard as noise is, for a generator, the disambiguating information that makes correct emission possible without round-trips.

This is a bet about the floor of model behavior, not the ceiling. Future models will read denser surfaces faster. But every generator, present and future, performs better when the surface forecloses ambiguity than when it relies on cross-file inference. Edda defends against the worst-case generation, not the best-case one. That is the conservative choice and the one that survives shifts in the underlying technology.

Edda is a dual-audience language. The first audience is the systems programmer who has been waiting for a language with C++'s control, Rust's safety, Zig's transparency, and none of their accidental complexity. The second audience is the LLM author, who needs every signature to declare its full obligations and every type to be inspectable without leaving the file. These two audiences agree on most things — both want explicit memory, predictable performance, no hidden runtime, and locally-decidable semantics.

Where the two audiences diverge, the LLM audience is the *distinguishing constraint*. Other languages serve systems programmers. Few serve generators. Edda's identity, and its reason to exist, comes from refusing to optimize for human ergonomics at the cost of generator legibility. Neither audience is sacrificed — but when in doubt, density of signal wins.

## The 8 Articles

The Articles are the principles from which every concrete decision derives. They are ordered: each succeeding Article reinforces and is enabled by the ones above. Article VIII is the culmination — the tooling story is a *consequence* of Articles I-VII, not a competing principle.

### Article I — Concrete over abstract

**Statement.** Edda has no generics, no traits, no virtual dispatch, no inheritance. The compiler is a code generator.

**Rationale.** Generic dispatch is the largest source of cross-file inference in modern systems languages. When a function's body depends on a trait resolved at a distant call site, the generator cannot determine the function's behavior locally. Specs (Edda's only generic mechanism) resolve at the top of the calling module and emit named, inspectable, content-addressed concrete modules. A spec invocation produces an artifact that lives in the codebase and can be read directly. The generator never reasons about parametric code; it reasons about the concrete code that a spec invocation produced.

**Tooling exploit.** Every type, function, and dispatch is grep-able in its final emitted form — `cargo doc` is replaced by reading the source.

### Article II — Local over global

**Statement.** Every effect appears on the signature; no function performs IO, allocation, mutation of non-local state, or capability use without declaring it.

**Rationale.** Ambient authority is the largest source of hidden contracts. A function that "just logs" or "just allocates" without saying so on its signature forces every caller — human or machine — to read the body to know what the function can do. Edda's effect rows make this impossible: every effect a function may perform is written on its signature, and every capability it requires is named. The generator never has to infer authority from context; the surface tells the truth.

**Tooling exploit.** A diff that changes a function's behavior is forced to change its signature, so contract diffs are computable from signatures alone.

### Article III — Inspectable over clever

**Statement.** One canonical form per construct; the surface matches the runtime 1:1; "if it runs, you can grep for it."

**Rationale.** Multiple ways to express the same thing increases the search space the generator must explore. Macros, operator overloading, custom syntax extensions, and hidden desugarings all break the property that the source is a faithful description of the runtime. Edda fixes one canonical form for each construct. A `while` is a `while`, a function call is a function call, and the generator's mental model never diverges from the compiler's.

**Tooling exploit.** Structural edits (rename, extract, inline) can be performed on the surface AST without semantic-aware fallback paths.

### Article IV — Verified over hoped

**Statement.** SMT refinements are first-class; trust hatches are explicitly listed.

**Rationale.** Generators hallucinate preconditions. They write functions that say "x must be positive" in a doc comment and then call them with negative values from another file. Edda lifts refinements into the type system: `where`, `requires`, `ensures`, and `decreases` are checked by an SMT backend, not by convention. When a refinement cannot be proven, the compiler says so, and the developer either tightens the proof obligation or annotates an `@unverified` or `@trust` escape hatch. Trust becomes audit-listed rather than implicit.

**Tooling exploit.** The compiler can enumerate every unverified path in the project, making code review pipelines auditable.

### Article V — Effects over magic

**Statement.** One typed-effect mechanism handles errors, async, IO, allocation, mutation, mocking, yielding, cancellation, and divergence.

**Rationale.** Mainstream languages have separate mechanisms for each of these: exceptions for errors, async/await for async, callback-passing for mocking, mutex for mutation. Each mechanism has its own syntax, its own failure modes, and its own special-case rules. Edda has one: effect rows on the signature, handlers at the call site. A function `with { err: T, io }` declares its full obligation in one place. Replacing the IO handler at the call site mocks IO. Adding `yield: T` to the row makes it an iterator. The unified mechanism collapses ten special cases into one.

**Tooling exploit.** Test infrastructure (mocking, fault injection, deterministic replay) is just handler substitution at the spec boundary.

### Article VI — Linear over borrowed

**Statement.** Parameter modes (`let` / `mutable` / `take` / `init`) express ownership and aliasing without lifetime annotations.

**Rationale.** Rust's lifetime system is precise but the surface tax — explicit lifetime parameters, variance, higher-ranked bounds — is the largest source of cross-file inference in the language. Generators write code that "looks right" but fails to compile because a lifetime relationship was missed three function calls away. Edda's modes are local. Each parameter declares whether it is borrowed for read (`let`), borrowed for write (`mutable`), consumed (`take`), or initialized (`init`). The call site states the mode explicitly when non-default. There is no notion of "lifetime ?" to propagate.

**Tooling exploit.** Refactors that move ownership boundaries (e.g., turning a borrow into a transfer) are local syntactic transformations, not whole-call-graph rewrites.

### Article VII — Compile-time over run-time

**Statement.** `comptime` is the only metaprogramming. There is no runtime reflection.

**Rationale.** Reflection at runtime is a form of dynamic dispatch the generator cannot reason about locally. A function that calls `type_of(x)` and branches on the result is opaque to the surface. `comptime` moves all such reasoning to compile time, where every introspection produces a concrete artifact. Field iteration, type predicates, derive forms, and conditional compilation all run before the binary exists. The runtime is left with the cheap, predictable, fully-monomorphized code that the comptime stage emitted.

**Tooling exploit.** Derive macros and codegen are inspectable: `comptime` expansions can be queried from the daemon and inserted into the source for human review.

### Article VIII — The compiler is part of the language

**Statement.** Tooling — the daemon, the MCP-native compiler service, the LSP, structural edits, compiler-emitted structmap, diagnostics quality — is a *consequence* of Articles I-VII being true.

**Rationale.** This Article is the culmination of the others, and the *exploit surface* on which Edda's whole proposition rests. Strip any of Articles I-VII and Article VIII becomes impossible. Generics break grep-ability and structmap. Ambient authority breaks contract diff. Macros break structural edits. Reflection breaks comptime introspection. Lifetimes break local refactoring. Untyped effects break handler substitution. Hidden contracts break SMT verification. Each Article is a *precondition* for a tooling capability that Edda must deliver.

The tooling consequences include: a daemon that maintains a structural model of the project incrementally; an MCP server that exposes that model to LLM authors so the model never has to grep blindly; an LSP that delivers hover, goto, and completion driven by the same daemon; structural edits that operate on the surface AST with full type and effect awareness; compiler-emitted `index.toon` structure maps that need no separate parsing pass; contract diff that computes the behavioral delta between two versions of a function from their signatures and effect rows alone; PBT and verification harnesses driven from the same spec system; and diagnostics whose quality is itself a design surface, not an afterthought.

**Tooling exploit.** Article VIII *is* the exploit. The other seven Articles exist so that the daemon, MCP, and structural edits can be built without the accidental complexity that defeats them in other languages.

## The locked design bets

The Articles describe principles. The design bets are the concrete commitments that implement those principles. Each bet borrows from an existing language or research line; the combination is original.

### Koka-style effect handlers (Article V)

Edda's effect rows are inspired by Koka's row polymorphism. Every function declares the union of effects it may perform. Handlers at the call site discharge effects, replacing them with concrete behavior. The mechanism is uniform for all effects — `err: T`, `io`, `alloc`, `yield: T`, `panic`, `cancellation`, `divergence`, `nondet`. Capabilities appear in the row as named idents. See [language/02-modes-effects-refinements.md](language/02-modes-effects-refinements.md).

### Hylo-style modes (Article VI)

Parameter modes — `let`, `mutable`, `take`, `init` — are taken from the Hylo language's mutable-value-semantics model. The compiler tracks ownership and aliasing through modes alone; there are no lifetime annotations. The call site repeats the mode keyword when non-default, eliminating the silent-borrow-vs-move ambiguity that other languages tolerate.

### Zig-style comptime (Article VII)

`comptime` is Edda's only metaprogramming. Expressions, blocks, and parameters can be marked `comptime`, and the compiler evaluates them at compile time. The semantics are Zig's: compile-time and runtime share one language. Edda extends the built-in set with introspection primitives sufficient to implement derive forms, conditional compilation, and constraint-driven specialization in the surface itself.

### Zig-style allocator-passing

There is no global allocator. Every function that allocates takes an `Allocator` capability and declares `alloc` in its effect row. Bounded allocators carry a static byte budget enforced by graded effects. Sandbox testing, deterministic replay, and memory-budget enforcement all derive from this single discipline.

### Reified ABI

Layout, alignment, padding, and representation are part of the surface, not compiler folklore. `@align(N)`, `@layout(...)`, `@repr(c)`, and `@abi(...)` attributes declare how a type is laid out in memory and how it is called across an FFI boundary. The generator can read these directly; the runtime ABI is not implicit.

### MCP-native compiler-as-service (Article VIII)

The daemon exposes its structural model via the Model Context Protocol. An LLM author can query the daemon for type information, effect rows, refinement obligations, callers and callees, spec instantiations, and unverified-path inventories. The compiler is not a batch process; it is a long-lived service that the author — human or machine — interacts with continuously.

### F*/Liquid Haskell/Dafny refinement types (Article IV)

Inline `where` clauses on parameter types, top-level `requires` and `ensures` clauses on functions, and `decreases` clauses for recursive termination are checked by an SMT backend. The lineage is F\*, Liquid Haskell, and Dafny. Unverified clauses become `@unverified(reason: "...")` or `@trust(reason: "...")` annotations that the audit pipeline can enumerate.

### Spec-as-type

A `spec Name(comptime T: Type) where ...` declaration is the only way to express genericity. Specs are content-addressed via BLAKE3, so a spec instantiation in one project produces the same module as the same invocation in another. Spec invocations at the top of a file emit named concrete modules that participate in the structural index like any other module.

### No language-level abstraction (Article I)

Edda has no traits, no type classes, no virtual dispatch, no inheritance. The only mechanism for code reuse is specs. The only mechanism for runtime polymorphism is sum types with pattern matching. Both are inspectable; both produce concrete artifacts.

### Pony-style capability-based effects (Article II)

Capabilities are typed authority. The locked set is `Filesystem`, `ReadOnlyFilesystem`, `SandboxedFilesystem`, `Network`, `LocalhostNetwork`, `RestrictedNetwork`, `Clock`, `MonotonicClock`, `Random`, `DeterministicRandom`, `Allocator`, `BoundedAllocator`, `Executor`, `Stdin`, `Stdout`, `Stderr`, `Subprocess`, `Debugger`. There is no `World` aggregate — `main` enumerates exactly the capabilities it needs. Typestate on capabilities tracks open/closed handles, in-progress/closed connections, and similar lifecycle constraints. Narrowing methods convert a broad capability into a narrower one; synthesis is forbidden — a capability must be received, never invented.

### Structured concurrency

`scope(exec) name { ... }` introduces a structured concurrency region with a mandatory `Executor` capability. All tasks spawned in the region complete before the scope exits. `scope(coherence) name { ... }` introduces an observational atomicity region — mode invariants are re-validated at exit; there is no rollback, but observers outside the region see only validated states. See [language/05-concurrency-coherence.md](language/05-concurrency-coherence.md).

### Graded effects

Graded effects extend the effect row with constant non-negative bounds: `alloc(bytes <= N)`, `io(calls <= N)`, `time(ops <= N)`. The compiler verifies that the body's effect usage stays within the declared bound. This collapses memory-budget enforcement, throughput contracts, and quota systems into the same surface.

### Stability

The `stable function` keyword marks a function as ABI- and behavior-stable for downstream consumers. The compiler enforces a row whitelist (only `err`, `panic`, `alloc`, `yield`, their graded forms, and the `DeterministicRandom` capability are permitted on stable functions), a callee whitelist (a stable function may only call other stable functions or audit-listed escapes), and a hash-iteration ban (no iteration over hash-table contents whose order is not deterministic).

### Coherence regions

`scope(coherence)` is observational atomicity: an external observer sees only the pre-region state or the post-region state, never an intermediate one. Modes are re-validated at the exit point. No rollback machinery; when the region exits through an effect, partial mutations remain and the effect propagates to the surrounding context. The mechanism is designed for state machines and protocol stages where partial progress is meaningless.

### Contract diff

Because every effect, mode, refinement, and capability appears on the signature, the behavioral delta between two versions of a function is computable from signatures alone. The daemon exposes a `contract diff` operation that summarizes what changed: new effects added, refinements weakened, modes promoted, capabilities required. This is a precondition for safe LLM-authored changes — the reviewer sees the contract delta before reading the body.

### Decreases termination (Article IV)

Recursive functions declare a `decreases <expr>` clause. The SMT backend proves the expression decreases on every recursive call, establishing termination. Mutual recursion uses a shared decreases function. This is the same mechanism Dafny uses; Edda adopts it without modification.

### Property-based testing first-class

PBT is not a library; it is a language feature. The `@property` attribute on a function declares it as a property check. The compiler-emitted test harness invokes the property under generators derived from the parameter types. Shrinking is deterministic; counterexamples are reported with full reproduction context.

### Capability-safe stdlib lint

The standard library is checked, at every commit, against the rule that no public function takes ambient authority. Every IO, every allocation, every clock read appears as a capability parameter. The lint is part of the language toolchain, not an external linter.

### Derive forms

Derive forms (`derive eq`, `derive ord`, `derive hash`, `derive debug`, `derive clone`, `derive properties`, `derive serialize`, `derive deserialize`) are `spec` invocations that consume a type and emit the corresponding implementation. The vocabulary is closed; user-defined derives are not admitted. Reading the underlying spec's source reveals the generated code structure exactly.

### Type-state on capabilities

Capabilities carry type-state. An `Allocator` may be in state `open` or `closed`. A `Network` connection may be in `dialing`, `connected`, `closing`, or `closed`. The compiler tracks transitions, refusing operations that the current state does not permit. The mechanism is purely static; no runtime checks are inserted.

### Linear-flagged types

Types are declared as `linear` (must-consume) or `affine` (may-drop). Linear types cannot be silently discarded; the compiler refuses code that drops a linear value without consuming it. Affine types may be dropped but otherwise behave linearly. Resource handles, transaction handles, and protocol states all benefit.

### Compiler-emitted structmap

The structural map (a per-directory `index.toon`) is emitted by the compiler, not by an external parser. Every signature, every effect row, every refinement is already in the compiler's data structures; emitting structmap is a write operation, not a parse-and-extract pipeline. This means structmap is always perfectly synchronized with the source at the commit that built it.

### Bidirectional synthesis surface

The MCP server exposes both "parse this source" and "given this contract, synthesize the body" operations. The daemon can deliver concrete type information, suggest spec invocations, and accept partial code from an LLM author and complete it under contract constraints. This is the synthesis surface — the interface through which an LLM author actually writes Edda code at scale.

## Hard removals

Edda explicitly does not have, and will not have:

- **`null` / `nil` / `undefined`.** Optional values use sum types. There is no special-case absence.
- **Exceptions.** Errors are values, carried in the `err: T` effect.
- **Implicit conversions.** Every type conversion is explicit (`as T`, `as T checked`, etc.).
- **Operator overloading.** Operators have fixed meanings determined by the type system.
- **Inheritance.** No `extends`, no base classes, no method resolution order.
- **Runtime reflection.** No `type_of(x)` at runtime; all introspection is `comptime`.
- **Headers and preprocessor.** No `#include`, no macro expansion before parsing.
- **Order-dependent declarations at module scope.** Items in a module are resolved by name, not by line order.
- **Name shadowing within a scope.** A binding may not reuse an existing binding's name in the same scope.
- **Generics.** No type parameters on functions or types. Use specs.
- **Traits / type classes / protocols.** No ad-hoc polymorphism. Use sum types or specs.
- **Virtual dispatch.** No `dyn`, no vtables in user code (FFI excepted).
- **Lifetime annotations.** Modes carry the necessary information.
- **Macros.** `comptime` is the only metaprogramming.
- **Implicit global state.** Every effect on every signature; no module-level mutable bindings.

## Preserved from C++/Rust

Edda inherits, without modification, the following properties from its closest predecessors. These are non-negotiable; the language is unrecognizable without them.

- **Total memory control.** Explicit layout, alignment, padding, packing. Stack vs heap is the programmer's choice and visible on the signature via `Allocator` (with `Box(T)` / `[T]` for heap-allocated values). `HeapPtr` is stdlib-internal — user code never spells it.
- **Zero-cost abstractions.** Specs monomorphize. Effect rows are erased. Modes compile to direct memory operations. The runtime cost of a feature is what the source says it is.
- **No required runtime.** Edda programs link against `edda-rt` only for the capabilities they use. A program that uses no allocator does not link the allocator runtime.
- **First-class FFI.** Calling C is a single `@abi(c)` annotation away. Inline assembly is a first-class block. Layout attributes match the C ABI when requested.
- **RAII and deterministic destruction.** Destructors run at scope exit in reverse construction order. Linear types make consumption mandatory.
- **Strong static types with sum types and pattern matching.** Algebraic data types are the primary modeling tool. Exhaustiveness is checked.
- **Cargo-quality tooling.** Package manifest, dependency resolution, content-addressed builds, incremental compilation, structured diagnostics — all match the bar Cargo set.

## The dual-audience constraint

Edda must be loved by both systems programmers and LLM authors. These audiences agree on most things: both want explicit memory, predictable performance, no hidden runtime, locally-decidable semantics, and high-quality diagnostics. The agreements outnumber the disagreements by a wide margin.

Where the audiences diverge, neither is sacrificed. Verbose effect rows feel heavy to a human reading code they wrote yesterday; they feel essential to a generator reading code it has never seen. Mode keywords on call sites feel redundant to a programmer who knows the function; they foreclose ambiguity for a generator that does not. Explicit refinements feel like ceremony to a programmer who trusts their own preconditions; they make verification possible for everyone.

The resolution is not compromise — it is to recognize that the human cost of verbosity is bounded (it adds keystrokes; it does not add cognitive load once read), while the generator cost of *insufficient* verbosity is unbounded (the model emits wrong code that compiles). Edda accepts a fixed surface cost in exchange for an unbounded reduction in generation defects.

The LLM audience is the *distinguishing constraint*. A language that serves only systems programmers exists already; Edda would not be necessary. The reason to build Edda is that the LLM audience needs something no existing language provides. Article VIII — the compiler-as-service, the MCP-native daemon, the structural model — is what makes the language genuinely useful at the scale generation enables.

## What this charter does not cover

This document fixes the principles and the locked bets. The concrete language surface, the standard library shape, the toolchain interfaces, and the formal semantics are elaborated in the rest of the corpus:

- [language/01-syntax.md](language/01-syntax.md) — bindings, primitive types, control flow, syntax surface.
- [language/02-modes-effects-refinements.md](language/02-modes-effects-refinements.md) — parameter modes, effect rows, refinement clauses.
- [language/03-verification.md](language/03-verification.md) — SMT backend, refinements, decreases, trust annotations.
- [language/04-specs-comptime.md](language/04-specs-comptime.md) — `comptime`, specs, derive forms.
- [language/05-concurrency-coherence.md](language/05-concurrency-coherence.md) — structured concurrency, coherence regions.
- [language/06-tooling.md](language/06-tooling.md) — daemon, MCP server, LSP, structmap emission, contract diff.
- [language/07-distribution.md](language/07-distribution.md) — rune pack format (`.rune`), content addressing, three-tier cache.
- [language/08-packages.md](language/08-packages.md) — Mímir package management, manifest pins, lockfile, supply-chain discipline.

The Charter is the lens through which every other document is read. When a downstream document and the Charter disagree, the Charter wins, and the downstream document is the one that gets corrected.
