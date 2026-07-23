# 03 — Verification

> Article IV: Verified. Every refinement that the SMT fragment can discharge is discharged at compile time; anything that can't is either rejected, gated by an explicit `@unverified` / `@trust` annotation with a recorded reason, or made visible in the diagnostic output. Bugs that the SMT fragment can express are caught before runtime — modulo the declared trust annotations.

This is the document that says what makes Article IV's promise true. It covers the SMT discharge fragment, the certificate machinery, the termination check, the property-based testing runner, the stability discipline, the contract-diff machinery, and the diagnostics discipline that surfaces failures actionably.

The eight Articles assigned to Edda are:

- I. Concrete
- II. Local
- III. Inspectable
- **IV. Verified** ← this document's domain
- V. Effects
- VI. Linear
- VII. Comptime
- VIII. Tools (consequence)

The seven sibling documents you will cross-reference:

- [01-syntax.md](01-syntax.md)
- [02-modes-effects-refinements.md](02-modes-effects-refinements.md) — refinement clause syntax, effect rows
- [04-specs-comptime.md](04-specs-comptime.md) — derive forms, comptime introspection
- [05-concurrency-coherence.md](05-concurrency-coherence.md) — `scope(coherence)`, interaction with stability
- [06-tooling.md](06-tooling.md) — MCP query surface, diagnostics format
- [07-distribution.md](07-distribution.md) — certificate format, content addressing
- [08-packages.md](08-packages.md) — Mímir packaging, lockfile integrity, rune-level contract diff

---

## 1. Overview

Article IV makes a single load-bearing promise: **if `edda build` succeeds, the bug doesn't exist — modulo declared trust annotations.** Every other verification feature in Edda exists to make that sentence true.

The promise has seven machinery components.

1. **SMT discharge.** Every `requires`, `ensures`, `where`, and inline refinement compiles to an obligation in a decidable theory fragment. The solver discharges it or the build fails. There is no "warning level"; failure to discharge is a hard error.
2. **Trust hatches.** The two annotations `@unverified` and `@trust` opt out of SMT discharge with a mandatory `reason: "..."`. The `assume` keyword does not exist in the language. Every trust annotation in your project is audit-listed via `edda lint --trust-points`.
3. **Certificates.** Every discharged obligation produces a certificate. V1.0 writes certificates to disk; the verifier reads from the cache and independently re-checks every cached `unsat` claim, so cache poisoning is always detectable. The verifier is the Article IV trust root.
4. **Termination.** `decreases <expr>` on every recursive function and unbounded `loop`. Absence of `decreases` requires admitting `effect divergence` in the function's effect row. The check is discharged via LIA on a well-founded relation.
5. **Property-based testing.** Every refinement is a runnable property. `edda test --properties` synthesizes generators from refinement structure. `@unverified` functions get PBT synthesized automatically, so the trust hatch is never silent.
6. **Stability.** `stable` is a declaration keyword on functions and types. `stable function` asserts equal-input-equal-output across runs and machines (enforced by an effect-row whitelist + callee whitelist + hash-iteration ban); `stable type` freezes a type's structural surface against breaking change. `@unverified` on a stable function is rejected.
7. **Contract diff.** BLAKE3 hash over a canonical encoding of every function's signature; two functions have the same contract iff the hashes match. The per-function structured-replay query in §8 below (and its `inspect.contract_diff` MCP counterpart) is still-roadmapped target design — the CLI verb `edda contract-diff` that ships today performs a coarser rune-level surface/effect SemVer diff, documented at [08-packages.md](08-packages.md) §8.5.

Tying these together is one discipline: **diagnostics**. Every failure across all seven components emits a structured diagnostic with three load-bearing fields: a canonical form of the failing expression, the chain of in-scope predicates that were assembled, and (when SMT reports `sat`) a counterexample rendered in Edda source syntax.

The bootstrap and the native compiler emit byte-identical diagnostics for the same input. This is a V1.0 commitment.

---

## 2. SMT discharge — the V1.0 decidable fragment

The V1.0 fragment is the combination of these decidable theories:

- **EUF** (Equality with Uninterpreted Functions). User-declared types and their constructors are uninterpreted; equality and disequality between values is reasoned by congruence closure.
- **LIA** (Linear Integer Arithmetic). Addition, subtraction, and multiplication-by-constant over `Int`.
- **Bool** (propositional). `and`, `or`, `not`, implication. Discharged via DPLL.
- **Extensional Arrays.** Read/write/select/store axioms over indexed sequences, with extensionality (`a == b iff forall i: a[i] == b[i]`).
- **Bounded quantifiers.** `forall i in 0..<n: P(i)` and `exists i in 0..<n: P(i)` over a range or slice domain. The bound is finite and statically known, so each quantifier expands to a decidable conjunction/disjunction over the array theory. *Unbounded* quantifiers stay outside the fragment.

The combination is decidable; the SMT-LIB term for the V1.0 fragment is `AUFLIA + extensionality + bounded quantifiers`. The in-tree solver decides it directly.

### Why this fragment

Three reasons.

First, **decidability.** Every obligation either succeeds or fails in bounded time. There is no "the solver timed out, please re-run" interaction; obligations that fall outside the fragment are rejected at the canonical-encoding step, with a diagnostic pointing the author at the relevant trust hatch or refactor.

Second, **practical sufficiency.** The Edda authoring corpus showed that >95% of LLM-generated refinements fall inside `AUFLIA + extensionality + bounded quantifiers`. Range bounds, length invariants, key-presence claims, monotonicity proofs, accumulator preservation — all handled.

Third, **conservatism.** The fragment is small enough that obligations cannot accidentally drift into NLA, unbounded quantifiers, bitvectors, or floating-point predicates. The post-V1.0 reserved list (section 11) is the explicit deferral surface.

### The V1.0 solver

The native compiler's `lib/refine` discharges obligations with an **in-tree SMT solver written in Edda** (`compiler/lib/refine/src/solver/`): a CDCL SAT core (`solver/cdcl/` — Tseitin CNF conversion, watched-literal propagation, conflict analysis) driving theory solvers for the V1.0 fragment (linear integer arithmetic, equality with uninterpreted functions, and arrays). There is no external solver process and no `Subprocess` dependency — discharge runs entirely in-process within the compiler. Because the V1.0 fragment is decidable, every obligation terminates in bounded time; an obligation that exhausts the solver's resource bound *inside* the fragment indicates a bug in the canonical encoder or a theory solver, not a real "undecided" verdict — it surfaces as an internal compiler error, distinct from a genuine `refinement_unproven`.

### What obligations look like at the SMT layer

An obligation is a triple `(predicate, context, sort_signature)`:

- **Predicate.** The claim to discharge, in canonical form.
- **Context.** The conjunction of all in-scope predicates (from enclosing `requires`, `where`, pattern-match arms, dominator-conditional facts, etc.).
- **Sort signature.** The declared types of every free symbol in either.

The solver is asked to prove `context implies predicate` by checking `context and not predicate` for unsatisfiability. `unsat` means the obligation discharges; `sat` means a counterexample exists and is rendered into the diagnostic.

### Worked example

```edda
function residue(n: i64) -> i64
  ensures result >= 0
  ensures result < 4
{
    return n % 4
}
```

The two `ensures` clauses produce obligations. Edda's `i64` parameters lift to the SMT-LIB `Int` sort (LIA's unbounded integer type) for predicate discharge, and `%` maps directly to SMT-LIB's `(mod x y)`:

```
predicate:   (result >= 0) and (result < 4)
context:     result == (n mod 4)
sorts:       n: Int, result: Int
```

Each `i64` symbol lifts to the SMT-LIB `Int` sort as shown in `sorts`. The divisor `4` is a constant, so the `mod` term stays inside LIA; modulo or division by a *non-constant* would fall in the post-V1.0 NLA sub-fragment (section 10).

The solver is asked: is `(result == (n mod 4)) and not ((result >= 0) and (result < 4))` unsatisfiable? It is, by the Euclidean modulo semantics of LIA (`0 <= (mod x k) < k` for constant `k > 0`). The certificate captures the unsat core and is keyed by the obligation hash.

A *full-correctness* postcondition for integer division — `ensures result * b == a || result * b + (a % b) == a` over `function divide(a: i64, b: i64) -> i64 requires b != 0 { return a / b }` — multiplies two non-constant terms (`result * b`), which is **nonlinear**. The V1.0 fragment excludes it: the obligation is refused at the canonical-encoding step (section 10), not sent to the solver. Stating such a postcondition at V1.0 requires `@trust(reason: "...")`; the decidable NLA sub-fragment that would discharge it is post-V1.0.

---

## 3. Trust hatches

The V1.0 fragment is decidable, not omniscient. Three classes of claim sit outside it:

- Claims that depend on a theory not yet admitted (NLA, bitvector, floating-point).
- Claims imported from an external proof — "Knuth shows this terminates," "RFC 5246 specifies this byte layout."
- Claims that the author can prove by hand but that the encoder rejects as too complex for V1.0.

For each, Edda provides one of two annotations.

### `@unverified(reason: "...")`

Whole-function. Every obligation produced anywhere in the function body — refinements, termination checks, stability claims — is skipped. The function emits an `Unverified` certificate carrying the `reason` string.

```edda
@unverified(reason: "Extended Euclidean via Knuth TAOCP 2 §4.5.3")
function gcd_extended(a: i64, b: i64) -> GcdResult
  requires a > 0 && b > 0
  ensures result.gcd == gcd(a, b) && result.gcd == result.x * a + result.y * b
{ ... }
```

The body (omitted) returns a record with fields `{gcd: i64, x: i64, y: i64}`.

The function still type-checks. Its refinements still produce property-based tests (see section 6). The certificate it emits is `Unverified`, not `Smt`, and the trust-points audit lists it.

### `@trust(reason: "...")`

Per-site. Skips SMT discharge at the annotated call or expression. The remainder of the function continues to discharge normally.

```edda
function pack_header(version: i64, kind: i64) -> u32
  requires 0 <= version && version < 256
  requires 0 <= kind && kind < 256
{
    @trust(reason: "Bit-shift packing — bitvector theory deferred to post-V1.0")
    return (version << 8) | kind
}
```

The surrounding function still discharges its `requires` and any other obligations normally; only the annotated expression is exempted.

### Audit surface

Every `@unverified` and `@trust` annotation in your project is listed by:

```
edda lint --trust-points
```

Output format is JSON with one entry per trust point: file, line, kind (`unverified` / `trust`), qualified function name, reason string, and the BLAKE3 hash of the surrounding contract. The MCP query `typecheck.trust_points_in_scope` returns the same shape filtered to a scope (file, package, dependency tree).

### Why this exists

The Article IV promise reads: "if it compiles, the bug doesn't exist — **modulo declared trust annotations**." The list of trust annotations is the audit surface for what the language is not verifying. Reviewers can scan the list; CI can fail on unreviewed additions; published crates carry their trust-point lists as part of their content-addressed manifest.

### What is not admitted

The keyword `assume` does not exist in Edda. There is no way to inject an axiom into the SMT context. The only escape hatches are `@unverified` and `@trust`, both of which require a `reason: "..."` argument. Empty reasons are a compile error.

This is deliberate. An `assume` is an axiom; if the axiom is wrong, the verifier silently produces a false certificate. `@unverified` and `@trust` produce certificates that carry their reason and are visibly distinct from `Smt` certificates in the audit listing.

---

## 4. Proof certificates

Every discharged obligation produces a certificate. Five witness variants are admitted in V1.0:

- **`Smt`** — the solver returned `unsat`. The certificate carries the unsat core (the minimal subset of the context that produced the contradiction), wrapped in an `EDDA-Z3-PROOF-v1` byte frame.
- **`Comptime`** — the obligation was discharged at comptime (e.g., a `decreases` over a constant, an `ensures` over comptime-evaluable expressions). Certificate carries the evaluation trace.
- **`Implicit`** — built-in obligations (signed-overflow check, array-bounds check, division-by-zero) discharged by the type-system rather than user-authored refinements.
- **`Unverified`** — carries the `reason` from `@unverified`. Produced for every obligation skipped by the annotation.
- **`Trust`** — carries the `reason` from `@trust`. Produced for the single annotated site.

### Certificate byte format

Every certificate is a 2-byte common header followed by a per-witness payload. The certificate carries no leading length prefix or magic — the surrounding proofs-blob index supplies each certificate's length, and the witness kind is read from the header.

```
common header (2 bytes):
  certificate_format_version  u8   0x01    bumps on per-certificate layout changes
  certificate_type            u8   0x00=Smt 0x01=Comptime 0x02=Implicit 0x03=Unverified 0x04=Trust

payload (selected by certificate_type; varints are unsigned LEB128):
  Smt:        solver_id u8 (0x00=Z3; 0x01/0x02 reserved for CVC5/Yices) | solver_version (varint-len + UTF-8) | witness (varint-len + bytes)
              — the witness is an EDDA-Z3-PROOF-v1 frame: refutation-proof S-expression + unsat-core S-expressions
  Comptime:   witness_value_kind u8 | witness_value (varint-len + bytes)
  Implicit:   (empty — the 2-byte header is the entire certificate)
  Unverified: reason (varint-len + UTF-8) | function_site (file_id, lo, hi — three little-endian u32)
  Trust:      reason (varint-len + UTF-8) | obligation_site (file_id, lo, hi — three little-endian u32)
```

`certificate_format_version` is independent of the surrounding proofs-blob's `blob_version`: the blob version covers the blob layout (string table, index, certificate sequence); the certificate's own version covers this per-certificate payload format. The `EDDA-Z3-PROOF-v1` frame is the 17-byte ASCII tag `EDDA-Z3-PROOF-v1\n` followed by the refutation proof and unsat-core S-expressions.

A certificate's cache identity is the `(obligation_hash, context_hash)` pair below — two obligations with byte-identical canonical predicate and context resolve to the same cached certificate. The hashes are the cache key; they are not embedded in the certificate bytes.

### Cache keys

Certificates are stored under two BLAKE3-derived keys:

- `obligation_hash` — over the canonical predicate. Identifies the claim.
- `context_hash` — over the sorted context. Identifies the proof environment.

A discharge cache lookup is `(obligation_hash, context_hash) → certificate`. V1.0 writes every certificate to the cache (`.edda/cache/certificates/`); the verifier reads from it.

### The verifier — Article IV trust root

The verifier sits between the discharge cache and the build. Its job is to **independently re-check** every cached `unsat` claim:

1. Read certificate from cache.
2. Reconstruct the SMT obligation from the canonical encoder.
3. Run the solver on the reconstructed obligation, ignoring the cached unsat core.
4. Confirm the solver returns `unsat`.

If the solver disagrees, the cache entry is rejected and the build fails. **The verifier is the Article IV trust root.** A reader who trusts the verifier transitively trusts every cached certificate. A reader who doesn't can run the verifier themselves; the cache is just a hint.

### Worked certificate

For the `residue` example from section 2, the SMT certificate is:

```
common header:
  certificate_format_version:  0x01
  certificate_type:            0x00  (Smt)

payload:
  solver_id:        0x00  (Z3)
  solver_version:   "4.12.2"
  witness:          EDDA-Z3-PROOF-v1 frame
                      proof: <refutation-proof S-expression>
                      core:
                        - result == n % 4

cache key (not part of the certificate bytes):
  obligation_hash:  blake3(canonical_predicate)  = 7e3a...c4f1
  context_hash:     blake3(canonical_context)    = 9b21...0d6e
```

The certificate lives in the package's proofs blob and is keyed in the discharge cache by `(obligation_hash, context_hash)` (`.edda/cache/certificates/`). On a subsequent build the canonical encoder reproduces the same key, the cache lookup hits, and the solver is not invoked; the verifier re-runs the solver against the cached certificate to confirm.

---

## 5. Termination — `decreases <expr>`

Every recursive function and every unbounded `loop` either has `decreases <expr>` or admits `effect divergence` in its row. There is no third option.

### The check

For a recursive call within a function `f`, the obligation is:

```
predicate:   decreases_expr[call_site_args] < decreases_expr[caller_args]
context:     all in-scope predicates at the call site
              + decreases_expr[caller_args] >= 0
```

The `<` is interpreted in a well-founded relation. For `Int`, this is the standard `<` with a `0` floor (the second context conjunct enforces it). For tuples, lex-product over component well-founded relations. For user types, the measure must reduce to an `Int` or a tuple of `Int`s — e.g. a structural size projection — discharged by the same LIA / lex-product rule; a first-class user-defined well-founded relation is post-V1.0.

The obligation discharges via LIA for `Int` expressions; comptime evaluation for compile-time-known relations.

### Factorial

```edda
function factorial(n: i64) -> i64
  requires n >= 0
  decreases n
{
    if n == 0 { return 1 }
    return n * factorial(n - 1)
}
```

The recursive call generates the obligation:

```
predicate:   (n - 1) < n
context:     n >= 0, n != 0, n - 1 >= 0
```

Discharged unconditionally in LIA.

### Bounded loop

```edda
function sum(xs: [i64]) -> i64 {
    var total: i64 = 0
    var i: usize = 0
    loop
      decreases xs.len() - i
    {
        if i == xs.len() { break }
        total = total + xs[i]
        i = i + 1
    }
    return total
}
```

The back-edge generates:

```
predicate:   (xs.len() - (i + 1)) < (xs.len() - i)
context:     xs.len() - i >= 0, i != xs.len(), i' == i + 1
```

LIA discharges this.

### Mutual recursion

A group of mutually recursive functions shares one `decreases` tuple, and each call within the group must decrease the lex-product.

```edda
function is_even(n: i64) -> bool
  requires n >= 0
  decreases (n, 0)
{
    if n == 0 { return true }
    return is_odd(n - 1)
}

function is_odd(n: i64) -> bool
  requires n >= 0
  decreases (n, 1)
{
    if n == 0 { return false }
    return is_even(n - 1)
}
```

The call `is_odd(n - 1)` from `is_even` generates:

```
predicate:   (n - 1, 1) <_lex (n, 0)
context:     n > 0
```

LIA on the first component (`n - 1 < n`) discharges; the second-component tie is irrelevant.

### Divergence as positive admission

A function that does not write `decreases` and cannot be proven to terminate by other means must declare:

```edda
function event_loop() -> ()
  with {divergence}
{
    loop {
        let event = await_event()
        dispatch(event)
    }
}
```

`effect divergence` propagates through callers. A caller that wants to inherit `divergence` does so by including it in its own effect row; a caller that does not must add `decreases` to its own recursive call or otherwise restrict the call's reachability.

This elevates the `divergence` reserved kind from a placeholder to a **positive admission**. The function says, explicitly: "I may not terminate, and any caller knows it."

---

## 6. Property-based testing — refinements as runnable properties

Every `requires` and `ensures` is a property. `edda test --properties` synthesizes input generators from the refinement structure and runs each function against random inputs.

### Generator derivation

The synthesis rules match the V1.0 SMT fragment:

| Refinement kind | Generator strategy |
|---|---|
| `requires x >= a && x < b` (LIA interval) | Uniform integer in `[a, b)` |
| `requires x >= a` (half-bounded) | Geometric distribution from `a` |
| `requires xs.len() < N` (array length) | Length sampled in `[0, N)`, elements recursively |
| Bool-typed parameter | Both branches tested |
| Sum-typed parameter (EUF over variants) | Each variant equally weighted |
| `requires p(x)` (uninterpreted predicate) | Fall back to declared inhabitants of `x`'s type; shrink toward minimum |

Generators compose: a parameter `xs: [i64]` with `requires xs.len() < 10 && forall x in xs: x >= 0` produces a length in `[0, 10)` and each element from the `>= 0` half-bounded generator.

### Shrinkage

When a property fails, the runner shrinks toward a minimal counterexample. Integer counterexamples shrink toward `0`; lists toward `[]`; sum types toward the lexicographically-first variant. The shrinking strategy is published in [04-specs-comptime.md](04-specs-comptime.md) so authors can predict failure-mode output.

### `@unverified` and PBT

A function annotated `@unverified` automatically gets PBT tests synthesized for every refinement on its signature. The trust hatch is no longer silent:

```edda
@unverified(reason: "Extended Euclidean via Knuth TAOCP 2 §4.5.3")
function gcd_extended(a: i64, b: i64) -> GcdResult
  requires a > 0 && b > 0
  ensures result.gcd == gcd(a, b)
  ensures result.gcd == result.x * a + result.y * b
{ ... }
```

Running `edda test --properties` generates `(a, b)` pairs satisfying `a > 0 && b > 0`, calls `gcd_extended`, and checks both `ensures` clauses on the result. A counterexample is reported with the same diagnostic format as a normal compile-time failure.

A function with PBT-passing properties is **not** formally verified, but its trust annotation is no longer silent. The audit listing shows `unverified — PBT: 10_000 cases passed`.

### `derive properties`

The form `derive properties for fn_name` materializes the synthesized property test as an explicit, addressable artifact:

```edda
derive properties for gcd_extended
```

This produces a top-level test function `prop_gcd_extended` in the package's test scope, callable individually and listed by `edda test --list`. The explicit form is required when the author wants to extend the synthesized generator (e.g., bias `a` and `b` toward known edge cases).

---

## 7. Stability — `stable function` and `stable type`

```edda
stable function fold_sum(xs: [i64]) -> i64 { ... }
```

`stable` is a declaration keyword (not an attribute — it carries a verifier obligation, so it cannot be a removable `@`-tag; see [01-syntax.md](01-syntax.md) §Stability modifiers and the annotation collapse in [06-tooling.md](06-tooling.md)). It applies to both **function** and **type** declarations.

On a function it asserts: **the function produces equal outputs for equal-by-equality inputs, across runs and across machines.** This is the foundation of Article IV's bit-identical reproducibility claim, the foundation of [05-concurrency-coherence.md](05-concurrency-coherence.md)'s `scope(coherence)`, and the foundation of [07-distribution.md](07-distribution.md)'s content-addressed specs.

Stability is structurally enforced, not refinement-discharged. The three rules below govern `stable function`.

### Rule 1 — Effect-row whitelist

A stable function's effect row may contain entries only from:

```
{err: T, panic, alloc, yield: T}
```

plus graded forms `alloc(bytes <= N)` and `time(ops <= N)`. Disallowed in a stable row:

- `Stdin`, `Stdout`, `Stderr` (observable side channels)
- `Clock`, `MonotonicClock` (time depends on wall clock)
- ambient `Random` (non-determinism by definition)
- `Network` (network state varies)
- `Filesystem` reads (filesystem state varies)
- `nondet` (the reserved kind for explicit non-determinism)
- `cancellation` (cancellation timing varies)

`DeterministicRandom` **is** admissible in a stable row: a seeded generator produces the same sequence across runs and machines, so equal-input-equal-output holds by construction — that reproducibility is the whole point of the `Random.deterministic(seed)` narrowing. Only ambient `Random` is excluded.

Post-V1.0 will admit `ReadOnlyFilesystem` with content-addressed inputs — a read whose contents are statically known by hash — but V1.0 disallows all filesystem effects in stable rows.

### Rule 2 — Callee whitelist

A stable function may call:

- Other stable functions (recursive structural check)
- Arithmetic, mode operations, pattern matching, control flow primitives
- A curated stdlib subset: `std.math.*`, `std.bytes.*`, `std.text.string`, and `std.core.fmt` formatting to `String` only (no stream writes)

Calling a non-stable function from a stable one is a compile error at the call site. The diagnostic class is `stability_callee`.

### Rule 3 — Hash-iteration ban

`HashMap` and `HashSet` cannot be iterated directly in a stable function. Iteration order depends on hash seed, which varies across runs. Authors must use:

- `iter_sorted_by_key()` — iterates in key-comparison order
- `iter_in_insertion_order()` — iterates in insertion order (requires `LinkedHashMap` / `LinkedHashSet`)

Direct `for k in map` in a stable function emits diagnostic class `stability_hash_iter`.

### Specs and stability

Spec bodies may declare `stable`:

```edda
spec Foldable(comptime T: Type) {
    stable function fold<comptime U: Type>(xs: [T], init: U, f: function(U, T) -> U) -> U
}
```

Instantiations inherit the constraint. An attempt to instantiate the spec with a non-stable `fold` is rejected.

### Stability and `scope(coherence)`

A stable function **can** contain `scope(coherence)` blocks. The recursive structural check descends into the region body and verifies that it is itself structurally stable (effect-row whitelist + callee whitelist + hash-iteration ban). This is implemented in V1.0; there is no deferral. See [05-concurrency-coherence.md](05-concurrency-coherence.md) for the region semantics.

A stable function **cannot** contain `scope(exec)`. Spawn-and-await produces observable timing dependencies even when the spawned work is itself stable. Stable parallelism is expressed via stable primitives like `std.parallel.map` — a locked stable primitive not yet in the stdlib — which guarantees bit-identical fold order regardless of executor scheduling.

### Allocator and address independence

The `alloc` effect is admitted in stable rows. The return value of a stable function must be **address-independent**: equality on the return type must not depend on pointer identity. The structural check enforces this by requiring that all return-type constructors are themselves stable-by-construction (no `Box<dyn>` with identity-defined equality, no `Rc` cycles, etc.). Allocator outputs are wrapped at the boundary so that the address itself is not observable through the return value.

### `@unverified` on a stable function is rejected

Stability is itself a verification claim. Admitting `@unverified` on `stable function fold_sum(...)` would let an author claim a property that is then exempt from being checked. The compiler rejects the combination with diagnostic class `stability_unverified`.

The author who wants to express "this function should be stable, but I cannot prove it" must drop the `stable` keyword and record the intended property in the issue tracker.

### `stable type`

```edda
stable type Point {
    x: f64
    y: f64
}
```

The `stable` keyword on a **type** declaration places that type's structural surface — its fields (or variants) and their types, in declaration order — onto the package's stable, versioned surface. It is the type-level analogue of `stable function`: where a stable function's signature and contract are frozen against breaking change, a stable type's shape is. The contract-diff tool refuses to remove or retype a field, remove a variant, or otherwise break the type across versions; such a change requires a major-version bump. A stable type feeds the `surface_hash` (see [08-packages.md](08-packages.md) §4.2), which scopes that hash to stable items only.

A type referenced by a stable function's signature — as a parameter, return, or field-of-return — must itself be `stable`, by the same address-independence and structural-stability reasoning as Rule 1/Rule 2: an unstable type's shape could drift underneath the stable function's frozen contract. The defaults match functions: `public` types default to `unstable`; non-`public` types carry no stability obligation. `since:` metadata is **not** recorded in source (Edda records no decisions in-source) — version-introduced information lives in the changelog and issue tracker. (`@deprecated(reason:, since:)` is unaffected: it is a live, consumer-surfaced attribute, not a stability marker.)

### Worked example — stable function

```edda
stable function checksum(xs: [i64]) -> i64
  ensures result >= 0 || exists x in xs: x < 0
{
    var total: i64 = 0
    for x in xs {
        total = total + x
    }
    return total
}
```

The function passes the structural check: the effect row is `{}` (empty, which is a subset of the whitelist), the only callee is the iteration primitive over `List` (in the whitelist), no hashed container is iterated. The `ensures` clause discharges via LIA with the bounded existential `exists x in xs: x < 0` expanded over the array theory.

### Worked example — stability failure

```edda
stable function bad_random_sum(rng: mutable Random, xs: [i64]) -> i64 {
    let nonce = random.next_u32(mutable rng)
    var total: i64 = 0
    for x in xs {
        total = total + x
    }
    return total + (nonce as i64)
}
```

Diagnostic:

```
error[stability_callee]: stable function calls non-stable function
  --> src/checksum.ea:42:18
   |
42 |     let nonce = random.next_u32(mutable rng)
   |                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^ non-stable callee
   |
  obligation_trace:
    - bad_random_sum is declared `stable`
    - random.next_u32 has effect row { rng, nondet }
    - nondet is not in the stable whitelist { err, panic, alloc, yield }
  canonical_form:
    callee: std.math.random.next_u32
    callee_effect_row: { rng, nondet }
    caller_effect_constraint: stable_whitelist
```

---

## 8. Contract diff — BLAKE3 over canonical signature

**Implementation status:** the per-function query surface below — the `deltas` schema, the `added`/`removed`/`changed` JSON shape, and `inspect.contract_diff` over MCP — is target design with no implementation today (not even an unrouted MCP stub constant). The CLI verb `edda contract-diff <a> <b>` that ships today is the coarser rune-level surface/effect SemVer-impact classifier specified in [08-packages.md](08-packages.md) §8.5 — it takes rune `name@version` specs or `.rune` paths (not git refs) and emits patch/minor/major-classified diagnostics, not the structured JSON below.

Every function declaration has a **contract hash**: BLAKE3 over the canonical encoding of its signature. Two functions have the same contract iff their hashes match. The encoding covers everything a caller can observe:

- Qualified name
- Parameter list — each parameter's name, mode, type, and inline refinements
- Return type
- Effect row, including graded bounds (`alloc(bytes <= N)`, `time(ops <= N)`), sorted alphabetically
- `requires` clauses, in declaration order, one per separate clause
- `ensures` clauses, in declaration order, one per separate clause
- Trust annotations with their `reason` strings
- Attribute set (`stable`, etc.)

The canonical encoder is the same one used for content-addressed distribution in [07-distribution.md](07-distribution.md). Reusing it guarantees that contract identity and artifact identity are computed against the same byte stream.

### Target CLI shape (not implemented)

```
edda contract-diff <ref-a> <ref-b>
```

This per-function shape has never been implemented under any verb name. `<ref-a>` and `<ref-b>` would be git refs, file paths, or package versions; output would be structured JSON over `qualified_name → contract_hash` maps. It does not describe the real `edda contract-diff <a> <b>` verb, which is the rune-level SemVer classifier at [08-packages.md](08-packages.md) §8.5.

```json
{
  "added":   [ { "qualified_name": "...", "contract_hash": "..." } ],
  "removed": [ ... ],
  "changed": [
    {
      "qualified_name": "my_pkg.fold_sum",
      "contract_hash_before": "...",
      "contract_hash_after":  "...",
      "deltas": [
        {
          "kind": "requires_added",
          "clause": "xs.len() < 1_000_000"
        }
      ]
    }
  ]
}
```

### Target MCP query (not implemented)

```
inspect.contract_diff(from, to) → ContractDiff
```

Not in the §2.2 locked catalogue ([06-tooling.md](06-tooling.md)) — no stub constant exists today. Same shape as the target CLI output above; would let editors and CI surface contract changes in PR reviews once built.

### Delta replay

The `deltas` field is produced by replaying the canonical encoder side-by-side on the before and after signatures and reporting the **first divergence** per signature element. Categories of delta:

- `parameter_added` / `parameter_removed`
- `parameter_mode_changed` — `mutable` ↔ non-`mutable`, `take` introduced
- `parameter_type_changed`
- `parameter_refinement_added` / `parameter_refinement_strengthened` / `parameter_refinement_weakened`
- `return_type_changed`
- `effect_added` / `effect_removed`
- `effect_bound_widened` / `effect_bound_tightened` (graded `alloc`, `time`)
- `requires_added` / `requires_strengthened` / `requires_weakened`
- `ensures_added` / `ensures_strengthened` / `ensures_weakened`
- `attribute_gained` / `attribute_lost` — including `stable`
- `trust_annotation_added` / `trust_reason_changed`

"Strengthened" and "weakened" are reported only when the encoder can statically detect direction (e.g., `requires x >= 0` strengthened to `requires x >= 1` is detectable; arbitrary refinement edits are reported as opaque `requires_changed`).

### Worked example

Before:

```edda
function fold_sum(xs: [i64]) -> i64
  requires xs.len() < 1_000_000
{ ... }
```

After:

```edda
stable function fold_sum(xs: [i64]) -> i64
  requires xs.len() < 1_000_000
  ensures result >= 0 || exists x in xs: x < 0
{ ... }
```

Contract diff output:

```json
{
  "changed": [{
    "qualified_name": "my_pkg.fold_sum",
    "contract_hash_before": "a3f2...01b8",
    "contract_hash_after":  "9e44...c702",
    "deltas": [
      { "kind": "attribute_gained", "attribute": "stable" },
      { "kind": "ensures_added",    "clause": "result >= 0 || exists x in xs: x < 0" }
    ]
  }]
}
```

A caller that depended on the old contract still type-checks against the new one (both deltas are additive on the function's side: gaining `stable` is a strictly stronger guarantee, gaining an `ensures` is a strictly stronger postcondition). The diff still surfaces in CI so reviewers see the change.

A removal of `requires xs.len() < 1_000_000` would surface as `requires_weakened` and is a **non-breaking change for callers** (the function accepts strictly more inputs). The contract diff captures it because it is observable through the hash; the human reviewer judges whether to ship it.

---

## 9. Diagnostics discipline

Every diagnostic — across SMT discharge, termination, stability, and contract diff — carries three load-bearing fields.

### The three fields

- **Canonical form.** The fully-elaborated form of the failing expression. Type aliases expanded, operator overloads resolved, comptime branches collapsed, generic parameters substituted. The reader sees what the compiler is actually working with, not the surface syntax.
- **Obligation trace.** The chain of in-scope predicates that were assembled into the discharge context. Predicates are listed in the order they entered the context, with their source location. This shows the author exactly why the obligation is what it is.
- **Counterexample in source form.** When SMT reports `sat`, the solver's model is **rendered into Edda source syntax**, not raw solver output. `xs := (Array Int 3) [0 := 1; 1 := 2; 2 := 3]` becomes `let xs: [i64] = [1, 2, 3]`. Negative integer counterexamples include their sign in idiomatic form (`let x: i64 = -1`, not `let x = (- 1)`).

### MCP protocol shape

A diagnostic is published over MCP with the following structured shape:

```
Diagnostic {
    class:            DiagnosticClass,
    severity:         Error | Warning | Note,
    file:             AbsolutePath,
    range:            SourceRange,
    canonical_form:   String,
    obligation_trace: List<TracePredicate>,
    counterexample:   Optional<EddaSourceFragment>,
    related:          List<RelatedLocation>,
    suggested_fix:    Optional<TextEdit>,
}

TracePredicate {
    predicate:        String,
    source_location:  SourceRange,
    role:             "requires" | "where" | "match_arm" | "if_branch" | ...,
}
```

In `TracePredicate`, `predicate` is the canonical form of the predicate and `source_location` is where it entered scope. The same shape is emitted by the bootstrap (Rust-hosted) and the native compiler (self-hosted). Diagnostic format parity is a V1.0 commitment.

### The `DiagnosticClass` enum

The locked `DiagnosticClass` enum has **46** members spanning parsing, import resolution, typechecking, verification, stability, capability, package management, and the structural/hygiene lints. The complete enumeration and each class's default severity live in [06-tooling.md](06-tooling.md) §Diagnostic classes, including the explicit note on how this locked set relates to the native self-host's separate `code.ea` diagnostic-code catalogue — the two are not required to be 1:1. The verification-relevant classes this chapter discharges against are:

```
refinement_unproven
termination_unproven
divergence_not_admitted
effect_row_mismatch
effect_graded_bound_exceeded
mode_violation
stability_callee
stability_effect
stability_hash_iter
stability_unverified
stable_contract_revision
capability_not_available_on_target
capability_escalation
lockfile_tampered
```

`capability_not_available_on_target` was added alongside the cap-availability table at [02-modes-effects-refinements.md §3.7](02-modes-effects-refinements.md); `capability_escalation` and `lockfile_tampered` were locked alongside the Mímir package-management surface at [08-packages.md §6.3, §7.2, §9](08-packages.md); the `unknown_attribute` and `comment_not_admitted` sterility classes were locked alongside the no-comment rule (D-18). `non_exhaustive_match` brought the enum from 42 to 43 — the bootstrap previously had no exhaustiveness pass and silently accepted non-exhaustive `match` expressions over sum types as a false-negative. `unprovided_runtime_extern` brought the enum from 43 to 44 members — the pre-link gate that turns a cryptic `lld-link: undefined symbol` into an attributable compiler diagnostic. `executor_missing_in_row` brought the enum from 44 to 45 members — the `scope(exec)` mandatory-`Executor`-capability-in-row check. The most recent addition, `duplicate_runtime_extern`, brought the enum from 45 to its current 46 members — the warn-severity link-time mirror of `unprovided_runtime_extern`: it reports a `__edda_*` runtime-extern symbol defined by more than one link input, where the linker would otherwise resolve the clash arbitrarily and a stray duplicate could silently shadow the intended definition (advisory — the link proceeds). New classes are admitted in minor versions; existing classes are not renumbered (the `doc_example_failed` class was retired together with the doc-example-compilation feature it served, removed with the comment system).

Each class is overridable via `package.toml`'s `[lints]` table — a project can promote `stable_contract_revision` to a hard error (default: warning) or demote `divergence_not_admitted` to a warning (default: error). Severity overrides do not affect the diagnostic's payload, only whether the build fails.

### Worked diagnostic

```edda
function head(xs: [i64]) -> i64
  ensures result >= 0
{
    return xs[0]
}
```

Failure:

```
error[refinement_unproven]: ensures clause not satisfied
  --> src/lists.ea:3:15
   |
 1 | function head(xs: [i64]) -> i64
 2 |   ensures result >= 0
   |           ^^^^^^^^^^^^ ensures result >= 0 unproven
 3 |     return xs[0]
   |            ^^^^^ return expression
   |
  canonical_form:
    expression:    xs[0]
    return_type:   i64
    return_value:  xs[0]
  obligation_trace:
    [1] xs.len() > 0          (required by xs[0] bounds check; src/lists.ea:3:12)
    [2] result == xs[0]       (from return statement; src/lists.ea:3:5)
    [3] result >= 0           (ensures clause; src/lists.ea:2:11)
  counterexample:
    let xs: [i64] = [-1]
    note: result == xs[0] == -1, and -1 < 0 violates the ensures clause
  suggested_fix:
    requires forall x in xs: x >= 0
```

Three things are visible to the author:

1. The `canonical_form` says what `xs[0]` actually returns — an `i64`, with no positivity constraint.
2. The `obligation_trace` shows what predicates were in scope. Notably, **nothing constrains `xs`'s elements to be non-negative**.
3. The `counterexample` renders the model in Edda syntax: `let xs: [i64] = [-1]`. The author can copy-paste it to reproduce.

The `suggested_fix` proposes the smallest change that would discharge the obligation. Suggested fixes are heuristic; they are not certified to be correct.

### Bootstrap-side parity

The bootstrap and the native compiler emit byte-identical diagnostic payloads for the same input. This is enforced by:

- A shared canonical-form printer (one implementation, two language hosts via the published spec)
- A shared obligation-trace assembler (same predicate-ordering rules)
- A shared counterexample renderer (same source-syntax conventions)

The diagnostic-parity test suite in the bootstrap repo runs a corpus of failing programs through both compilers and asserts byte equality on the emitted diagnostics. Regressions block the bootstrap milestone.

---

## 10. Reserved for post-V1.0

The following are explicit deferrals. V1.0 rejects them at the canonical-encoding step — an obligation outside the decidable fragment is refused rather than sent to the solver; a post-V1.0 expansion lifts the rejection.

- **Unbounded quantifiers** — `forall x: P(x)` and `exists x: P(x)` over an unbounded domain. V1.0 admits the *bounded* forms (`forall i in 0..<n: P(i)` and the existential dual, expanded over the array theory); only the unbounded form is deferred, because it is undecidable.
- **NLA sub-fragment** — multiplication and division by non-constants. V1.0 admits `2 * x` and `x / 4`; post-V1.0 admits `x * y` and `x / y` over a decidable NLA sub-fragment (Tarski for reals; over `Int`, a quantifier-elimination subset).
- **Bitvector theory** — for crypto/parser refinements. Allows reasoning about packed bit layouts directly rather than through `@trust` annotations.
- **`old(...)` pre-state references in `ensures`** — `ensures self.count == old(self.count) + 1`. Requires the verifier to thread pre-state values through obligation contexts.
- **Loop invariants orthogonal to `decreases`** — `while ... invariant P(i)`. V1.0 requires that loop invariants be expressed as `requires`/`ensures` on a recursive helper. Post-V1.0 admits the inline form.
- **Refinements on capability identity** — beyond type-state. V1.0 reasons about capability rows as effect sets; post-V1.0 admits `requires cap.identity == ...` for fine-grained capability discipline.
- **Floating-point predicates beyond comparison** — V1.0 admits `f32` and `f64` comparison and equality (modulo NaN); post-V1.0 admits arithmetic predicates via a decidable float sub-fragment.
- **Sub-contract relations** — `is_strictly_stronger_than(contract_a, contract_b)` as a first-class operation on contract hashes. Post-V1.0 contract-diff payloads include the strictly-stronger judgment; V1.0 reports `requires_strengthened`/`requires_weakened` heuristically.
- **Inferred contracts for un-instantiated specs** — V1.0 requires that every function in a spec body have an explicit contract; post-V1.0 infers contracts from the spec's intent statements where possible.

Each deferral is matched by a tracked issue and a post-V1.0 milestone. The post-V1.0 reserved list is the public surface for "what the language doesn't yet check," parallel to the trust-points list ("what the language has been told not to check in your code").

---

## Summary

Article IV's promise — **if it compiles, the bug doesn't exist, modulo declared trust annotations** — is true because:

- SMT discharge runs on a small decidable fragment (`AUFLIA + extensionality + bounded quantifiers`) where every obligation succeeds or fails in bounded time.
- `@unverified` and `@trust` are the **only** trust hatches, both audit-listed, both required to carry a reason. `assume` is not in the language.
- Every discharged obligation produces a certificate. The verifier re-checks every cached `unsat` independently. The verifier is the Article IV trust root.
- `decreases <expr>` is mandatory for recursion and unbounded loops, or `effect divergence` admitted as positive admission.
- Refinements are runnable properties; `@unverified` functions get PBT synthesized automatically.
- `stable function` is structurally enforced via effect-row whitelist, callee whitelist, and hash-iteration ban; `stable type` freezes the type's structural surface (feeds `surface_hash`). `@unverified` on stable is rejected.
- Contract diff is BLAKE3 over canonical signature, with structured delta replay surfacing every observable change.
- Every diagnostic carries canonical form, obligation trace, and source-rendered counterexample. Bootstrap and native compiler emit byte-identical diagnostics.

The post-V1.0 reserved list is the deferral surface. The trust-points list is the per-project exemption surface. Together they enumerate exactly what is not being verified. Everything else is.
