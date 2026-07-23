# Specs and comptime

This document covers the two pillars of Edda's metaprogramming story: **specs** (the only generic mechanism) and **comptime** (the only metaprogramming layer). Article I demands that all codegen targets be concrete; Article VII demands that all metaprogramming flow through a single, inspectable evaluator. Specs and comptime are designed together because the design is unified — there is no preprocessor, no template engine, no macro system, no trait resolver. Specs and comptime do all the work.

## 1. Why these together

Edda's generics story is unusual: there is exactly one form of polymorphism, and it is monomorphization through spec invocation. A spec is a parameterised body of code that, when invoked with concrete comptime arguments, produces a concrete module. Every spec invocation is comptime-evaluated. Every comptime expression can call into the language's introspection surface to inspect what the spec is generating. Specs emit modules; modules expose items; items can themselves contain comptime computations.

The two layers compose:

- **Specs need comptime** to evaluate their `where` clauses, to thread comptime parameters into the body, and to interrogate the types they are generating over (`size_of`, `field_count`, etc.).
- **Comptime can emit specs** (reserved for post-V1.0 — see §8) and can introspect already-emitted specs through the structmap.

A single content-addressed identity scheme covers both. A spec invocation has a BLAKE3 hash over its canonical form; a comptime expression evaluated in a stable context is replayable byte-for-byte. The compiler's structmap and the MCP `inspect.*` surface expose the materialised artifacts to the author (see [06-tooling.md](06-tooling.md) and §7 below).

Specs are not traits, not type classes, not concepts, not templates, and not macros. They are parameterised modules whose parameters are evaluated at compile time. That is the entire mental model. Everything that follows is detail on how the surface and the evaluator meet that mental model precisely.

## 2. Spec language

### 2.1 Declaration

A spec declaration looks like a module wrapped in a `spec` keyword and parameterised on comptime values:

```edda
public spec Stack(comptime T: Type) where size_of(T) > 0 {
    public type Stack {
        items: [T]
        len: usize where len <= items.len()
    }

    public function push(s: mutable Stack, item: take T) -> ()
        with {panic}
    {
        ...
    }
}
```

The keyword `spec` is reserved (see locked-keyword list in [01-syntax.md](01-syntax.md)). The form is:

```
[public] spec Name(<comptime-params>) [where <constraints>] { <body> }
```

A spec body admits the full Edda surface (types, functions, nested specs, derive declarations) with these restrictions:

- No top-level I/O. Specs are pure-codegen artifacts; their body is evaluated abstractly to produce a module, and the only side effect is the emission of the artifact file on disk.
- No `import` of capability-effected modules at spec scope. Capability flow happens at runtime in callers, not at spec instantiation.
- No partially-applied spec invocations. Every parameter must be filled in at the invocation site.

### 2.2 Invocation (top-of-file)

Specs are invoked at the top of an Edda file, after `import` statements and before any other declarations:

```edda
spec mypkg.stack.Stack(i32)

function main() -> () with {panic} {
    var s: Stack_i32.Stack = ...
    Stack_i32.push(mutable s, 42)
}
```

An invocation names the spec by its full module path — the package's root namespace onward (`mypkg.stack.Stack`), never a `local.` path. Each invocation produces a generated module bound to the short name `Name_T` (here `Stack_i32`). All items inside the spec body are reached through the module: `Stack_i32.Stack` for the type, `Stack_i32.push` for the function.

Invocations are top-level only. There is no `spec` expression form, no late binding, no virtual dispatch. Every invocation is statically resolved at the file's content-addressed identity boundary.

### 2.3 Mangling and naming

The author-facing short name is `Name_<arg1>_<arg2>_...` where each `<argN>` is the canonical display of the comptime argument (`i32`, `String`, `MyStruct`, etc.). Long argument lists are truncated visually but never collide because every artifact is also disambiguated by its content hash.

The on-disk artifact filename is:

```
<short>__<12-hex-prefix>.ea
```

For example, `Stack_i32__a3f2c19d04bb.ea`. The 12-hex prefix is the leading 48 bits of the BLAKE3 hash described in §2.7. The double-underscore separates the human-legible short name from the cryptographic disambiguator.

Two invocations with the same short name but different content hashes (e.g. via differing spec body bytes after an upgrade) get distinct artifact files. The compiler will refuse to link a build that contains conflicting short names with different hashes — collisions are surfaced as a `spec_short_name_collision` diagnostic and resolved by lifting one of the invocations into a sibling-spec wrapper (see §2.10).

### 2.4 Outbound type parameters per-function

A function inside a spec may add its own comptime parameters that are not part of the spec's outer signature:

```edda
public spec Option(comptime T: Type) {
    public type Option {
        ...
    }

    public function map<comptime U: Type>(
        opt: take Option,
        f: function(T) -> U with {},
    ) -> Option_U.Option
    {
        ...
    }
}
```

The function `map` introduces a fresh comptime parameter `U`. At each call site, the caller must have already invoked `spec std.core.option.Option(U)` so that `Option_U` is in scope — the spec system does not implicitly chain invocations. This is deliberate: every materialised module must appear by name in the file's invocation list so that grep finds it, structmap records it, and the content-addressing pipeline can hash it.

The angle-bracket form `<comptime U: Type>` is the only place Edda uses angle brackets, and it is restricted to function-level comptime parameters inside specs. Outer spec parameters use plain parens.

### 2.5 Provides clauses — operator-availability constraints

A `where` clause on a spec may demand that a type parameter "provides" some operator or method:

```edda
public spec Sum(comptime T: Type where T provides +, 0) {
    public function sum(xs: [T]) -> T with {} { ... }
}
```

`T provides +` is a **structural** constraint, not a trait bound. It asserts that the type `T` has an `add` method (or the `+` operator equivalent) with the canonical signature `function(T, T) -> T`. The compiler verifies the constraint at spec instantiation time by inspecting the named type's actual surface; no trait declaration, no `impl` block, no witness table is involved.

Provides clauses can name multiple operators (`+, 0` above demands both an addition operator and a zero value of type `T`). The full operator vocabulary is fixed by the locked symbol set: `+`, `-`, `*`, `/`, `%`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `&`, `|`, `^`, `<<`, `>>`, and the zero/one/identity name forms (`0`, `1`).

Provides clauses can also demand named methods:

```edda
spec ToString(comptime T: Type where T provides to_string: function(T) -> String with {})
```

At instantiation, the compiler resolves the method on `T`'s surface and emits a call to the resolved function. There is no virtual dispatch; the call is direct.

### 2.6 Spec parameter kinds

Spec parameters are always comptime. Their kinds are:

- **`comptime T: Type`** — a type parameter. The argument at invocation is a type expression.
- **`comptime n: usize`** (or other primitive type) — a comptime primitive value. The argument is a constant expression evaluable at compile time.
- **`comptime f: function(T) -> U with {effects}`** — a function-typed parameter. The argument is a named function, encoded by its qualified name (kind tag `0x05`, §2.9); each distinct function value produces a distinct monomorphization. Use this when you want the callee inlined or when the operation should be specialised heavily. Expensive on artifact count; very cheap at the call site.

Two further kinds are **reserved, not part of the locked surface** (§8.1): a *shape-only* function parameter — monomorphized once per function type-shape, with the value supplied at runtime as a function pointer through the generated module's interface — and a *module* parameter (`comptime A: Module where A provides ...`), a generated spec instantiation passed as a comptime argument for cross-iterator polymorphism. Neither has a canonical-form kind tag, so neither can be content-addressed yet.

### 2.7 Content-addressed specs

Every spec invocation produces a deterministic content hash. The hash inputs, in canonical order, are:

1. The fully qualified name of the spec (e.g. `std.core.option.Option`).
2. The canonical tuple of comptime arguments. Each argument is encoded by its kind tag (see §2.9 below) followed by its canonical bytes.
3. The canonical body bytes of the spec — the source text after lexing, normalising whitespace, and sorting items lexicographically within each visibility tier. (Edda source admits no comments, so there is no comment-stripping step; the earlier "strip comments below the High importance tier" rule retired with the doc-comment surface.)
4. The transitive set of nested spec invocations triggered by the body — each represented by its own content hash, sorted and deduplicated.

The hash function is **BLAKE3** (256-bit output). The leading 48 bits form the 12-hex artifact suffix; the full 256 bits identify the spec in the package's lockfile.

Materialization is **reachability-driven**: only specs reachable from the active command's root set are written to disk. Building a binary materialises only specs the binary uses. Building a library materialises only specs the library re-exports. Building a test target materialises only specs the test reaches. Unreachable specs are not emitted, even if they appear in the source tree.

#### Worked example

Consider `spec std.core.option.Option(i32)` invoked at the top of `main.ea`.

The compiler resolves `std.core.option.Option` to its declaration in the standard library. It collects the canonical argument tuple: a single argument with kind tag `0x01` (Type) and the length-prefixed canonical name bytes for `i32`. It computes the canonical body bytes of the `Option` spec declaration. It enumerates the nested spec invocations the body triggers (none in this case). It feeds these inputs into BLAKE3.

Suppose the resulting hash is `a3f2c19d04bb1e58...`. The artifact name becomes `Option_i32__a3f2c19d04bb.ea`. The compiler writes the generated module to the content-addressed codegen cache — `.edda/cache/codegen/<shard>/Option_i32__a3f2c19d04bb.ea`, sharded by a leading-hex prefix of the hash — and records the binding `Option_i32 → <that file>` in the build's spec table.

The same invocation in a different file in the same build resolves to the same hash and reuses the artifact — content-addressing makes duplicate invocations free.

### 2.8 Sibling-spec pattern for nested generics

When a function needs nested generics (e.g. `Option(Option(T))`), the canonical pattern is a **sibling spec** that wraps the chain of invocations:

```edda
public spec OptionFlatten(comptime T: Type) {
    spec std.core.option.Option(T)
    spec std.core.option.Option(Option_T)

    public function flatten(opt: take Option_Option_T.Option) -> Option_T.Option {
        ...
    }
}
```

The first invocation generates `Option_T`; the second generates `Option_Option_T` (the argument uses the bare-instance shorthand — `Option_T` for `Option_T.Option` — admitted when the spec's main type shares the spec's name). Nested invocations spell the spec's full module path exactly as at file scope.

The sibling spec exists solely to bundle the chain of invocations so the caller writes a single full-path invocation of the wrapper instead of two separate invocations in the right order. Each nested invocation inside `OptionFlatten` produces its own artifact file with its own content hash, exactly as if it had been written at the caller's site. The wrapper is purely for ergonomic grouping.

This pattern scales: a spec that needs a tree of nested instantiations groups them all under one sibling-spec name, and the caller materialises the entire subtree by invoking the wrapper once.

### 2.9 Argument kinds — canonical form wire types

The canonical encoding of a comptime argument uses a kind tag followed by kind-specific bytes:

| Kind tag | Name | Encoding |
|----------|------|----------|
| `0x01` | `Type` | Canonical type bytes (qualified name + nested type args, recursively) |
| `0x02` | `EffectRow` | Sorted, deduplicated effect names, each as length-prefixed UTF-8 |
| `0x03` | `Primitive` | Primitive type discriminant + little-endian value bytes |
| `0x04` | `UserDefined` | Type bytes + canonical record/variant value bytes |
| `0x05` | `Function` | The function's qualified name, length-prefixed like a `Type` — the distinct kind tag keeps a function argument hash-distinct from a same-named type |

EffectRow encoding sorts entries lexicographically (`capability` before `panic` before `yield: T`) and emits the sorted list. Two effect rows with the same set of effects always produce identical bytes, so spec instantiations that differ only in row order hash to the same artifact.

Primitive encoding uses fixed-size little-endian bytes: `i64` is 8 bytes, `usize` is 8 bytes (target-independent at the spec layer, normalised to 64-bit), `String` is length-prefixed UTF-8, `bool` is 1 byte.

The `UserDefined` (0x04) wire encoding — the type's canonical bytes followed by the value's canonical record/variant bytes — is implemented in the bootstrap's spec-argument encoder; monomorphization over struct-typed comptime arguments is still maturing. The native encoder (`compiler/lib/specs/src/encode.ea`) does not yet emit it: a struct-typed comptime value there raises `spec_encoding_failed`. See §8.1, which tracks the compound-value comptime surface.

### 2.10 Short-name collisions and disambiguation

The short name `Name_T` is convenient but not unique across content hashes. If two distinct invocations of `spec std.core.option.Option(i32)` would produce different hashes (e.g. one is built against an older version of the `Option` spec), the compiler emits a `spec_short_name_collision` diagnostic listing the two artifact paths and the differing inputs.

The author resolves the collision by lifting one of the invocations into a sibling spec with a longer name, or by upgrading the older invocation to match the newer spec body. There is no implicit "newest wins" rule — the compiler refuses the build.

This is intentional: an Edda build either has a single coherent set of spec instantiations, or it doesn't link. There is no namespace-versioning system to paper over divergence.

## 3. Comptime evaluator

### 3.1 Five forms

Edda exposes comptime through five syntactic forms:

- **`comptime <expr>`** — forced evaluation. The expression is evaluated at compile time; the result is a comptime value. Example: `comptime size_of(MyStruct)` evaluates to a `usize` constant baked into the surrounding context.
- **`comptime { <stmts> }`** — block. The block executes at compile time. The block's tail expression (if any) is the block's value, also a comptime value. Used for multi-statement comptime computations such as building lookup tables or normalising configuration.
- **`comptime <param>: <type>`** — parameter mode. The parameter is bound at compile time. Used on function signatures, spec signatures, and on type-level positions.
- **`comptime if <pred> { <true-branch> } else { <false-branch> }`** — target-conditional branch. The predicate must be comptime-decidable. Unlike `comptime <expr>`, both branches are *not* checked: the surviving branch is selected at compile time and the dead branch is **elided before typecheck**. This is the form that admits "use cap X if the target supports it, otherwise fall back to Y" — code inside the surviving branch can reference target-restricted capabilities the dead branch could not. See [02-modes-effects-refinements.md §3.7](02-modes-effects-refinements.md) for the cap-availability use case and the diagnostic contract.
- **`comptime for <ident> in <comptime-range> { <body> }`** — monomorphization-time **unrolled** loop (D-22). The range bounds must be comptime-decidable — canonically `0..<field_count(T)`. The loop is **fully unrolled before typecheck**: each iteration is emitted as a distinct concrete block with `<ident>` bound to that iteration's comptime value, so the introspection built-ins (`field_name_at(T, i)`, `field_type_at(T, i)`, `offset_of`) resolve to concrete results per iteration. There is no loop and no iteration variable in the emitted code — like `comptime if`, the structure is resolved at compile time. This is the form a spec body uses to walk a type's fields or variants, for both reading (the `eq` / `hash` / `debug` derives mix each field) and construction (§4.5). **Current implementation status:** only this field/variant-introspection-bounded idiom (a `field_count(U)`-shaped bound over a comptime `Type` parameter, inside a `spec` body) is lowered today — confirmed by both compilers and by `std.serde.core`/`std.testing.properties` building on it. `comptime for` over an arbitrary comptime-decidable bound (e.g. a literal range) is not yet lowered, in a spec body or otherwise, and panics with `comptime evaluation does not yet support for`.

The five forms share the same evaluator, the same purity rules, and the same introspection surface. Mixing them is encouraged when it improves readability.

### 3.2 Comptime values

The comptime evaluator's universe of values includes:

- **Primitive types and values** — `i32`, `u64`, `f32`, `f64`, `bool`, `String`, `usize`, etc., and their inhabitants. Comptime arithmetic on these uses the same operator semantics as runtime arithmetic, including overflow checks (a comptime overflow is a hard compile error).
- **`Type` meta-values** — type expressions are first-class at comptime. `i32` is both a runtime type-context construct and a comptime `Type` value. `MyStruct` is a `Type`. `Option_i32.Option` is a `Type` referring into a generated module.
- **`Module` meta-values** — every generated spec instantiation produces a `Module` value (e.g. `Option_i32` itself). Passing a `Module` value as a comptime argument to a spec's *module* parameter kind is reserved, not part of the locked surface (see §2.6).
- **Effect-row values** — `{capability}`, `{panic, yield: T}`, etc., are first-class effect-row values. The compiler canonicalises rows on construction (sort, dedupe) so that equality on effect-row values is byte equality.

Comptime values are *not* runtime values until they are spliced into a runtime context. A comptime `usize` that's used as an array bound, for example, becomes a constant in the emitted code, not a runtime variable.

### 3.3 Comptime-purity

Functions called in comptime context must be **comptime-pure**: their effect row must be a subset of `{panic, yield: T}`.

The rationale is that comptime evaluation is deterministic and replayable. Capability access (`{capability}`), error returns (`{err: T}`), and non-determinism (`{nondet}`) cannot meaningfully execute at compile time — there is no clock, no filesystem, no random source, no concurrent agent for them to interact with.

`{panic}` is permitted because a comptime panic surfaces as a compile error, which is the right behaviour: if a comptime computation discovers an invariant violation, the build fails. `{yield: T}` is permitted because the compiler runs comptime generators to fixpoint or to a step limit (see [02-modes-effects-refinements.md](02-modes-effects-refinements.md) for the locked rule).

Calling a function with a non-subset effect row in comptime context produces a `comptime_purity_loss` diagnostic that points at the offending call site and names the offending effect entry.

Comptime is implicitly **stable** in the sense of [03-verification.md](03-verification.md): the evaluator is deterministic by construction, so there is no need to annotate comptime computations with stability markers. (Stability matters at the surface boundary between specs and their callers, where contract diffs flow.)

## 4. Comptime built-ins (locked)

The comptime evaluator exposes a fixed surface of built-in functions. They are part of Edda's locked surface and cannot be redefined by user code.

### 4.1 Layout and structure

```edda
size_of(comptime T: Type) -> usize
align_of(comptime T: Type) -> usize
offset_of(comptime T: Type, field: String) -> usize
field_count(comptime T: Type) -> usize
field_name_at(comptime T: Type, comptime i: usize) -> String
field_type_at(comptime T: Type, comptime i: usize) -> Type
```

`size_of` returns the runtime size in bytes of an inhabitant of `T`. For variant types this is the size of the largest variant plus the discriminant. For zero-sized types it returns 0.

`align_of` returns the alignment in bytes. Primitive types use the target's natural alignment; aggregates use the maximum of their fields' alignments (or a declared `align_as` if specified).

`offset_of` returns the byte offset of `field` within `T`. The `field` argument is a `String`, not an identifier token — `offset_of(Point, "x")`. Errors are compile errors if the field does not exist.

`field_count`, `field_name_at`, `field_type_at` provide structural iteration over record types. For variant types they iterate the variants (each "field" is a variant). The order is the declaration order in the type's source.

### 4.2 Type predicates

```edda
is_signed(comptime T: Type) -> bool
is_unsigned(comptime T: Type) -> bool
is_integer(comptime T: Type) -> bool
is_floating(comptime T: Type) -> bool
is_numeric(comptime T: Type) -> bool
is_primitive(comptime T: Type) -> bool
is_sum(comptime T: Type) -> bool
is_copy(comptime T: Type) -> bool
is_container(comptime T: Type) -> bool
```

Each predicate returns `true` if `T` matches the named category. `is_numeric(T)` is `is_integer(T) || is_floating(T)`. `is_primitive(T)` is true for the locked primitive set (`i8`, `i16`, ..., `i128`, `u8`, ..., `u128`, `f32`, `f64`, `bool`, `String`, `usize`, the heap-pointer primitive — see §6). `is_sum(T)` is true for a `type` declared with `case` variants. `is_copy(T)` is true for a non-linear, non-affine type whose values may be duplicated by ordinary binding. `is_container(T)` is true for slice, array, and stdlib collection-spec-instantiated types.

Predicates are pure and return primitive `bool` values, suitable for use in `where` clauses and spec invocations.

### 4.3 Target gating

```edda
target_has(comptime feature: String) -> bool
target.supports(comptime Cap: Type) -> bool
```

`target_has` returns true if the current build target declares the named feature. The feature vocabulary is part of the build system's locked surface — examples are `"x86_64-avx2"`, `"wasm-simd"`, `"target-pointer-width-64"`. The compiler refuses unrecognised feature names at the call site rather than silently returning false, so typos surface immediately.

`target.supports` returns true if the current build target supports the named capability. `Cap` must be one of the 18 locked nominal capability types listed in [02-modes-effects-refinements.md §3.1](02-modes-effects-refinements.md) (`Debugger` is the 18th); passing a non-capability type is a compile error (`comptime_target_supports_non_capability`). The answer is locked per (capability, target) pair in the cap-availability table at [§3.7](02-modes-effects-refinements.md). The table grows monotonically — ✗ → ✓ transitions are admissible (e.g. WASI preview 2 flipping `Subprocess` from ✗ to ✓ on `wasm32-wasi-preview2`), ✓ → ✗ transitions are not.

`target_has` predates the dotted `target.` namespace and remains the more heavily exercised gate in the existing stdlib — e.g. `target_has("windows")` / `target_has("wasm32")`, used throughout `std.os.*` and `std.io.stdio`.

The two functions are the only built-ins whose value varies across builds. Two builds of the same source with different target gates produce different content hashes for any spec invocation that depends on either. This is intentional: target-conditional code is a legitimate source of divergence, and the content-addressing pipeline tracks it explicitly.

The dotted form `target.supports` reads as a namespaced query: it is the first member of an open `target.*` namespace that will grow with subsequent built-ins (e.g. `target.triple()`, `target.bits()`) as targets diversify. `target_has` predates the namespace and is retained as-is.

### 4.4 Introspection extensions (new locks)

```edda
parameters_of(comptime F: function(...) -> ... with {...}) -> [Parameter]
effects_of(comptime F: function(...) -> ... with {...}) -> EffectRow
refinements_of(comptime F: function(...) -> ... with {...}) -> [Predicate]
contract_hash_of(comptime F: function(...) -> ... with {...}) -> String
pattern_of(comptime item) -> Option_String
```

`parameters_of` returns the function's parameters as a list of `Parameter` records, each carrying:

- `name: String` — the parameter's identifier
- `mode: ParamMode` — one of `take`, `mutable`, `init`, or none (immutable borrow)
- `param_type: Type` — the declared type
- `refinements: [Predicate]` — the parameter's `where`-clause predicates

`effects_of` returns the function's effect row as an `EffectRow` value (the same canonical sorted-deduplicated form as comptime effect-row arguments).

`refinements_of` returns the combined `requires` and `ensures` predicates declared on the function, as a list of `Predicate` records. The list is in declaration order; preconditions come first, postconditions next. Each `Predicate` carries the predicate expression and the kind tag (`Requires` or `Ensures`).

`contract_hash_of` returns the 64-hex BLAKE3 contract hash described in [03-verification.md](03-verification.md). The hash inputs are the function's signature, effect row, and full refinement set — it is the canonical identity for the function's verifiable contract.

`pattern_of` returns the qualified name of the spec that the item is an instance of, if any. For items produced by `spec std.core.option.Option(i32)`, `pattern_of(Option_i32.Option)` returns `Some("std.core.option.Option")`. For hand-written items not produced by a spec, it returns `None`. This is the primary hook that tooling uses to walk from a generated item back to its spec.

**Implementation status.** None of the five are implemented in the bootstrap. In the native compiler, `parameters_of`, `effects_of`, and `contract_hash_of` are partially dispatched — `contract_hash_of`'s surface-encoder covers only scalar signatures, so composite-typed parameters and capability / typed-effect (`err:` / `yield:`) row entries are not yet encoded. `refinements_of` and `pattern_of` are not yet implemented anywhere: `refinements_of` needs the code-quotation primitives reserved in §8.1 to carry predicate ASTs as comptime values; `pattern_of` awaits the spec-origin back-pointer on generated items from the monomorphisation pass. Treat all five as specified, not yet implemented — calling an unimplemented one is a comptime-evaluation error today.

### 4.5 Introspection-driven construction (new lock — D-22)

The read built-ins of §4.1 (`field_count`, `field_name_at`, `field_type_at`) let a spec body *inspect* a comptime type `T`. D-22 locks the complementary *write* surface: a spec body can **assemble** an inhabitant of `T` from per-field (record) or per-variant (sum) values. This is what `derive deserialize` (reconstruct `T` from decoded bytes) and `derive properties`'s `generate(rng) -> T` (build a random `T`) require, and it is the construction half of the introspection pair whose read half is §4.1.

Construction is **not** a comptime built-in — it adds nothing to the §4 catalogue. It is a syntax-and-lowering feature: inside a spec body, a construction form whose shape is resolved against `T` at monomorphization lowers to the *same* record/variant construction the language already emits for source-literal construction. The values it consumes are ordinary runtime values, and the result is an ordinary runtime value of `T`. **No comptime value of `T` is produced** — the reserved `UserDefined` (0x04) canonical kind tag (§2.9) and multi-stage code-quotation (§8.1) stay deferred; this lock does not move them.

The two type shapes that §4.1 iterates take the two forms below. Both are admitted **only inside a spec body or `comptime`-driven block** — never as general-purpose surface (see the scope note).

#### Records — `uninit` + field-by-introspected-index (the staged-init typestate)

A record is assembled by the field-by-field initialisation already locked in [02-modes-effects-refinements.md](02-modes-effects-refinements.md) — `uninit aggregate` walking `Uninit → PartialInit → Valid` as each field is assigned. D-22 adds only the ability to name the field by a comptime index rather than a source-literal name:

```edda
public spec deserialize(comptime T: Type) {
    public function deserialize(bytes: [u8]) -> T {
        uninit out: T
        comptime for i in 0..<field_count(T) {
            out.(i) = decode_field(field_type_at(T, i), bytes, offset_of(T, field_name_at(T, i)))
        }
        return out
    }
}
```

`out.(i)` is **comptime-indexed field access**: a generalisation of the tuple `.0` / `.1` projection to a comptime index expression, valid only where `i` is a comptime value. It names field `i` of `T` in declaration order (equivalently `out.<field_name_at(T, i)>`). The assigned value must have type `field_type_at(T, i)`, checked per unrolled iteration. After the unrolled `comptime for` covers `0..<field_count(T)` — which it does structurally, the compiler having emitted exactly one assignment per field — `out` is `Valid` and may be returned. No new typestate, no coverage proof beyond what staged source-literal construction already discharges.

#### Variants — construct by introspected discriminant

A sum type has no fields to stage; exactly one arm is active. For variant `T`, `field_count(T)` is the variant count and `field_name_at(T, d)` / `field_type_at(T, d)` give the `d`-th constructor name and payload type. Construction selects a discriminant — typically from a runtime tag — and supplies that arm's payload, lowering to the variant constructor the language already emits (`T.<name>(payload)`):

```edda
let v: T = T.(d)(decode_field(field_type_at(T, d), bytes, payload_offset))
```

`T.(d)(payload)` is **comptime-indexed variant construction**: it constructs the `d`-th variant of `T` by its introspected constructor; the payload must have type `field_type_at(T, d)`. Because the live discriminant is a runtime value over a comptime-enumerated arm set, the canonical pattern wraps it in a `comptime for d in 0..<field_count(T)` that unrolls to a discriminant ladder (a `match`/`if` chain on the runtime tag, arm `d` constructing variant `d`). Both the unit form `T.(d)` and the payload form `T.(d)(payload)` are **implemented and verified end-to-end**: the pass-2 expansion folds `T.(d)` to the variant path `T.<variant_name_at(T, d)>`, inheriting the receiver's name resolution so the variant-constructor call rule discharges it normally. The one remaining gap for a *fully generic* variant `deserialize` is comptime field-type dispatch (`field_type_at` as a value, to decode each arm's distinct payload type) — tracked separately; the construction surface itself is complete.

#### Scope — why this is not general positional construction

Both forms are admitted **only** inside a spec body or `comptime`-driven block. Hand-written code constructs records name-keyed (`Point { x: .., y: .. }`) precisely so a field-order transposition is a compile error; admitting `out.(i)` generally would erode that. Inside a `comptime for`, position `i` is bound to field `i` by the *same* unrolled iteration that produced the value, so there is no human transposition hazard — the binding is mechanical. The name-keyed discipline of ordinary code is unchanged. Both forms are pure-lowering: they emit the MIR record/variant construction already used by hand-written literals, so no new runtime ABI and no new content-hash inputs are introduced.

## 5. Derive forms (new lock)

Edda provides a closed `derive` form for the common case of generating standard operations over a user-defined type. The syntax is:

```edda
public type Point {
    x: i32
    y: i32
}

derive eq, hash, debug, properties for Point
```

`derive` is a top-level declaration form, parallel to `spec`. It desugars to a sequence of spec invocations:

```edda
spec std.core.compare.eq(Point)
spec std.core.hash.hash(Point)
spec std.core.fmt.debug(Point)
spec std.testing.properties.properties(Point)
```

The derive whitelist is **closed**: only items from a curated subset of the standard library may appear after `derive`. The locked vocabulary is:

- `eq` → `std.core.compare.eq` — structural equality
- `ord` → `std.core.compare.ord` — total ordering (requires `eq`)
- `hash` → `std.core.hash.hash` — content hashing
- `debug` → `std.core.fmt.debug` — debug formatting (see [03-verification.md](03-verification.md) for the locked output format)
- `clone` → `std.core.copy.clone` — structural copying (only for types without linear/affine fields)
- `properties` → `std.testing.properties` — property-based-testing surface (see [03-verification.md](03-verification.md))
- `serialize` → `std.serde.core.serialize` — canonical serialisation
- `deserialize` → `std.serde.core.deserialize` — canonical deserialisation

Items not on this list cannot appear in a `derive` form. User-defined derive vocabulary is not supported — this is a deliberate closure, not an oversight. Custom code-generation is achieved by writing a spec and invoking it directly.

### 5.1 Generated module access

Each derive emits a generated module accessed through the standard spec-mangling rules. For the `Point` example:

```edda
derive eq, hash, debug for Point

let same: bool = eq_Point.eq(a, b)
let h: u64 = hash_Point.hash(p)
let s: String = debug_Point.format(p)
```

The generated module names follow the uniform spec-mangling rule `<spec-leaf>_<arg>` (§2.3) — the spec name leads, the argument follows, exactly as for `Vec_i32` / `Option_String` / `Box_TreeNode`: `eq_Point` (from `spec std.core.compare.eq(Point)`), `hash_Point` (from `spec std.core.hash.hash(Point)`), and `debug_Point` (from `spec std.core.fmt.debug(Point)`). Each derive spec follows a uniform convention: a primary entry point named for the operation (`eq`, `hash`, `format`, etc.) plus any helper items the spec needs. The conventions are part of the locked stdlib surface. The deriving type must be `public` — each derive materialises a sibling module that references the type across the module boundary, so deriving on a module-internal type fails with `error[import_resolution_error]: item ... is not 'public'`.

### 5.2 Multiple derives on one type

A type may have multiple `derive` declarations, and each declaration may list multiple items:

```edda
derive eq, hash for Point
derive debug, clone for Point
```

These are syntactically equivalent; the compiler concatenates them and processes them as one combined list. Duplicate items (`derive eq for Point` twice) are rejected: the second invocation re-materialises the same generated module and surfaces as `error[import_resolution_error]: duplicate top-level declaration eq_Point` (there is no dedicated `derive_duplicate` diagnostic).

### 5.3 Cross-derive dependencies

Some derives depend on others. `derive ord for T` requires `derive eq for T` to have been declared somewhere in the same module — the compiler refuses to instantiate `std.core.compare.ord` if `eq_T` (e.g. `eq_Point`) is not in scope. This dependency is enforced by the derive front end at the point `derive` is processed, ahead of the underlying `ord` spec's own body.

## 6. Recursive types via Box

Edda's record types are by-value. To express recursive structures (trees, lists, graphs), the author allocates indirection explicitly using `std.mem.alloc.Box`:

```edda
spec std.mem.alloc.Box(TreeNode)
spec std.core.option.Option(Box_TreeNode)

type TreeNode {
    value: i32
    left: Option_Box_TreeNode.Option
    right: Option_Box_TreeNode.Option
}
```

`Box(T)` generates a heap-allocated pointer-to-T wrapper. The generated module exposes:

- `Box` — the type itself
- `new(value: take T, allocator: Allocator) -> Box with {allocator, err: alloc.AllocError}` — allocate
- `get(b: Box) -> T` — read access
- `unbox(b: take Box, allocator: mutable Allocator) -> T` — move out and deallocate
- `drop(b: take Box) -> ()` — deallocate without reading the value out

The internal pointer representation uses the opaque `HeapPtr` primitive, a stdlib-internal carrier that backs `Box` and the allocator intrinsics. `Box`'s own struct body is empty — the pointer field is synthesised by the compiler — so the carrier surfaces in source only in a handful of stdlib-internal opaque-handle types (e.g. `std.math.bigint`, `std.os.process`). User code never names `HeapPtr` directly, and this is now **enforced**: the type-path checker raises `heapptr_outside_box` when `HeapPtr` is named in a non-stdlib module (any module whose root namespace is not `std`). Stdlib-internal modules may name it; a user spec that names `HeapPtr` is rejected.

### 6.1 Multi-pass type resolution

The recursive use of `TreeNode` inside its own fields requires the compiler to know `TreeNode`'s identity before it has resolved `TreeNode`'s field types. The compiler handles this with a three-pass algorithm:

1. **Pass 1 — name collection.** All type names in the module are registered, including their parameters but not their field shapes. After pass 1, the compiler knows `TreeNode` is a record type with three fields whose names are `value`, `left`, `right`, but it does not yet know the field types.
2. **Pass 2 — spec materialization.** All `spec` invocations are resolved and the resulting modules are emitted. The spec invocations may name types whose fields are still unknown, but the *type identity* is available, which is all the spec mangling and content-addressing require.
3. **Pass 3 — field type resolution.** Field types are resolved using the now-fully-populated type and module namespace. Cycles in the field-type graph are admitted only if every cycle passes through a `Box`, a slice `[T]`, or another heap-indirecting spec instance (i.e. through a `HeapPtr`); a cycle of pure-by-value record/sum types is a `cyclic_value_type` diagnostic. This is now **enforced**: a by-value self-reference such as `type Node { value: i32  next: Node }` is rejected with `cyclic_value_type`, while recursion through `Box` (the `TreeNode` example below) is admitted. Detection is intra-file — a cycle is reported when it closes through type declarations in the same module via direct record/sum embedding, tuple, or fixed-array nesting; edges through `Box`, `[T]`, or any spec instance break the cycle. (Because the type checker rejects the cycle before MIR lowering can force its layout, the diagnostic replaces what would otherwise be an unbounded layout recursion.)

The multi-pass approach admits **mutual recursion** through `Box` cleanly:

```edda
spec std.mem.alloc.Box(Forest)
spec std.mem.alloc.Box(Tree)

type Tree {
    root: Box_Forest.Box
}

type Forest {
    trees: [Box_Tree.Box]
}
```

Both `Tree` and `Forest` are valid; the cycle passes through `Box` on both sides.

### 6.2 Why Box is a spec

`Box` is a spec rather than a built-in for two reasons:

- It is content-addressed and inspectable like every other spec. The generated `Box_TreeNode` module shows up in the structmap with a content hash and is grep-able as `Box_TreeNode__<hex>.ea` on disk.
- The allocation strategy is parameterizable. Future variants (`std.mem.alloc.Arena(T, A)`, `std.mem.alloc.Pool(T, P)`) follow the same template and integrate with the same multi-pass resolver.

The `HeapPtr` primitive (opaque, no type parameter) is the stdlib-internal carrier that makes this work — it backs `Box` (and the allocator intrinsics), so a recursive type reaches it only through `Box`. User code never spells `HeapPtr`.

## 7. Inspectability and tooling integration

Every artifact described in this document is visible to the author through three mechanisms:

### 7.1 Filesystem grep

Spec invocations produce real files on disk under the content-addressed codegen cache (`.edda/cache/codegen/<shard>/`). The author can `grep -r "Stack_i32" .` and find every call site. They can `ls .edda/cache/codegen/*/Stack_i32*` and see every materialised invocation. There is no hidden code generation; the artifacts are first-class build outputs.

### 7.2 Compiler-emitted structmap

The compiler emits an `index.toon` file in each source directory (see [06-tooling.md](06-tooling.md)), derived directly from the type-checker's own data structures — signatures, effect rows, refinements, stability, and the call graph for every item, spec-generated modules included. Recording per-invocation content hashes, and tracing a generated item back to its originating spec via `pattern_of`, are natural extensions of that same derivation; `pattern_of`'s current unimplemented status (§4.4) is what gates the latter today.

The structmap is the canonical surface for navigating the codebase; agents read it before reading source.

### 7.3 MCP introspection

The Edda MCP server's `inspect.*` namespace (see [06-tooling.md](06-tooling.md)) exposes the structural facts above to a client — the artifact an invocation produced, the source that produced it, and the invocation sites and consumers of a given artifact.

These endpoints are pure (read-only against the build's artifact directory) and replayable. The author or an agent can ask "what did `spec std.core.option.Option(MyError)` actually produce?" and get the answer directly.

## 8. Reserved for post-V1.0 and indefinite

The following surfaces are explicitly out of scope for the current locked surface, in two tiers.

### 8.1 Reserved for post-V1.0

- **Multi-stage programming.** `comptime` functions that return typed code values (in the MetaOCaml sense) are reserved. The current surface allows comptime to compute *values* (including types and modules) but not to construct arbitrary code expressions. Adding this requires extending the comptime evaluator with code-quotation primitives and a static-type-preserving splice operator; the design is open. (The D-22 introspection-driven construction of §4.5 does **not** cross this line: it produces ordinary runtime values of a known type `T` via the record/variant construction the language already emits — it never quotes or returns code, and never produces a comptime value of `T`. The `comptime for` of §3.1 is unrolling, not code-quotation.)
- **Comptime certificate format for compound types.** A canonical serialisation of comptime-evaluated compound values (records, variants, lists) for use as content-address inputs to other specs. The current `UserDefined` kind tag (0x04) reserves the slot; the encoding details are deferred.
- **Cross-spec module argument constraints beyond `provides`.** The current `provides` form is structural and operator-oriented. Richer constraints (e.g. "this module's `next` and `peek` operations must agree on the iterator's position semantics") require a constraint language that does not yet exist.

These three are tracked for post-V1.0 because the design has open shape and the locked surface should not foreclose them. None are required for the bootstrap.

### 8.2 Indefinite

- **`comptime async` / `comptime scope(exec)`.** Concurrent comptime evaluation is out of scope. Comptime is intentionally single-threaded and deterministic; admitting concurrency would either compromise determinism or require an effect-system extension that contradicts the locked rule for comptime-purity.
- **User-defined derive vocabulary.** The closed whitelist (§5) is deliberate. Allowing user-defined derives reopens the macro design space that Edda explicitly rejects.

These are not promised for any version. They are documented here so that future authors do not propose them under the assumption that the door is left open.

---

The locked surface in this document is sufficient for Edda's bootstrap. Every generic data structure, every metaprogramming pattern, and every introspection use case in the current codebase routes through specs and comptime as described above. The composition of these two pillars — content-addressed parameterised modules and a deterministic comptime evaluator with closed introspection — is the entire Edda metaprogramming story.
