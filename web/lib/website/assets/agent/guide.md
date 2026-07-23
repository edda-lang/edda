# Edda authoring — special operations

`AGENTS.md` at the repo root carries the everyday language surface: declarations, modes, effect rows, refinements, specs, derive, the no-comment rule, anti-patterns, code quality. This guide covers the operations beyond that surface — verification tooling, property-based testing, the full comptime table, capability typestate, distribution, daemon/MCP/LSP, and the diagnostics catalogue.

Every feature here carries a status tag, so you never mistake locked design for shipped behaviour:

- **[shipped]** — works in the current toolchain.
- **[partial]** — part works; the rest is specified but pending. The text says which part.
- **[design]** — locked V1.0 design (specified in `codex/language/`), not yet implemented. Do not write code that depends on it.

If you're writing ordinary `.ea` code (signatures, types, control flow, error propagation), `AGENTS.md` is enough.

---

## Verification tooling

### `edda build` — [shipped]

End-to-end compilation of a package or workspace: type-check, refinement discharge, codegen (`.mir` + `.o` under `target/edda/<triple>/`).

```
edda build                          # current package
edda build --target <triple>        # explicit target
```

The target comes from `[build] default_target` in `package.toml` or `--target`. The compiler emits `index.toon` per `.ea` directory as part of the build — these files are byproducts, never edit them by hand.

### `edda check` — [shipped]

Type-check only — parse, resolve, modes, effects, signatures. **`check` does not discharge refinement obligations**; a clean `check` says nothing about your `requires` / `ensures` / `decreases` clauses. Use it as the fast inner-loop gate, and `edda build` as the truth.

### `edda contract-diff` — [partial]

Ships today as a package-level contract delta over the distribution surface (what changed between two package versions, SemVer-relevantly).

The **per-function** contract diff — a canonical BLAKE3 hash per signature over parameter modes, types and refinements, return type, effect-row entries, `requires`/`ensures`/`decreases`, stability, and linearity, with an `added`/`removed`/`changed` delta between any two refs — is locked design (`codex/language/03-verification.md` §8), not yet implemented. When it lands, reviewers see the contract delta before reading the body; until then, compare `index.toon` between refs for the same information at directory granularity.

### `edda lint --trust-points` — [shipped]

Enumerates every `@unverified` and `@trust` annotation in scope as an audit listing (one `Info` diagnostic per trust hatch; exits `0` — it is a listing, not a gate). Trust hatches are never silent.

### Syntax sanity

There is no separate parse-roundtrip verb. The quick syntactic gate is `edda check`; the formatter (`edda fmt`) normalizes layout where available.

---

## Property-based testing — [partial]

The specification (`codex/language/03-verification.md` §6) is locked; the bootstrap toolchain carries the property-synthesis machinery and the `edda test --properties` flag. The native compiler recognizes the `@property` attribute (it is whitelist-valid) but does not yet run the harness.

### `@property` attribute

```edda
@property
function reverse_involution(xs: [i32]) -> bool {
    return reverse(reverse(xs, allocator)?, allocator)? == xs
}
```

`@property` declares the function as a runnable property check. The test harness invokes the property under generators derived from the parameter refinements. Shrinking is deterministic; counterexamples report with full reproduction context.

### `derive properties`

```edda
type Point {
    x: i32
    y: i32
}

derive properties for Point
```

Emits the generator + runner for the type, so it's usable as a parameter in other `@property` functions.

### Refinement-as-property

Every refinement on a function is also a runnable property: `edda test --properties` synthesises generators from refinement structure and runs the `ensures` clauses against generated inputs. Per the locked design, `@unverified` functions get PBT **auto-synthesised** — the trust hatch is never silent.

---

## Comptime — full built-in table

### Shape predicates — [shipped]

All comptime-pure; all admissible in `where` clauses, refinement predicates, and `spec` bodies.

| Signature | Purpose |
|---|---|
| `size_of(T: Type) -> usize` | Size in bytes of `T`'s in-memory representation |
| `align_of(T: Type) -> usize` | Required alignment of `T` |
| `offset_of(T: Type, field: String) -> usize` | Byte offset of named field within `T` |
| `field_count(T: Type) -> usize` | Number of fields on a record type |
| `field_name_at(T: Type, i: usize) -> String` | Name of the i-th field |
| `field_type_at(T: Type, i: usize) -> Type` | Type of the i-th field |

### Type-category predicates — [shipped]

| Signature | Purpose |
|---|---|
| `is_signed(T: Type) -> bool` | True for `i8`..`i128`, `isize` |
| `is_unsigned(T: Type) -> bool` | True for `u8`..`u128`, `usize` |
| `is_integer(T: Type) -> bool` | True for any integer type |
| `is_floating(T: Type) -> bool` | True for `f32`, `f64` |
| `is_numeric(T: Type) -> bool` | `is_integer(T) \|\| is_floating(T)` |
| `is_primitive(T: Type) -> bool` | True for primitive types (table in `AGENTS.md`) |

Target gating: `target.supports(Cap)` — see `AGENTS.md` → Capabilities.

### Contract introspection — [design]

Newer locks (`codex/language/04-specs-comptime.md` §4.4–4.5): `parameters_of`, `effects_of`, `refinements_of`, `contract_hash_of`, `pattern_of`. Specified, not yet implemented — don't build on them.

### `provides` clauses — [shipped]

Declare operator availability or function-shape requirements on comptime arguments:

```edda
spec Sum(comptime T: Type where T provides +, 0) { ... }
spec Eq(comptime T: Type where T provides ==) { ... }
```

The check happens at the **invocation site** — `spec Sum(MyType)` fails if `MyType` does not provide `+` and `0`.

---

## Capability typestate

The mechanism is purely static; operations invalid in the current state are compile errors (`typestate_violation`), no runtime checks.

### `Allocator` — [shipped]

```
open ──alloc.close(take a)──> closed
```

- `open` state: `alloc_array()`, `fork()` (returns a new `open` allocator), and the `Box`/`Vec`/collection constructors that take it.
- `closed`: no operations admit.

### `Network` connection — [design]

```
dialing ──connect()──> connected ──close()──> closing ──quiesce()──> closed
```

The state machine is locked; the `Network` capability's stdlib surface (including the `bind_localhost` / `restrict_to` narrowing) is not yet implemented.

### Narrowing does not change state

Narrowing creates a **new, strictly weaker capability value**; the original is unchanged. Typestate cycles are within a single capability instance. In the current stdlib, `fs.scoped_to(rfs, prefix)` returns a scoped `ReadOnlyFilesystem` and `fs.scoped_to_w(wfs, prefix)` a scoped `Filesystem`; the `SandboxedFilesystem` nominal type is in the locked catalogue but not yet produced by a narrowing method.

---

## Attribute family — full semantics

All **[shipped]** as parse/typecheck surface; `@property`'s runner is [partial] (above).

| Attribute | Form | Purpose |
|---|---|---|
| `@layout(packed)` | item-level on types | Forbids implicit padding between fields |
| `@layout(c)` | item-level on types | C-compatible field order and padding |
| `@align(N)` | item-level on types | Override the type's natural alignment to N bytes |
| `@repr(transparent)` | item-level on types with one field | Type has the same representation as its single field |
| `@abi("name")` | item-level on functions | Declare external ABI binding name (FFI) |
| `@unverified(reason: "...")` | item-level on functions | Skip SMT discharge for the function. `reason` mandatory |
| `@trust(reason: "...")` | site-level inside a body | Skip discharge at a single annotated site. `reason` mandatory |
| `@deprecated(reason: "...", since: "vX.Y")` | item-level | Mark item as deprecated; both fields mandatory |
| `@property` | item-level on functions | Mark as runnable property check (PBT) |
| `@target_requires(Cap)` | item-level on functions | Function exists only on targets supporting `Cap` |

The audit surface for trust hatches is `edda lint --trust-points`.

---

## Diagnostics

### Shape — [shipped]

Every diagnostic prints the same structured body:

```
error[<class>]: <message>
 --> <file>:<line>:<col>
    canonical_form: <canonical form of the failing expression, or <none>>
    obligation_trace: <chain of in-scope predicates assembled to that point, or <none>>
    counterexample: <SMT counterexample rendered in Edda source syntax, or <none>>
    note: <why the rule exists / the likely fix>
```

When the solver reports `sat` on a refinement obligation, the counterexample renders in **Edda source syntax**, not raw SMT-LIB.

### Class names — [shipped], with a compiler split

The native compiler's diagnostic codes (`compiler/lib/diagnostics/src/code.ea`) include, among others:

- `parse_error`, `typecheck_error`, `import_resolution_error`
- `comment_not_admitted`, `unknown_attribute`
- `linear_unconsumed` — a `linear` value reached end-of-scope unconsumed
- `typestate_violation` — operation invalid in the capability's current state
- `heapptr_outside_box` — `HeapPtr` spelled outside its one home in `std/lib/mem/alloc`
- `stability_violation`, `stability_hash_iter` — stable-surface rule breaches
- `capability_not_available_on_target`
- refinement discharge: `refine_failed`, `refine_timeout`, `refine_unknown`, `refine_solver_internal`, `refine_encoding_unsupported`
- lints: `unused_import`, `structure_map_too_dense`, `filename_encodes_hierarchy`, `file_low_cohesion`, `binding_should_be_let`

The bootstrap's diagnostic classes are not 1:1 with the native codes (the bootstrap collapses the `refine_*` family into one class and splits `stability_violation` into finer classes). Byte-identical diagnostics between the two compilers is the **committed goal** backed by a parity corpus, but known divergences remain — quote diagnostics verbatim and name which compiler emitted them when reporting bugs.

---

## Distribution — packages, `.rune`, content addressing

### Package layout — [shipped]

```
<pkg-root>/
  package.toml           # manifest (TOML)
  src/                   # source root — always `src/`
    <name>.ea            # one module per file; each begins `module <root>.<name>`
```

Workspace layout uses `lib/<name>/` per member (see `AGENTS.md` → Layout).

### `package.toml` — [shipped]

The real manifest shape used across this repository:

```toml
[package]
name = "my_package"
version = "0.1.0"
root_namespace = "mypkg"
license = "MIT OR Apache-2.0"

[build]
default_target = "x86-64-windows-msvc"   # or pass --target per invocation

[[dependencies]]
name = "hermod"
version = "0.7.0"
source = "path+../../../runes/lib/hermod"   # or a registry source

[workspace]                # workspace roots only
discover = true            # auto-enumerate lib/<...>/package.toml
# members = ["foo", "bar"] # or an explicit list
```

There is no `kind` key; a package with a `main` entry point links as a binary.

### `.rune` — [design], with shipped fragments

The unit of distribution is the **`.rune`** archive, content-addressed with three hashes — `rune_hash` (the artifact), `surface_hash` (the public API surface), `effect_hash` (the effect-row surface) — pinned in `package.lock.toml` and resolved against the **Mímir** registry. The archive format and trust chain are locked design (`codex/language/08-packages.md`); the lockfile model and hash plumbing exist in the bootstrap today.

Registry verbs (bootstrap CLI): `edda add`, `edda update`, `edda audit`, `edda publish`, `edda why`, plus `edda key` for signing identity. There are **no** `edda package` / `edda install` verbs.

### Build caching — [partial]

Spec instantiations and codegen artifacts are content-addressed (BLAKE3 over the canonical encoding) and cached — `edda build` reports `N artifacts (M cached, K generated)`. The multi-tier cache hierarchy (project / team / global) is locked design, not yet implemented.

---

## Daemon / MCP / LSP — [design], with shipped fragments

The architecture is locked (`codex/language/06-tooling.md`): a long-lived daemon holding the structural model, an MCP wire with eight namespaces (`client.*`, `build.*`, `codegen.*`, `inspect.*`, `edit.*`, `typecheck.*`, `layout.*`, `stream.*`), and an LSP adapter over the same backing.

What exists today, all bootstrap-side: an in-process daemon library (no stdio/socket transport), an MCP dispatch layer where a **subset** of `inspect.*` and `typecheck.*` routes work (e.g. `typecheck.trust_points_in_scope`) and the rest return `method_not_implemented`, and an LSP crate at matching maturity. The native compiler's `daemon` verb is a stub.

Structural edits (`edit.*` — replace a function body, add a refinement, change a parameter mode, each returning a contract-diff) and **contract-grounded synthesis** (candidate bodies generated against a signature + row + refinements, compiling and discharging before they're returned) are locked design with no implementation surface yet. Plan tooling around text edits + `edda check`/`build` for now.

---

## Concurrency, tasks, subprocesses, stability — worked detail

`AGENTS.md` carries the locked rules in terse form; the worked detail lives here.

### Structured concurrency — worked example

```edda
scope(exec) group {
    let fa = group.spawn { read_file_safe(rfs, a) }
    let fb = group.spawn(take allocator = alloc.fork(allocator)) {
        read_file_safe(rfs, allocator, b)
    }
    return match (fa.await, fb.await) {
        case (.ok(let sa), .ok(let sb)) => (sa, sb)
        case (.err(let e), _)           => raise e
        case (_, .err(let e))           => raise e
    }
}
```

`scope(exec) <name>` requires the `Executor` capability. `<name>.spawn { <body> }` opens a child task; spawn args are `take`-mode bindings — `group.spawn(take allocator = alloc.fork(allocator)) { ... }` hands each task its own forked allocator. The scope **cannot exit while children are running** (no fire-and-forget); **no `mutable` crosses a spawn boundary** — pass `take` of a fresh value. Pure concurrency effects (`cancellation`, `divergence`, `nondet`) each have a handler form analogous to `err: T`.

### `std.task` — the deferred-computation carrier

`group.spawn { body }` produces `linear Task(T)` from `std.task`, where `T` is the body's return type. The body's outer effect row may carry capabilities and `cancellation` but **not** `err: T` — cross-task error transport goes through the value shape, not the row. A fallible body returns `Outcome(T, E)`; the await joins observe failure as a value.

`.await` is **compiler-lowered** — it is not a stdlib function. The stdlib surface on `Task(T)`:

```edda
public function detach(t: take Task) -> ()
public function cancel(t: mutable Task) -> ()
public function cancel_and_await(t: take Task) -> () with {cancellation}
```

`Task(T)` is `linear` — losing a handle without `await` / `detach` / `cancel_and_await` is `linear_unconsumed`. `await`'s row is `{cancellation}` only; `?` propagates *only* `err: T`, so cancellation surfaces via `handle cancellation -> ...` or absorption by the enclosing `scope(exec)`.

**Why errors-as-values across the spawn boundary**: `err: T` is the form for synchronous call frames where the row carries the contract. Spawn bodies are deferred computations whose storage shape is the contract — "parallel-task join" is an `Outcome(T, E)` use case. Single-param `Task(T)` matches every other transport spec (`Box(T)`, `Vec(T)`); no row-polymorphism, no `EffectRow` comptime arg in the user-facing surface.

### `Subprocess` and `ChildSpec` — [shipped]

`std.os.process.spawn(p: Subprocess, take bundle: ChildSpec, allocator: Allocator) -> ChildHandle` spawns an external process. The handle's typestate is `running → exited`; consume it via `wait(take h) -> ExitOutcome` / `kill(take h) -> ExitOutcome` / `detach(take h)` — losing it is `linear_unconsumed`. `ExitOutcome` distinguishes `exited` / `signaled` / `wait_failed`; `spawn_captured(p, exe, args, input, allocator)` is the capture-stdio convenience.

**`ChildSpec` — the parent grants the child its capability bundle.** The builder consumes `take` handles from the parent's holdings; a child structurally cannot exercise authority the parent doesn't hold:

```
ChildSpec.of(take exe, take args)
  .with_stdin(take h) .with_stdout(take h) .with_stderr(take h)
  .with_fs(take ro_fs)      # read-only filesystem
  .with_fs_rw(take fs)      # full filesystem
  .with_env(take env) .with_cwd(dir)
  .build()
```

Narrowing `subprocess.allowing(allowlist)` / `subprocess.scoped_to(dir)` is one-way.

**Per-target capability availability** is locked per `(cap, target)` pair in the comptime-queryable availability table, which is **monotonic** (`✗ → ✓` admissible; `✓ → ✗` not). Two gating mechanisms: `@target_requires(T)` (the function does not exist on unsupported targets; declaring a param of that cap type without the attribute fails with `capability_not_available_on_target`) and `comptime if target.supports(T) { ... } else { ... }` (dead branch elided **before** typecheck). `Subprocess` is `✗` on `wasm32-wasi-preview1` (no spawn syscall) and freestanding `bare_metal`.

### Stability — full rules

`stable function` / `stable type` puts the signature on the stable (versioned) surface. A `stable` function may only:
- list `err`, `panic`, `alloc`, `yield`, or `DeterministicRandom` in its row — no `io`, ambient `random`, or `time` (`DeterministicRandom` is admitted because seeded RNG is bit-reproducible, exactly what stability requires);
- call other `stable` functions (or audit-listed escapes: arithmetic, control flow, curated pure stdlib);
- avoid iterating hash collections directly (diagnostic `stability_hash_iter`) — iterate a sorted snapshot of the keys instead (the blessed helpers `iter_sorted_by_key` / `iter_in_insertion_order` are locked names, not yet in the stdlib);
- return values that don't depend on pointer identity;
- use `scope(coherence)` but **not** `scope(exec)`.

`@unverified` on a `stable function` is rejected. Defaults: `public` items default to `unstable`; non-`public` items carry no stability obligation. `stable` / `unstable` are contextual soft-keywords — admitted as identifiers outside declaration position.

### Closure capture syntax — [partial]

`captures {name, other: take}` is mandatory on every closure literal (even empty: `captures {}`); capture modes are `let` (default) and `take` — `mutable` capture is forbidden. Lowering status: zero-capture closures and scalar captures (word-sized primitives, `let` or `take`) execute correctly; record/aggregate captures and heap-backed escaping captures (`String`, records) are not yet reliable end-to-end. Factor anything beyond simple scalar captures into named top-level functions passed by name — the fully wired path.

---

## Examples

`examples/` beside this guide is a **buildable package** — every file compiles with the current toolchain (`cd docs/authoring/examples && edda build`):

- `src/option.ea` — declaring a parameterised `spec`: sum type + functions over its own comptime `T`.
- `src/consume.ea` — instantiating a same-package spec (`spec authoring.option.Option(i64)` — full path, never `local.`) and consuming the instance module.
- `src/config.ea` — capability passing, narrowing (`fs.read_only`, `fs.scoped_to`), `?` propagation of `fs.FsError`, `requires` preconditions, and the `handle ... as e ->` recovery form.
- `src/dispatch.ea` — named functions passed as values to a `function(...) with {row}` parameter; capability threading at the indirect call.
- `src/tree.ea` — recursive types via `Box` indirection, spec-before-type ordering, named-payload construction (`.some(value: x)`), fuel-bounded recursion with `decreases`, saturating arithmetic, and mutual recursion.

When this guide and the examples disagree with observed compiler behaviour, trust the compiler and file the discrepancy; when prose in `codex/language/` disagrees with this guide, `codex` is the design authority and this guide reports implementation status.
