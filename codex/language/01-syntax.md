# Edda — Locked Syntax Surface (V1.0)

This document is the canonical syntax reference for Edda. Every form admitted by the parser is listed here. Forms not listed here are not admitted. The shape of the surface is locked; semantics layered on top of these forms live in the sibling docs:

- [02-modes-effects-refinements.md](02-modes-effects-refinements.md) — modes, effects, refinements, capabilities
- [03-verification.md](03-verification.md) — SMT discharge, certificates, stability, contract diff
- [04-specs-comptime.md](04-specs-comptime.md) — spec language, comptime evaluation, derive forms
- [05-concurrency-coherence.md](05-concurrency-coherence.md) — `scope(exec)`, `scope(coherence)`
- [06-tooling.md](06-tooling.md) — daemon, MCP, LSP, attribute family
- [07-distribution.md](07-distribution.md) — content addressing, runes (`.rune`), package layout
- [08-packages.md](08-packages.md) — package management: Mímir, manifests, lockfile, CLI

Edda's design thesis is that the LLM author is given all the context the model could possibly need to generate correctly. The syntax is verbose, explicit, and locally readable. Every signature carries enough information — effects, modes, refinements, capabilities — that a generator does not need to chase definitions across files to know whether a call is legal. The forms below are chosen with that thesis as their first principle, ahead of any tradition borrowed from C, Rust, or ML.

---

## 1. Lexical surface

### File header

Every `.ea` file begins directly with a `module <root>.<file>` declaration naming this file's position in the package's module tree. There is no file-level doc comment — Edda admits no comment tokens (see "Comments — none admitted" below). The structure map is derived entirely from checked facts (signatures, effect rows, refinements, `calls`), never from authored prose.

```edda
module path.helpers

import std.core.option
import std.text.string.{split, join}

public function normalize(p: String) -> String { ... }
```

### Identifiers

Edda enforces a small, mechanical naming convention. The compiler rejects identifiers that violate it; the formatter does not silently rewrite them.

| Item | Convention | Example |
|------|------------|---------|
| Types | `CamelCase` | `Option`, `Filesystem`, `TcpStream` |
| Type fields | `snake_case` | `read_timeout`, `next_id` |
| Sum variants | `snake_case` | `.not_found`, `.permission_denied` |
| Functions | `snake_case` | `read_file`, `from_utf8` |
| Bindings (let/var) | `snake_case` | `path`, `buffer_size` |
| Primitives | lowercase | `i32`, `usize`, `bool` |
| Modules / namespaces | `snake_case` | `std.os.fs`, `local.parser.tokens` |
| Attributes | `snake_case` | `@deprecated`, `@layout` |

Identifiers must start with an ASCII letter or underscore and contain only ASCII letters, digits, and underscores. Unicode identifiers are not admitted.

### Reserved keywords

The following words are reserved and may not be used as identifiers. The list is closed: the parser admits no other keywords.

```
function   type        spec        comptime    let
var        uninit      public      mutable     take
init       with        where       requires    ensures
decreases  result      forall      exists      return
match      case        if          else        loop
for        in          break       continue    raise
panic      handle      scope       captures    provides
as         import      true        false       stable
unstable   linear      affine      derive      extern
```

`result` is reserved exclusively as the implicit binding for the return value inside `ensures` clauses. It is not a general identifier and not a control-flow keyword.

`forall` and `exists` are the bounded-quantifier keywords; they are admissible only in refinement positions (`where` / `requires` / `ensures`) and are part of the V1.0 surface.

`spec` is reserved because the spec invocation form `spec std.core.option.Option(i32)` lives at the top of files; the language for writing specs lives in [04-specs-comptime.md](04-specs-comptime.md).

`stable` and `unstable` are **contextual soft-keywords**: the lexer emits them as ordinary identifiers and the parser recognizes them only in stability-declaration position, so they remain admissible as identifiers everywhere else — `let stable = 3`, a field named `stable`. The native self-host and the Rust bootstrap agree on this. `linear`, `affine`, and `derive` are **not** soft — both lexers reserve them unconditionally and reject them as identifiers. `extern` (the external-implementation body-form, §Functions) is likewise **hard-reserved**: both lexers emit it as a keyword everywhere and the parser recognizes the `extern "symbol"` body-form in body position. The keyword-elimination pass that produced the soft-keyword rule softened only `stable`/`unstable`; it did not extend to `linear`/`affine`/`derive`/`extern`.

### Comments — none admitted

Edda source admits no comment tokens. The lexer rejects every one — `//`, `///`, `//!`, `/!!`, `!!!`, and block comments (`/* ... */`) — with `error[comment_not_admitted]`. There is no doc-comment tier system. Every function a comment would serve relocates: claims about code go into effect rows, refinements, attributes, or the issue tracker; descriptions are *derived* into the structure map from signatures, effect rows, refinements, and the call graph (never authored by hand); rationale and intent live in the conversation and the issue tracker, not in source.

### Numeric literals

Integers admit decimal, hex, binary, and octal forms. The underscore `_` is a digit separator and may appear anywhere except as the first character of a literal.

```edda
let dec: i32 = 1_000_000
let hex: u32 = 0xDEAD_BEEF
let bin: u8  = 0b1010_0101
let oct: u32 = 0o755
```

Float literals require a digit before and after the decimal point; `.5` and `5.` are not admitted.

```edda
let pi: f64    = 3.141_592
let nano: f64  = 1e-9
let avo: f64   = 6.022e23
```

A numeric literal without a type annotation defaults to `i64` for integers and `f64` for floats. The default applies only when the context does not impose a type; in `let x: u8 = 5` the literal `5` is typed as `u8`.

### String literals

Three forms are admitted.

```edda
let single: String      = "hello"
let interp: String      = f"hello, {name}"
let multi:  String      = """
    line one
    line two
"""
```

`"..."` is a single-line string. The newline character `\n` and standard escapes (`\t`, `\r`, `\0`, `\\`, `\"`) are honored. A literal newline inside `"..."` is a parse error — use the triple-quoted form for multi-line content.

`f"..."` is an interpolated string. Any expression inside `{...}` whose type has a canonical formatter (primitives, `bool`, `String`, derived-`debug` types) is admitted and interpolated in place — verified with a non-trivial arithmetic expression (`f"{n + 1}"`), not just bare identifiers/dotted paths. No `to_string` call is written at the use site.

`"""..."""` is a triple-quoted string. The leading newline immediately after the opening triple-quote is stripped. Common leading indentation, measured against the indentation of the closing triple-quote, is removed from each line. This makes embedded code or text legible without leaking the surrounding indentation into the value.

### Whitespace

Edda is not indentation-significant. Block structure is `{ ... }`. Whitespace matters in two narrow places:

- A newline between two expressions terminates the first; semicolons are not required (and not admitted) at the ends of expression statements.
- The position of `with`, `where`, `requires`, `ensures`, and `decreases` clauses on a function signature is enforced by the formatter, not the parser. Either single-line or multi-line layouts parse identically.

---

## 2. Top-level structure

A file consists of, in order:

1. A mandatory `module <root>.<file>` declaration (the first element of every `.ea` file).
2. Zero or more `import` declarations.
3. Zero or more `spec` invocations.
4. Zero or more `derive` declarations.
5. Zero or more top-level items (`function`, `type`, attribute-prefixed forms).

Declaration order within sections is significant only for `import` (lexical) and `spec` (instantiation). Top-level items in section 5 may be declared in any order; no forward declaration is needed.

### Imports

```edda
import std.core.option
import std.os.fs.{read_bytes, write_bytes, path_exists}
import std.os.fs as fs
import local.parser.tokens
import local.parser.tokens.{Token, kind}
```

`import std.core.option` brings the module name `option` into scope; uses are `option.Option(...)` or, after `spec`, `Option_i32`.

`import std.os.fs.{read_bytes, write_bytes}` brings the named items into scope unqualified. The selection list is enclosed in braces and is comma-separated.

`import std.os.fs as fs` aliases the imported module. Uses are `fs.read_bytes(...)`. Aliases must be unique within a file.

`import local.parser.tokens` references a sibling within the current package. An import path resolves through one of three classes: `std` for the standard library, `local` for the current package's local modules, and any other leading segment for a rune dependency declared in the package manifest or for another workspace member's root namespace. There are no relative imports.

### Spec invocations

A spec is a generic-like form whose instantiation is performed at compile time and produces a concrete module. The invocation form lives at file scope, immediately after imports:

```edda
spec std.core.option.Option(i32)
spec std.collections.vec.Vec(String)
spec std.core.range.Range(usize)
```

`spec std.core.option.Option(i32)` generates a module named `Option_i32` and makes its items (`Option_i32.some`, `Option_i32.none`, `Option_i32.is_some`, ...) visible from this file's scope. The mangling rule is positional: `Module(T)` becomes `Module_T`; `Module(T, U)` becomes `Module_T_U`; nested instantiations are joined with `_`.

Full spec syntax — `comptime` parameters, `provides`, `derive`, the spec body — is documented in [04-specs-comptime.md](04-specs-comptime.md). For this document's purposes, the only fact that matters is: types are not parameterized at use sites. `Option<i32>` is not admitted; the user writes `spec std.core.option.Option(i32)` once and refers to `Option_i32` thereafter.

### Module declarations

Every `.ea` file begins with a `module <root>.<file>` declaration — it is the first element in the file, with no comment preceding it (Edda admits no comments). A file at `lib/foo/src/bar.ea` declares `module foo.bar`:

```edda
module foo.bar

public function ...
```

The declaration names this file's position in the package's module tree. Without it, cross-file type references in the same package fail with `error[import_resolution_error]: unresolved path <Type>`. A `module` directive that names a path other than the path-implied one overrides the default.

### Visibility

`public` is the only visibility modifier. It applies to top-level items only:

```edda
public function read_bytes(...) -> [u8] { ... }

public type Point { x: f64, y: f64 }

function internal_helper() { ... }
```

The absence of `public` makes an item internal to its module. There is no `private` keyword (its absence is the default), no `crate` or `package` scope, and no `protected` visibility. Cross-module visibility for a non-`public` item is a hard error.

### Attributes

Attributes are prefixed with `@` and applied to the item directly below them. They take an optional argument list in parentheses.

```edda
@deprecated(reason: "Use `read_bytes` instead.", since: "v0.2")
public function read_blob(fs: Filesystem, path: String) -> [u8] { ... }
```

The attribute family is a **closed whitelist** of exactly nine — `@layout`, `@align`, `@repr`, `@abi`, `@unverified`, `@trust`, `@deprecated`, `@property`, `@target_requires` — documented in [06-tooling.md](06-tooling.md). There are no user-defined attributes and no open extension point: the parser hard-rejects any other `@name` at parse time with `error[unknown_attribute]`. This closure is the sterility backstop for the no-comment lock — attributes are exactly where claims about code relocate once prose leaves source (see "Comments — none admitted"), so a permissive `@`-namespace would reopen that drift surface as a smuggling vector (`@invariant("…")`, `@note("…")`); sealing the namespace is what keeps the relocation target itself sterile. Their arguments use a `key: value` calling form — one of exactly three places where named-style arguments appear in Edda, alongside named variant payloads (§Sums) and the entries of `with` / `captures` rows.

Each attribute is *orthogonal, removable metadata* on an already-complete item — strip any of them and the item still parses. In particular, `@abi("symbol")` is **pure symbol-name override**: it renames the exported symbol of a function that *has* a body, and removing it leaves the item well-formed. It does **not** license a bodyless function — external implementation is the `extern "name"` body-form (§Functions), a structural fact in the body slot. An attribute the grammar *depended on* for well-formedness ("a body is required… unless `@abi` is present") would be grammar wearing an attribute's clothes; external-implementation is declaration-vs-definition structure, not a claim about code, so it lives in grammar. This refines, rather than overturns, the "attributes are the relocation target for claims about code" framing above.

---

## 3. Type expressions

### Primitives

| Group | Members |
|-------|---------|
| Signed integers | `i8`, `i16`, `i32`, `i64`, `i128`, `isize` |
| Unsigned integers | `u8`, `u16`, `u32`, `u64`, `u128`, `usize` |
| Floats | `f32`, `f64` |
| Boolean | `bool` |
| Unit | `()` |
| Bottom | `never` |
| Text | `String`, `Codepoint` |
| Meta | `Type` (comptime only) |
| Stdlib internal | `HeapPtr` |

`String` is owned, length-prefixed, UTF-8. `Codepoint` is a Unicode scalar value (a `u32` constrained by the refinement `< 0x110000` excluding surrogates).

`Type` is a first-class value during `comptime` evaluation only. Runtime values of type `Type` do not exist.

`HeapPtr` is reserved for stdlib internals (allocator handles, type-erased boxes). User code does not name it.

### Tuples

```edda
let pair: (i32, String)        = (42, "hi")
let triple: (f64, f64, f64)    = (1.0, 2.0, 3.0)
```

Tuples are admitted at arity 2 and above. The 1-tuple `(T,)` and zero-tuple `()` are not tuple types; `()` is the unit type.

Tuple element access is by zero-indexed dotted projection: `pair.0`, `pair.1`. A pattern-match on a tuple binds elements positionally — see Pattern Matching.

### Slices

```edda
let xs: [i32]               = collect_vec(0..<10)
let head: [i32]             = xs[..5]
let tail: [i32]             = xs[5..]
let middle: [i32]           = xs[2..<8]
let all: [i32]              = xs[..]
let one: i32                = xs[0]
```

`[T]` denotes a slice of `T`. Slices carry both length and element-mode. Indexing `xs[i]` returns a single element by the slice's element mode. Subrange indexing `xs[lo..<hi]` returns a slice that inherits the parent slice's mode (a mutable slice's subrange is mutable, an immutable slice's subrange is immutable).

Index expressions require the index to be in bounds. The compiler discharges this as a refinement obligation; an `xs[i]` site without `i < xs.len()` proved is a verification failure. See [02-modes-effects-refinements.md](02-modes-effects-refinements.md) and [03-verification.md](03-verification.md).

Subrange syntax forms:

| Form | Meaning |
|------|---------|
| `xs[lo..<hi]` | Half-open, low to high exclusive |
| `xs[lo..=hi]` | Closed, low to high inclusive |
| `xs[lo..]` | From `lo` to `xs.len()` |
| `xs[..hi]` | From `0` to `hi` (exclusive) |
| `xs[..=hi]` | From `0` to `hi` (inclusive) |
| `xs[..]` | Whole slice (used in patterns and re-borrows) |

### Range literals

Outside of indexing, range literals construct a `Range_T` instance:

```edda
spec std.core.range.Range(usize)
spec std.core.range.Range(i32)

for i in 0..<n     { ... }
for i in 0..=n     { ... }
```

Range literals are sugar for `Range_T.new(lo, hi, kind)`. They are not slice-only; they are admitted anywhere a value is expected, provided the appropriate `spec` has been invoked.

### Refined inline types

A type position may carry a refinement clause:

```edda
function get(v: [i32], i: usize where i < v.len()) -> i32 { v[i] }
```

`i: usize where i < v.len()` is a refined parameter. The clause is a predicate referring to other parameters and constants in scope. The compiler emits a verification obligation at each call site of `get`. Refinements outside of parameter and return positions live in `requires`/`ensures`; see Declarations.

### Function types

A first-class function value's type is:

```edda
function(i32, String) -> bool with {fs, err: stream.IoError}
```

This is the type of a closure or free-function reference. The argument list is positional; modes on arguments are admitted (`function(mutable [u8]) -> ()`); the effect row after `with` is mandatory if the function performs effects. Full effect-row treatment is in [02-modes-effects-refinements.md](02-modes-effects-refinements.md).

---

## 4. Declarations

### Functions

The function form is:

```edda
function name(param_list) -> ReturnType
    with {effects}
    where <refinements>
    requires <precondition>
    ensures  <postcondition>
    decreases <termination-measure>
{
    body
}
```

A minimal function:

```edda
function add(a: i32, b: i32) -> i32 { a + b }
```

A function with the full clause set:

```edda
public function read_at(fs: Filesystem, path: String, offset: u64, len: usize)
    -> [u8]
    with {fs, err: stream.IoError}
    requires len > 0
    ensures  result.len() <= len
{
    ...
}
```

`with {effects}` declares the effect row. An empty row may be written as `with {}` or omitted. The effect row is mandatory for any function that reads or writes through a capability, raises an error, allocates, or spawns. See [02-modes-effects-refinements.md](02-modes-effects-refinements.md).

`where` introduces refinement bindings reused by `requires`/`ensures`. `requires` is the precondition checked at call sites; `ensures` is the postcondition checked once at the return point. Inside `ensures`, the keyword `result` refers to the return value.

`decreases <expr>` is required on every `loop` that is not bounded by an iterator and on every recursive function whose termination is not structurally obvious. The expression must be a natural-number-valued quantity that strictly decreases at each recursive call or loop iteration. See [03-verification.md](03-verification.md).

A function has exactly one **body-form** in the body slot — either a block `{ ... }` or an `extern "symbol"` form for an externally-implemented function:

```edda
function alloc_array(allocator: Allocator, count: usize) -> [u8]
    with {allocator, err: alloc.AllocError}
    extern "__edda_alloc_array"
```

`extern "symbol"` declares that the function has no Edda body; its implementation is the named external symbol. It occupies the body slot grammatically parallel to `{ ... }`, so the grammar enforces "exactly one body-form" and well-formedness is decidable locally — a function is never bodyless-by-omission. `extern` is a **hard-reserved keyword**: both the native self-host and the Rust bootstrap lexer emit it as a keyword everywhere (it is not admitted as an identifier), and the parser recognizes the `extern "symbol"` body-form in body position. The soft-keyword rule covers only `stable`/`unstable`; it does not extend to `extern`.

This is the **structural** form for external implementation — declaration-vs-definition is a structural fact, like the mandatory return type, and belongs in grammar. It is distinct from the `@abi("symbol")` attribute, which is orthogonal, removable symbol-name-override *metadata* (§Attributes) usable on a function that *has* a body; `@abi` does not license bodylessness.

### Records (product types)

```edda
public type Point {
    x: f64,
    y: f64,
}

public type Buffer {
    bytes: [u8],
    cursor: usize,
    capacity: usize,
}
```

Fields are **newline-separated**; commas between fields are admitted but unidiomatic. A trailing separator is admitted. Field declarations are `name: T` (or with modes: `name: mutable T` — see [02-modes-effects-refinements.md](02-modes-effects-refinements.md)). A record's fields are accessed by `obj.field`.

Records do not have constructors as a language feature. The literal form `Point { x: 1.0, y: 2.0 }` constructs a value when all fields are visible (struct-literal initialisers use comma separators between fields). For records with non-trivial validation, a free function (`Point.new`, `Buffer.with_capacity`) provides the validated construction; convention is to colocate it with the type.

Struct-literal field initialisers **admit mode keywords** and **require `take` for non-default ownership transfer**, exactly as at call sites: `Point { origin: take p }` consumes `p`; bare `Point { origin: p }` does not transfer ownership. A field initialiser is otherwise an ordinary expression. The motivation is uniformity with the call-site rule (§Mode at the call site, [02-modes-effects-refinements.md](02-modes-effects-refinements.md)): ownership transfer is the same operation in both positions, and consumption must be **locally visible** — reading `Point { origin: p }` must never silently consume `p` depending on `p`'s (non-local) linearity. Making consumption invisible is precisely what the linear/affine system exists to prevent.

### Sums (variant types)

```edda
public type Direction {
    case north
    case south
    case east
    case west
}

public type IoError {
    case os_error(code: i32)
    case unexpected_eof
    case broken_pipe
    case other
}

public type Tree {
    case leaf
    case branch(Tree, Tree)
}
```

Sum types use `{ ... }` containing one or more `case` declarations. Variant names are `snake_case`, dot-prefixed at every use site. Variants are newline-separated; commas between cases are admitted but unidiomatic.

Three payload forms are admitted:

- **No payload** — `case unexpected_eof`.
- **Positional payload** — `case branch(Tree, Tree)`; constructed positionally as `.branch(.leaf, .leaf)`.
- **Named payload** — `case os_error(code: i32)`; constructed with the field name as `.os_error(code: 32)`. Named-payload variants are the dominant form in stdlib and prototypes — they read like keyword arguments at the construction site and propagate field names into pattern matches.

At a value site, a variant is constructed qualified with its type:

```edda
let d: Direction = Direction.north
let e: IoError   = IoError.os_error(code: 32)
let t: Tree      = Tree.branch(Tree.leaf, Tree.leaf)
```

Construction qualifies with the type (`Direction.north`, `IoError.os_error(code: 32)`). The dot-prefixed bare form (`case .north => ...`) is the pattern syntax inside `match`, where the parent type is fixed by the scrutinee.

### No type parameters

A type may not introduce comptime parameters at its declaration. The following form is not admitted:

```edda
type Stack<comptime T: Type> { items: [T] }
```

The replacement is a spec module — see [04-specs-comptime.md](04-specs-comptime.md). The user writes the stack inside a spec, invokes `spec std.collections.stack.Stack(i32)`, and then refers to `Stack_i32`.

### Stability modifiers

A function may carry a stability modifier as the first token of its declaration:

```edda
stable function read_bytes(fs: Filesystem, path: String) -> [u8]
    with {fs, err: stream.IoError} { ... }

unstable function streaming_read(fs: Filesystem, path: String)
    -> [u8] with {fs, err: stream.IoError} { ... }
```

`stable` declares that this function's signature, effects, and contract are part of the package's stable surface. The verifier enforces that a stable function's contract is implementable; the contract-diff tool refuses to weaken or break it across versions. See [03-verification.md](03-verification.md). `unstable` is the explicit opposite. Absence means the default for the item's visibility: `public` items default to `unstable`; non-`public` items have no stability obligation.

`stable` and `unstable` modifiers also apply to top-level `type` declarations.

### Linear and affine types

A `type` declaration may carry a `linear` or `affine` modifier:

```edda
linear type Filesystem { ... }
affine type Allocation { ... }
```

`linear type T` declares that values of `T` must be consumed exactly once. `affine type T` declares that values of `T` must be consumed at most once. These modifiers shape how the compiler tracks ownership through modes; full treatment is in [02-modes-effects-refinements.md](02-modes-effects-refinements.md).

---

## 5. Statements vs. expressions

Edda is expression-oriented. The forms that produce values include all literals, all calls, all field/index accesses, `if`, `match`, `loop`, `scope`, block expressions, and the diverging forms (`return`, `break`, `continue`, `raise`, `panic`).

The diverging forms have type `never`. `never` unifies with every type, so `let x: i32 = if cond { 5 } else { return -1 }` typechecks: the `else` branch has type `never`, which is compatible with `i32`.

`for` is a statement, not an expression. A `for` loop does not produce a value; the user pushes into a `Vec` inside the loop body when accumulation is needed. This asymmetry is deliberate: `for` is overwhelmingly used for side effects; the rare collecting case is written as an explicit accumulator (see `for` under Control flow).

A block expression `{ ... }` is a sequence of statements followed by an optional final expression. If the final form is an expression, the block's value is that expression's value. If the final form is a statement (or the block is empty), the block has value `()`.

```edda
let x: i32 = {
    let a = compute()
    let b = adjust(a)
    a + b
}

let y: () = {
    log("done")
}
```

There is no expression-statement distinction at the grammar level; any expression may stand as a statement. An expression statement whose result is non-`()` and is unused is a hard error. To deliberately discard a value, bind it: `let _ = side_effecting()`. There is no `discard` keyword.

---

## 6. Expressions

### Literals

Numeric, string, boolean, and unit literals are admitted as detailed in the lexical section. `true`, `false`, and `()` are the canonical forms.

### Paths

Names resolve through a path:

```edda
let a = some_local_binding
let b = std.core.option.Option_i32.none
let c = fs.read_bytes
```

A bare name resolves against the current scope's bindings. A dotted path resolves through module names, with the final component naming an item.

### Method-call sugar

A method call `obj.method(args)` is sugar for the free function call `method(obj, args)`. Edda has no impl blocks, no traits, and no `Self` parameter. The method-call sugar is purely syntactic: the same function may be called with either form.

```edda
let n = vec.len(my_vec)
let n = my_vec.len()

let s = string.to_uppercase(name, allocator)?
let s = name.to_uppercase(allocator)?
```

Method-call sugar is the conventional form for stdlib operations on the receiver. The free-function form is conventional when the receiver is computed by another expression or when reading left-to-right is clearer with the function leading.

### Field, index, and call

```edda
obj.field
xs[i]
xs[lo..<hi]
f(a, b)
```

Calls of free functions and methods are positional. Edda does not admit named arguments at ordinary call sites. Named-style syntax appears in exactly three places — attribute arguments (`@deprecated(reason: "...", since: "...")`), named variant payloads (`.os_error(code: 32)`), and the entries of `with` / `captures` rows — none of which is an ordinary function call.

Non-default modes echo at the call site. The default mode is `let` (immutable, value-shaped). To pass a `mutable` parameter, the caller writes:

```edda
write(mutable buffer, b'!')
```

To pass a `take` parameter, the caller writes:

```edda
consume(take owned_value)
```

The mode echo is mandatory; passing a value to a non-default-mode parameter without the keyword is a hard error. The detailed semantics of modes are in [02-modes-effects-refinements.md](02-modes-effects-refinements.md).

### Tuple, struct, variant construction

```edda
spec std.core.outcome.Outcome(i32, String)

let pair       = (a, b)
let point      = Point { x: 1.0, y: 2.0 }
let dir        = Direction.north
let outcome    = Outcome_i32_String.ok(value: 42)
```

A struct literal requires all fields to be visible in scope. A struct literal with a missing required field is a hard error; there is no `..default` short-hand. To construct from a default, call a free function (`Point.origin()`). A field initialiser that transfers ownership must say so with `take` (`Point { center: take c }`); see §Records.

### Range expressions

Bare range expressions are forms `lo..<hi`, `lo..=hi`, `lo..`, `..hi`, `..=hi`, `..`. In indexing context, they describe a subrange; outside indexing, they construct a `Range_T` value provided the matching `spec` has been invoked.

### Casts

```edda
let x: u8        = some_i32 as u8
let y: u8        = some_i32 as u8 wrapping
let z: u8        = some_i32 as u8 saturating
let w: u8        = some_i32 as u8 checked
```

The trapping form `value as T` is the default. It panics at runtime if the source value does not fit in `T`. The compiler will discharge the no-overflow obligation when possible (a `usize` known to be `< 256` cast to `u8` is safe statically); a residual obligation that cannot be discharged surfaces as a verification failure.

The modifier forms `wrapping`, `saturating`, and `checked` express explicit intent. `checked` shifts the cast from trapping to an `err: Overflow` effect, which the caller must handle or propagate.

### Boolean operators

```edda
a && b
a || b
!a
```

`&&` and `||` short-circuit. No other operators bind to `and`/`or`/`not` keywords.

### Comparison

```edda
a == b
a != b
a < b
a <= b
a > b
a >= b
```

Comparisons are non-associative. `a < b < c` is a parse error; the user writes `a < b && b < c`.

### Arithmetic

Default arithmetic operators trap on overflow:

```edda
a + b
a - b
a * b
a / b
a % b
```

Integer `%` is **Euclidean** modulo: for any `b != 0` the result satisfies `0 <= result < abs(b)` (always non-negative, independent of the signs of the operands), matching SMT-LIB `(mod x y)` so a modulo refinement discharges in one solver call. Both `/` and `%` trap on `b == 0` and on `INT_MIN` with divisor `-1`; `%?` is the checked modulo variant (raises `err: Overflow`). There is no wrapping or saturating modulo.

Explicit-mode arithmetic operators:

| Operator family | Suffix | Behavior |
|-----------------|--------|----------|
| Wrapping | `+%`, `-%`, `*%` | mod 2^N |
| Saturating | `+|`, `-|`, `*|` | clamp to type bounds |
| Checked | `+?`, `-?`, `*?`, `%?` | `err: Overflow` effect |

```edda
let counter: u8       = counter +% 1
let dim: u32          = dim +| amount
let total: i64        = a +? b
```

Float arithmetic uses the default `+ - * /` operators with IEEE 754 semantics; there is no float overflow trap. Float division `a / b` carries the built-in obligation `b != 0.0`; a division site without that fact proved is a verification failure — discharge it with `requires b != 0.0` or a `where` clause on the parameter.

### Bitwise

```edda
a & b
a | b
a ^ b
~a
a << n
a >> n
```

Bitwise operators apply to integer types only. Shifts trap if `n` exceeds the bit width.

### Error propagation

```edda
let bytes = fs.read_bytes(rfs, path, allocator)?
```

`expr?` propagates an `err: T` effect outward. If `expr` raises `err: fs.FsError`, the surrounding function must declare `err: fs.FsError` in its effect row; the `?` either unwraps to the success value or short-circuits to the function's caller with the error. `?` is the only form of error propagation.

`?` operates only on effect-row errors. It does not apply to `Option_T` (use `match`) or to `Outcome_T_E` (also `match`). The reason is that Edda treats failure as an effect, not as a value shape; collapsing the two would dilute the signal that `with {err: stream.IoError}` carries in a signature.

### `result` in `ensures`

Inside an `ensures` clause, `result` is a binding for the function's return value:

```edda
function half(n: i32) -> i32
    ensures result * 2 == n
{
    n / 2
}
```

`result` is a keyword in this context only. It cannot be used as an identifier anywhere else.

---

## 7. Control flow

### `if`

`if` is an expression. Each branch is a block expression.

```edda
let label =
    if score > 90      { "excellent" }
    else if score > 70 { "good" }
    else if score > 50 { "pass" }
    else               { "fail" }
```

The `else` branch is optional when the overall expression's value is unused (i.e., the surrounding context expects `()`). When `if` is used as a value, all branches must produce compatible types.

### `match`

`match` is an expression. The arms are introduced by `case`.

```edda
let label = match dir {
    case .north => "up"
    case .south => "down"
    case .east  => "right"
    case .west  => "left"
}
```

Each case has the form `case <pattern> => <expression>`; arms are newline-separated — commas between arms are not admitted. Matches must be exhaustive; the compiler requires either total coverage or a wildcard `case _ => ...`.

Match patterns may be guarded:

```edda
match n {
    case 0           => "zero"
    case let x where x > 0 => "positive"
    case _            => "negative"
}
```

### `loop`

`loop` is an expression. By default it does not terminate; its value type is `never` unless `break value` produces an early exit:

```edda
let answer = loop {
    let x = next()
    if check(x) {
        break x
    }
}
```

A `loop` without an `iterator` form must carry a `decreases` clause if it is to be verified:

```edda
loop decreases (n - i) {
    if i >= n { break }
    process(i)
    i = i + 1
}
```

The `decreases` expression must be a non-negative integer-valued quantity that strictly decreases on each iteration. See [03-verification.md](03-verification.md).

### `for`

`for` is a statement. It iterates over a spec-provided iterator:

```edda
for i in 0..<n {
    sum = sum + xs[i]
}

for (k, v) in dict.entries() {
    process(k, v)
}
```

`for x in iter { ... }` desugars to a call to the iterator protocol (see [04-specs-comptime.md](04-specs-comptime.md)). It produces no value; to accumulate, push into a `Vec`:

```edda
spec std.collections.vec.Vec(i64)

uninit out: Vec_i64.Vec
Vec_i64.new(init out, allocator)?
for x in xs {
    if keep(x) { Vec_i64.push(mutable out, x, allocator)? }
}
```

### `break`, `continue`, `return`

`break` exits the nearest enclosing `loop`. `break value` exits with a value. `continue` re-enters the next iteration.

`return expr` exits the enclosing function with a value. `return` with no expression is admitted when the function returns `()`.

All three have type `never`.

### `raise` and `panic`

```edda
raise fs.FsError.not_found(path: path)

panic("invariant violated: cursor exceeded buffer length")
```

`raise <error-value>` adds an `err: T` effect to the current function's effect row. The function's signature must declare `err: T` to admit a `raise` of that type.

`panic("...")` aborts the current process. It is not catchable. Panics are reserved for unreachable program states; ordinary failures use `raise`.

Both have type `never`.

### `handle`

```edda
let data = handle err: fs.FsError as e -> [] {
    fs.read_bytes(rfs, path, allocator)?
}
```

`handle <effect>: <Type> as <binder> -> <recovery-expr> { body }` runs the body and intercepts the named effect, binding the caught value to `<binder>` and replacing the effect with the recovery expression. The handler removes the effect from the surrounding function's effect row.

Full effect-handler treatment is in [02-modes-effects-refinements.md](02-modes-effects-refinements.md).

---

## 8. Pattern matching

Patterns appear in `match` arms and in `let` destructuring of tuples and records. The pattern forms locked in the V1.0 surface are:

### Variant patterns

```edda
case .ok(let value)
case .err(_)
case .none
```

### Tuple patterns

```edda
case (let a, let b)
case (let a, _)
```

### Struct patterns

```edda
case Point { x: let xv, y: let yv }
case Point { x: let xv, y: _ }
case Point { x: 0.0, y: let yv }
case Point { x: let xv, .. }
```

A struct pattern need not be exhaustive over fields; missing fields are implicitly ignored. The `, ..` rest marker is the explicit form and is what the formatter emits. Struct patterns are implemented in the native compiler; admission in the bootstrap is pending.

### Literal patterns

```edda
case 0                     => ...
case "hello"               => ...
case true                  => ...
```

### Wildcard

```edda
case _                     => ...
```

### Guards

```edda
case .some(let v) where v > 0    => ...
```

Pattern guards are arbitrary boolean expressions that further constrain the arm. A failed guard falls through to the next arm.

### Range patterns

```edda
case 0..<10                => "small"
case 0..=255               => "byte"
case 65..=90               => "ascii uppercase letter"
```

Range patterns admit the same `..<` (exclusive) and `..=` (inclusive) endpoint forms as range expressions. Bounds must be literal constants of an ordered primitive type (any integer width or `f32`/`f64`); non-constant bounds are not admitted in a pattern position. The pattern matches when `lo <= value` and (`value < hi` or `value <= hi`). Exhaustiveness analysis treats ranges as covering their endpoint span — `case 0..=255` covers the full `u8` domain.

### Or-patterns

```edda
case .north | .south       => "vertical"
case .ok(let v) | .also_ok(let v)   => v
case 0 | 1 | 2             => "tiny"
```

The `|` operator combines pattern alternatives. Every alternative must bind the same set of names, with the same types, in the same modes — `case .ok(let v) | .err(let e)` is rejected (binder set differs). Or-patterns nest inside other patterns: `case (let a, .ok(let b) | .also_ok(let b))` is admitted. Guards apply to the whole arm after the `|` group: `case 0 | 1 where threshold > 0`.

### `@`-bindings

```edda
case whole @ .some(let v)              => use_both(whole, v)
case pt @ Point { x: 0.0, .. }         => log_origin_aligned(pt)
case window @ [_, _, _]                => exact_three(window)
```

`<name> @ <subpattern>` binds the matched value as `<name>` while also matching its shape against `<subpattern>`. The outer binder takes the whole value at the input's mode; the inner subpattern's binders work as usual. Useful when an arm body wants both the disassembled shape and the original aggregate without reconstructing it.

### Slice patterns

```edda
case [first, second]                   => pair(first, second)
case [head, ..tail]                    => head_and_rest(head, tail)
case [..init, last]                    => init_and_last(init, last)
case [first, ..middle, last]           => first_middle_last(first, middle, last)
case []                                => empty()
```

Slice patterns destructure `[T]` values. Bracketed positions match individual elements; `..name` binds the unmatched middle as a sub-slice, and `..` discards it. At most one rest binding is admitted per pattern. The fixed positions match left-to-right and right-to-left around the rest; the total slice length must be at least the count of fixed positions, otherwise the arm is skipped. The compiler discharges the bounds obligation on each fixed access; the rest binding carries the refinement `tail.len() == xs.len() - <fixed-count>`.

---

## 9. Bindings

### `let`

```edda
let x: i32 = 5
let name: String = "edda"
let pair = (1, 2.0)
```

`let` introduces an immutable binding. The binding may not be reassigned; if its contents are mutable (mode permitting), they may be modified through it. The type annotation `: T` is optional when the right-hand side is unambiguous.

### `var`

```edda
var counter: u32 = 0
counter = counter + 1
```

`var` introduces a mutable binding. The binding may be reassigned in its scope. `var` is the only form for reassignable bindings; `let mut x` is not admitted.

### `uninit`

```edda
spec std.collections.array.Array(u8, 4096)

uninit large_buffer: Array_u8_4096.Array
init_buffer(init large_buffer)
```

`uninit x: T` reserves storage for a value of type `T` without initializing it. The binding may not be read until an `init` call has written to it; the compiler tracks this through the linear/affine ownership tracking described in [02-modes-effects-refinements.md](02-modes-effects-refinements.md). Reading an `uninit` binding before it is initialized is a verification error.

`uninit` exists exclusively for performance-sensitive cases where zero-initialization is measurable. Stdlib types provide `T.new()` and `T.with_capacity(n)` for ordinary cases.

### Scope rules

Bindings are declared at expression position (inside a block). There are no module-level `let` or `var` declarations; module-level constants are `function name() -> T { value }`, evaluated and possibly `comptime`-cached. See [04-specs-comptime.md](04-specs-comptime.md).

### No shadowing within scope

```edda
let x = 5
let x = x + 1
```

The second binding above is a hard error. Within a single block, redeclaring a name is rejected. The user picks a new name (`let x_inc = x + 1`) or, if reassignment is the intent, uses `var`.

Shadowing across nested scopes is admitted — an inner block may bind a name declared in an outer block. The inner binding shadows the outer for the duration of the inner block. Explicit naming is preferred.

---

## 10. Closures (function values)

A closure expression has the form:

```edda
function(x: i32) -> i32 with {} captures {a, b} {
    a * x + b
}
```

The function keyword introduces a closure when it lacks a name. Parameter types and the return type are mandatory. The effect row and the `captures` clause are each optional: an absent row declares a pure closure, an absent `captures` clause declares zero captures. The body follows.

### Captures

The `captures` clause names the bindings the closure draws from its enclosing scope. Captures are explicit; there are no implicit closures over enclosing variables.

Each captured binding may carry a mode after the colon (`name: take` / `name: let`), exactly as a parameter mode sits after the colon; a bare name defaults to `let`:

```edda
captures {a, b}
captures {a, consumer: take}
captures {a: let, consumer: take}
```

The first line captures `a` and `b` by `let` (the default; read-only, scope-bound). The second captures `a` by `let` and moves `consumer` in by `take`. The third is the fully explicit form, equivalent to the second. `let`-captured bindings are read-only inside the closure and must outlive the closure's use. `take`-captured bindings are moved into the closure and owned by it; a `take`-capturing closure may escape its defining scope.

The capture modes `mutable` and `move` are not admitted. A `mutable` capture introduces aliasing that breaks the locality story; an explicit `move` keyword would duplicate `take`'s job.

### As an argument

A closure is a value of a function type. It may be passed to higher-order functions or stored in a struct field:

```edda
let mapped = vec.map(xs, function(x: i32) -> i32 with {} captures {} { x * 2 })
```

### Current lowering status

The grammar above (zero captures, multi-capture, `take`-mode capture) parses and typechecks in full. Codegen lowering is close behind but not yet complete: zero-capture closures (`captures {}`) and scalar captures — word-sized primitives, one or several, in `let` or `take` mode — lower and execute, including per-instance capture independence and escaping the defining scope (a scalar-captured closure may be returned from its capturing function). Record/aggregate captures and heap-backed escaping captures (`String`, records) are not yet reliable end-to-end — factor those cases into named top-level functions until they land.

---

## 11. Stdlib renames (carry-over)

A small set of stdlib namespaces have been renamed for clarity. The renames are mechanical and complete; the old names do not resolve.

| Old | New |
|-----|-----|
| `std.result` | `std.core.outcome` |
| `Result(T, E)` | `Outcome(T, E)` |

`Outcome(T, E)` is the carrier type for value-shaped success/failure. It is the value form of failure (used in collections, channels, returns where the failure mode is part of the API). Effect-based failure (`err: T`) is the form used for ordinary fallible functions.

---

## 12. Forbidden / explicitly removed

The following forms are not admitted. Each entry includes a one-line rationale.

- **No `let mut`.** Use `var`. The Rust-style `let mut` is two keywords for one binding kind; `var` is one.
- **No `&str`, `&T`, `&mut T`.** Modes (`let`, `mutable`, `take`) carry ownership and mutability at parameter declarations. Reference types as a separate concept do not exist.
- **No mode before name.** A parameter is `name: mutable T`, not `mutable name: T`. The mode binds to the type, not to the binding.
- **No modes on tuple-destructuring patterns.** A pattern `(let a, let b)` binds both as immutable; mixed modes on destructured tuple positions are deferred to post-V1.0 pending a worked example that presses for the grammar surface.
- **No `for`-as-expression.** `for` is a statement; collecting accumulators use a spec function. This is to avoid `for` expressions that surreptitiously allocate.
- **No `discard` keyword.** Use `let _ = expr`. The single underscore as a binding name is the unambiguous form.
- **No named arguments at call sites.** Positional arguments are the only call form. Named-style syntax exists in exactly three places — attribute arguments, named variant payloads, and `with` / `captures` rows — and none of them is an ordinary function call.
- **No multi-line `"..."` strings.** Use `"""..."""`. The single-line form is a parse error if a literal newline appears inside.
- **No `?.` or `??`.** Optional chaining is a tree-shaped form that hides null checks; Edda's `Option_T` is a sum type and is destructured with `match`.
- **No `?` on `Option_T` or `Outcome_T_E`.** `?` propagates `err: T` effects only. Value-shaped failure is destructured explicitly so its handling appears in the source.
- **No `Result<T, E>` as a fallible-function return type.** Fallible functions declare their failure mode as an effect (`with {err: stream.IoError}`) and either return `T` directly or are short-circuited at call sites with `?`. `Outcome` exists for the value-shaped failure case (channels, futures, batch results), not as the default return shape.
- **No `move` keyword on closures.** `take` in the `captures` clause is the moving form.
- **No implicit captures.** All captured bindings are named in `captures { ... }`; a closure with no `captures` clause captures nothing. A binding drawn from the enclosing scope without an entry in the clause is a hard error.
- **No `mutable` captures.** Captures are `let` or `take`. Mutable capture introduces aliasing that violates locality.
- **No `<T>` generic parameters on types or functions.** Generic-like parameterization is achieved through specs; see [04-specs-comptime.md](04-specs-comptime.md). The benefit is no-generics codegen: every spec instantiation produces a concrete module.
- **No traits, typeclasses, or `impl T { ... }` blocks.** Method-call sugar (`obj.method(args)`) desugars to free-function calls. Polymorphism over types is not a feature; spec instantiation covers the cases where the user would reach for it.
- **No virtual dispatch.** All function calls are statically resolved. The compiler may inline aggressively; there is no vtable.
- **No name shadowing within a single scope.** Cross-scope shadowing is admitted.
- **No order-dependent declarations at module scope.** Top-level items may be declared in any order; forward declarations are not needed.
- **No null, `nil`, or `undefined`.** Absence is `Option_T.none`. Uninitialized storage is `uninit x: T`, and reading it before `init` is a verification error.
- **No exceptions.** Failure is either an effect (`err: T`) or a value (`Outcome_T_E`).
- **No implicit conversions.** All numeric conversions go through `as T` (with optional `wrapping`, `saturating`, `checked`). String-to-number and number-to-string go through stdlib functions.
- **No operator overloading.** Operators apply to primitives and to specific stdlib types (e.g. `Fixed128` for deterministic arithmetic). User types do not declare operator implementations.
- **No inheritance.** Records and sums are flat. Composition through fields is the means of extension.
- **No runtime reflection.** Type information is available only at `comptime`. There is no `typeof(x)` at runtime, no dynamic dispatch by type identity, and no general-purpose introspection.
- **No headers, no preprocessor, no macros.** Comptime evaluation (see [04-specs-comptime.md](04-specs-comptime.md)) covers the cases where macros would otherwise be reached for.
- **No `assume` keyword.** Unverifiable assumptions use the attribute family — `@unverified` or `@trust` — at the item that needs them. The attribute form is surfaced in the structure map; an inline `assume` would not be.
- **No user-defined attributes.** The `@`-family is a closed whitelist of nine (§Attributes); the parser hard-rejects any other `@name` with `error[unknown_attribute]`. This seals the attribute namespace as the sterility backstop for the no-comment lock — without it, a fabricated attribute (`@invariant("…")`) would smuggle prose back into source.
- **No `Filesystem.new()` or other capability synthesis.** Capabilities are introduced only by the program's `main` (which receives them from the runtime) and passed down through arguments. Synthesizing a capability inside an arbitrary function defeats the entire effect system.
- **No fire-and-forget spawn.** Concurrency is launched through `scope(exec)`; every spawned task is joined at the scope's exit. See [05-concurrency-coherence.md](05-concurrency-coherence.md).
