# Modes, capabilities, effects, refinements

> The contract surface. Every Edda function signature carries four orthogonal
> kinds of information: parameter modes (how arguments flow), capabilities
> (what authority the function requires), effects (what observable behaviour
> it exhibits), and refinements (what predicates hold). Together they answer
> the question "what does this function do to the world?" — precisely enough
> for an LLM to author, an SMT solver to check, and a reviewer to audit.

This doc covers all four together because they compose. A `mutable`
capability flowing through a function appears in the row by parameter name;
a refinement on an integer parameter feeds a graded `alloc` bound; a `take`
parameter consumed inside a `handle` block changes mode-tracker state at the
handler boundary. Treating them as separate chapters obscures the
interactions that matter.

For lexical and declaration syntax see [01-syntax.md](01-syntax.md). For SMT
discharge, certificates, and termination proofs see
[03-verification.md](03-verification.md). For specs, comptime, and
`provides` clauses see [04-specs-comptime.md](04-specs-comptime.md). For
structured concurrency and coherence scopes see
[05-concurrency-coherence.md](05-concurrency-coherence.md).

---

## 1. The four-piece signature

Every Edda function signature has the same shape:

```edda
function name(p1: <mode1> T1, p2: <mode2> T2, ...) -> ReturnType
    with {<effect-row>}
    requires <precondition>
    ensures  <postcondition>
{ <body> }
```

Each piece is independently optional except the parameter list and the
return type. A pure, total, infallible function (`function add(x: i32, y:
i32) -> i32`) carries none of the optional clauses. A capability-using,
fallible function with bounded allocation and a refinement-typed parameter
may carry all of them at once.

The four pieces correspond to four distinct questions a caller (human or
LLM) needs answered before calling:

1. **Modes** — *for each argument, does my caller still own it after the
   call? Can the callee read it? Mutate it?*
2. **Capabilities** — *what authority must I already hold to call this?*
3. **Effects** — *what observable behaviour will the call produce?*
4. **Refinements** — *what must I prove before calling, and what may I
   assume after?*

The signature is the LLM's input. Inferring any of the four from the body
would force the model to re-derive constraints the author already knew. The
discipline is to write all four explicitly, with no inference shortcuts.

---

## 2. Parameter modes

### 2.1 Mode position and the four modes

A parameter declaration is `name: <mode> Type`, where `<mode>` is one of
`let`, `mutable`, `take`, `init`, or omitted (defaulting to `let`). The
mode sits between the colon and the type — never before the colon, never
after the type.

```edda
function read   (s: String)         -> usize { ... }
function write  (s: mutable String) -> ()    { ... }
function consume(s: take String)    -> [u8]  { ... }
function produce(out: init String)  -> ()    { ... }
```

`read` uses the default `let` mode: in a parameter declaration the `let`
keyword is **omitted**, never written. Spelling it (`s: let String`) is a
parse error — the parser, having consumed the colon, expects either one of
the three explicit mode keywords (`mutable` / `take` / `init`) or a type, and
`let` is neither (`error[parse_error]: expected type`). Only the three
non-default modes are written explicitly; the borrowed-immutable default is
always the bare form. The four modes describe the flow of the argument across
the call boundary:

- **`let`** (default; spelled by omission) — borrowed immutable view. The
  callee reads but does not mutate the value, and does not retain a reference
  after the call returns. The caller keeps ownership; the binding remains
  valid after the call. A `let`-mode `String` is what other languages spell
  `&str` — the mode carries the ownership story, and the type name `String`
  names the value; in a declaration it is written bare (`s: String`), with the
  `let` keyword omitted.
- **`mutable`** — borrowed mutable view. The callee may read and mutate the
  value in place; the caller keeps ownership. The binding remains valid
  after the call, but its contents may have changed.
- **`take`** — ownership transfers to the callee. The source binding is
  invalid after the call: any subsequent reference is a compile error. The
  callee may keep the value, drop it, return it, or pass it elsewhere.
- **`init`** — out-parameter. The argument must be an `uninit` binding at
  the call site; the callee writes a fresh value into it, after which the
  binding is valid. There is no input value to read; the callee receives
  storage, not a value.

### 2.2 Mode at the call site

Modes are mandatory at the call site whenever a non-default mode borrows or
consumes a binding. The keyword precedes the argument expression, mirroring
the parameter declaration:

```edda
let s = "hello"
let n = read(s)
write(mutable s)
let bytes = consume(take s)
uninit t: String
produce(init t)
let m = read(t)
```

The `let`-mode call needs no keyword; `mutable s` leaves `s` valid but
potentially changed; `take s` consumes `s` so any later use is an error;
`init t` initialises the previously-`uninit` `t`, after which `read(t)`
reads it. Omitting the keyword for a non-default mode is a mode-check error,
not a defaulting rule — but the check is scoped to what a reader could
misjudge, so it distinguishes a borrow of a place from ownership transfer of a
value. `mutable` and `init` borrow a named place and **always** require the
keyword at the call site: the reader must know the place may be written or
initialised. `take` requires the keyword only to consume a **binding**; a pure
rvalue — a constructor temporary, a literal, a struct/tuple literal, or a call
result — or a copy-type value needs no keyword at a `take` parameter, because
there is no surviving binding whose fate the reader could misread. Consuming a
`linear`/`affine` binding still requires `take`: omitting it borrows the value
and leaves it unconsumed, which the linearity check rejects
(`linear_unconsumed`). So the WYSIWYG guarantee — a
reader of the call knows whether each *binding* survives — holds without the
mode-check over-enforcing an echo on rvalues that name no binding. The call
site must visibly state the mode whenever a binding's post-call state depends
on it.

The visible keyword is the LLM-readability story: a reader of the call
expression knows immediately whether the binding survives the call, and in
what state. No analysis of the callee signature is required at the call
site to understand the local control flow.

The same rule governs **struct-literal field initialisers**: a field that
transfers ownership of a binding states `take` explicitly
(`Point { origin: take p }`); a field initialised from a pure rvalue — a
literal, a nested constructor, another struct/tuple literal — or a copy-type
value needs no keyword, exactly as a bare call argument does. A struct literal
is a value-construction site, but its field initialisers are arguments in the
same sense call arguments are — the consume-vs-borrow distinction is identical,
so the surface is identical. Reading `Point { origin: p }` must never silently
consume a `linear`/`affine` binding `p` on the basis of `p`'s (non-local)
linearity; the `take` token makes that consumption local, and omitting it
leaves `p` unconsumed (`linear_unconsumed`).

### 2.3 Worked example — each mode in turn

```edda
function length(s: String) -> usize {
    return s.len()
}

function append_bang(s: mutable String) -> () {
    s.push('!')
}

function into_bytes(s: take String) -> [u8] {
    return s.bytes()
}

function build_greeting(target: init String) -> () {
    target = "hello, world"
}

function demo() -> () {
    let name = "alice"
    let n = length(name)
    var greeting = "hi"
    append_bang(mutable greeting)
    let payload = into_bytes(take greeting)
    uninit msg: String
    build_greeting(init msg)
    let m = length(msg)
}
```

The `let` / `var` / `uninit` binding-form choice at the call site interacts
with the mode the call uses. `var` allows `mutable` at the call site;
`let` does not. `uninit` is required for `init`. `take` is admitted from
any binding form, with the side effect that the binding is invalidated.

### 2.4 Linear-flag and affine-flag types

A type declaration may carry a `linear` or `affine` flag (see
[01-syntax.md](01-syntax.md)). The flag modifies the mode discipline at
the type level:

- **`linear` type** — a value of this type MUST be consumed exactly once
  along every code path. Allowing the value to be dropped is a compile
  error. Database transactions, file handles in `Open` state, and one-shot
  channels are canonical linear types.
- **`affine` type** — a value of this type MUST NOT be consumed more than
  once, but may be dropped (consumed zero or one times). Cancellation
  tokens and idempotent commit handles are canonical affine types.

Linear-flag types interact with modes by tightening the rules: a `linear T`
value passed as `let` mode does not satisfy the "consumed exactly once"
obligation — only `take` does. A function returning a `linear T` value
imposes the consumption obligation on its caller. A `handle` block that
recovers from an error must ensure any linear value held in the body is
consumed on both the success and failure paths.

### 2.5 The mode tracker

The typechecker maintains a per-binding state in a small lattice:

- **Uninit** — declared but not initialised (only reachable from `uninit`).
- **Valid** — initialised, ownership intact, readable, mutable depending on
  binding kind (`let` vs `var`).
- **PartialInit(field_set)** — for record types, some fields initialised,
  others not. Reachable from inline struct construction in stages.
- **Consumed** — moved out by `take`; any subsequent read is a compile
  error.

Each statement and each call-site mode-keyword triggers a transition. The
rules are mechanical:

| From → To | Trigger |
|---|---|
| Uninit → Valid | argument used as `init` at a call site, or all fields initialised |
| Uninit → PartialInit | a single field assigned to an `uninit` aggregate |
| PartialInit → Valid | the remaining fields assigned |
| Valid → Consumed | argument used as `take` at a call site |
| Valid → Valid | argument used as `let` or `mutable` (contents may change for `mutable`) |
| Consumed → (error) | any reference is a compile error |

#### Worked example — mode-tracker trace

```edda
spec std.mem.alloc.Array(u8)

function process(allocator: Allocator) -> () with {allocator, err: alloc.AllocError} {
    let bytes = Array_u8.alloc(allocator, 16)?
    let s = string.from_owned_utf8(take bytes)
    var buf = s
    append_bang(mutable buf)
    let _ = buf.len()
    let _ = into_bytes(take buf)
    let _ = buf.len()
}
```

The tracker state after each statement:

| Statement | Resulting state |
|---|---|
| `let bytes = Array_u8.alloc(allocator, 16)?` | `bytes`: Valid |
| `let s = string.from_owned_utf8(take bytes)` | `bytes`: Consumed; `s`: Valid |
| `var buf = s` | `s`: Consumed; `buf`: Valid (mut) |
| `append_bang(mutable buf)` | `buf`: Valid (contents changed) |
| `let _ = buf.len()` | `buf`: Valid; reads OK |
| `let _ = into_bytes(take buf)` | `buf`: Consumed |
| `let _ = buf.len()` | error: `buf` is Consumed |

The state at each line is fully determined by the previous line plus the
syntactic mode used. There is no flow-sensitive inference beyond the
strictly local transition; an LLM author can read the function top-to-bottom
and know exactly which bindings are live at every point.

The `Uninit → PartialInit → Valid` field-by-field transition is also what drives **introspection-driven record construction** ([04-specs-comptime.md §4.5](04-specs-comptime.md), D-22): inside a spec body, a `comptime for i in 0..<field_count(T)` whose body assigns `out.(i)` (the comptime-indexed field) walks the same transitions per unrolled iteration, reaching `Valid` once every field is covered. No new state and no coverage proof beyond the staged-init discipline above — the unrolled loop emits exactly one assignment per field by construction.

### 2.6 Mode restrictions

Several positions in the grammar do not admit modes, because the mode
discipline would be ambiguous or unhelpful:

- **Tuple-destructuring patterns** carry bindings indefinitely; no mode
  keyword is admitted on the pattern. The bindings inherit the source's
  ownership: destructuring a `take` argument moves into the destructured
  bindings.
- **Closure captures** carry only `let` (default, declared bare) and
  `take` (declared `name: take` inside `captures {...}`). `mutable`
  captures are forbidden — mutation must flow through `mutable`
  parameters at the call site, never through a captured handle. See
  [01-syntax.md](01-syntax.md) for the closure capture grammar.
- **`for` loop bindings** are immutable views into the iterable;
  no mode keyword is admitted on the loop variable. To consume each
  element of a slice, use an explicit `take` at an inner call site.

---

## 3. Capabilities

### 3.1 The locked nominal catalogue

Capability types are *nominal*. Each capability is a distinct named type;
there is no parametric `Capability<X>` and no refinement-typed capability.
The locked catalogue is fixed for V1.0:

| Capability | Role |
|---|---|
| `Filesystem` | Full filesystem access. |
| `ReadOnlyFilesystem` | Read-only filesystem access. |
| `SandboxedFilesystem` | Filesystem access confined to a subtree. |
| `Network` | Full network access. |
| `LocalhostNetwork` | TCP/UDP to 127.0.0.1 only. |
| `RestrictedNetwork` | Network access restricted to a host allowlist. |
| `Clock` | Read system wall-clock time. |
| `MonotonicClock` | Read monotonic clock only (no wall-clock). |
| `Random` | Cryptographically strong random. |
| `DeterministicRandom` | Seeded deterministic random — reproducible. |
| `Allocator` | General heap allocation. |
| `BoundedAllocator` | Allocation with a per-instance byte cap. |
| `Executor` | Spawns concurrent tasks inside a `scope` block. |
| `Stdin` | Read from program standard input. |
| `Stdout` | Write to program standard output. |
| `Stderr` | Write to program standard error. |
| `Subprocess` | Spawn external processes (hosted only — see §3.5). |
| `Debugger` | OS process-control for the source debugger (hosted only — see below). |

These **eighteen** types are the locked nominal capability catalogue for
V1.0. The first sixteen are present across all hosted and WASI targets;
`Subprocess` (detailed in §3.5) and `Debugger` are hosted-only — their
per-target availability is in §3.7.

`Debugger` is the OS process-control capability backing the source debugger
(`edda debug`); it rides `ptrace` / `DebugActiveProcess`, so it is available
only on hosted operating systems (`linux` / `windows` / `macos` / `freebsd`),
exactly the availability class of `Subprocess`. Like `Stdin` / `Stdout` /
`Stderr` it has **no narrowing methods** — it is a leaf of the narrowing
lattice. Its nominal type is compiler-known; the process-control surface
(attach / detach / read-registers / set-breakpoint) lives in the stdlib and is
a roadmap item — the verification-aware source debugger it backs is not yet
built.

`Stdout` and `Stderr` are distinct capabilities: a tool that wants to write
diagnostics but not corrupt stdout-as-data takes `Stderr` only, and the
type signature alone makes that audit visible.

#### Browser / WebExtension capabilities (target-scoped)

Beyond the eighteen locked types above, the compiler's capability enum carries
a further four nominal capabilities that exist **only on `browser` targets**
(`wasm32-*-browser`):

| Capability | Role |
|---|---|
| `Dom` | Read/modify the document object model. |
| `Window` | Browser window/event-loop authority (timers, event listeners). |
| `ExtensionContent` | WebExtension content-script context. |
| `ExtensionWorker` | WebExtension background/service-worker context. |

These are nameable as parameter types only on `browser` targets (on every
other target they are not in scope, so naming one is an
`import_resolution_error`); a cross-target library gates them with
`@target_requires` — `std.task`, for example, marks its browser reactor
entry points `@target_requires(Window)`. Their stdlib operation surface
(DOM/Window, WebExtension contexts, the xlib bindings) is still in
progress, so unlike the eighteen above they are **not** part of the
always-shipped V1.0 stable surface. Whether they should join the headline
locked count in the `CHARTER` is a corpus-wide decision still under audit.

### 3.2 No capability synthesis

A capability is not constructible. There is no `Filesystem.new()`, no
`Allocator.global()`, no module-level capability binding. Capabilities
arrive in a program by exactly two paths:

1. **Runtime mint at `main`.** The runtime mints exactly the capabilities
   the `main` signature names — see [01-syntax.md](01-syntax.md)
   *Entry-point shape*. There is no `World` aggregate; `main` enumerates
   each primitive capability it needs as an individual parameter.
2. **Narrowing from a held capability.** A function holding a wider
   capability can derive a narrower one via a method declared on the
   wider type.

The narrowing methods form a closed lattice from each primitive capability
down to its narrowest leaves:

```edda
function setup(
    fs: Filesystem,
    net: Network,
    clock: Clock,
    rng: Random,
    alloc: Allocator,
    exec: Executor,
) -> () with {fs, net, clock, rng, alloc, exec} {
    let logs   = fs.scoped_to_w("/var/log")
    let ro_etc = fs.read_only()
    let lo     = net.bind_localhost(8080)
    let mono   = clock.monotonic()
    let det    = rng.deterministic(42)
    let child  = alloc.fork()
    ...
}
```

Each binding's narrowed type: `logs` is a `Filesystem` confined to the
`/var/log` prefix, `ro_etc` is `ReadOnlyFilesystem`, `lo` is
`LocalhostNetwork`, `mono` is `MonotonicClock`, `det` is
`DeterministicRandom`, and `child` is an independent-child `Allocator`.
The read-side counterpart `scoped_to` narrows a `ReadOnlyFilesystem` to a
prefix the same way.

> **Pending.** Three lattice edges are locked in the catalogue but not yet
> constructible through the stdlib: `alloc.bounded(cap)` (→
> `BoundedAllocator`), `exec.child()` (→ a sub-pool `Executor`), and any
> constructor for `SandboxedFilesystem` — today's scoping helpers
> (`scoped_to` / `scoped_to_w`) return prefix-scoped `ReadOnlyFilesystem` /
> `Filesystem` views rather than the distinct `SandboxedFilesystem` type.

Each derivation returns a tighter type. A narrowed value cannot be widened
back to its source — a `ReadOnlyFilesystem` never becomes a `Filesystem`
again; narrowing is one-way. The audit
story: a reviewer of any function's signature knows the maximum authority
it can exercise; widening is structurally forbidden.

### 3.3 Type-state on capabilities

Capability types carry a state index, encoded as a comptime type parameter
on the capability handle. The state transitions are visible in method
signatures.

The canonical example is file handles:

```edda
public type FileState {
    case open
    case closed
}

public spec FileHandle(comptime State: FileState) { ... }

spec FileHandle(FileState.open)
spec FileHandle(FileState.closed)

public function open_file(fs: Filesystem, path: String) -> FileHandle_open
    with {fs, err: stream.IoError}
{ ... }

public function read_chunk(h: mutable FileHandle_open, n: usize) -> [u8]
    with {err: stream.IoError}
{ ... }

public function close(h: take FileHandle_open) -> FileHandle_closed
{ ... }
```

A caller cannot pass a `FileHandle_closed` to `read_chunk`: the type does
not match. A caller cannot use the original `FileHandle_open` after
`close` because `close` consumes it via `take`. The state transition
"open → closed" appears once in the signature and is then enforced by the
mode tracker plus the type system, with no flow analysis required.

Type-state composes with linearity. Declaring `FileHandle_open` as a
`linear` type ensures every open file is closed on every code path —
forgetting to close it is a compile error.

```edda
function read_two_lines(fs: Filesystem, path: String) -> (String, String)
    with {fs, err: stream.IoError}
{
    var h = open_file(fs, path)?
    let chunk = read_chunk(mutable h, 128)?
    let _ = close(take h)
    ...
}
```

`open_file` produces a `linear FileHandle_open`; `read_chunk` leaves it
Open; `close(take h)` transitions it to Closed and discharges the linear
obligation. Forgetting the `close(take h)` call would leave a linear value un-consumed
— rejected by the mode tracker at the end of the function.

### 3.4 Capability entries in the effect row

A function that uses a capability lists it in the effect row by parameter
name. The row entry is a bare identifier matching a parameter; the row
makes the type-level statement "this function will only exercise authority
through these named parameters":

```edda
function read_config(rfs: ReadOnlyFilesystem, allocator: Allocator, path: String) -> Config
    with {rfs, allocator, err: fs.FsError, err: ParseError}
{
    let bytes = fs.read_bytes(rfs, path, allocator)?
    return parse_config(bytes)?
}
```

`fs.read_bytes` exercises both `rfs` and `allocator`; `parse_config`
exercises neither — but both are in the row because both are parameters the
function holds. (`ParseError` here is an application-local error type;
stdlib error types stay path-qualified, like `fs.FsError`.)

A function that holds a wider capability and narrows internally lists only
its held parameters in the row. The narrowed temporaries are local
bindings, not row entries:

```edda
function audit_log(fs: Filesystem, msg: String) -> () with {fs, err: stream.IoError} {
    let logs = fs.scoped_to("/var/log")
    logs.append("audit.log", msg)?
}
```

`fs` is the row entry because `fs` is the parameter held. `logs` is a
local derivation; it doesn't get its own row entry.

### 3.5 `Subprocess` — the 17th capability

`Subprocess` is the 17th locked nominal capability. It admits spawning
external processes; the motivating consumers are build drivers
(`lib/link/`, `lib/emit/` in the native compiler invoking `lld-link`,
`mold`, `llc`, `llvm-ar`), test runners, and any tool that wraps an
external command. Without it, such tools would either need ambient
process-spawn authority (rejected by Article II — *Local over global*)
or could not be written in Edda at all.

#### Narrowing methods

Two methods, each producing a strictly weaker `Subprocess`:

- `.allowing(allowlist: [String]) -> Subprocess` — restricts the set of
  executable basenames the resulting capability may spawn. Subsequent
  `.allowing(...)` calls intersect; the resulting allowlist is never
  wider than any of its predecessors.
- `.scoped_to(dir: String) -> Subprocess` — restricts the child's
  working directory to a prefix. Nested `.scoped_to` tightens;
  widening is not admitted.

The two compose: `subp.allowing(["mold"]).scoped_to("/build")` spawns
only `mold` and only with cwd inside `/build`.

#### `linear ChildHandle` typestate

`spawn` (defined in `std.os.process`) returns a `linear ChildHandle`
with two-state typestate `running → exited`. Linearity means every
spawned process must be consumed via exactly one of:

```edda
public function wait(h: take ChildHandle) -> ExitOutcome
    with {err: process.WaitError}

public function kill(h: take ChildHandle) -> ExitOutcome
    with {err: process.WaitError}

public function detach(h: take ChildHandle) -> ()
```

Losing a `ChildHandle` without consuming it is rejected by the mode
tracker (`linear_unconsumed`). This catches the orphaned-process bug
class at typecheck; no code path can leave a spawned process
unaccounted for, including panic-unwind paths (the linear-destructor
discipline in [05-concurrency-coherence.md](05-concurrency-coherence.md)
governs panic-time consumption).

### 3.6 `ChildSpec` — parent grants child its capability bundle

A child process is a separate Edda program with its own `main` and its
own parameter list. The parent assembles the child's capability set
explicitly through a `ChildSpec` builder; the child cannot see
capabilities the parent did not bundle. This is the natural extension
of *no capability synthesis* (§3.2) across the process boundary.

#### Builder

```edda
let spec = ChildSpec.of("/usr/bin/cc", ["-c", "main.c"])
    .with_stdout(take stdout_for_child)
    .with_stderr(take stderr_for_child)
    .with_fs(take ro_fs)
    .with_env(take env)
    .with_cwd("/build")
    .build()
```

Each `.with_*` method takes and returns `ChildSpec`; the handle
argument is `take`-mode. The audit story: once a parent puts `Stdout`
into a child spec, it no longer holds the handle, and the type
signature at the call site makes the transfer visible. The full
method catalogue (`with_stdin`, `with_stdout`, `with_stderr`,
`with_fs` for read-only, `with_fs_rw` for full, `with_env`,
`with_cwd`) lives in `std.os.process`.

#### The child-cannot-exceed-parent invariant

Every capability bundled into a `ChildSpec` arrives via `take` from
holdings the parent already has (or a narrower derivative produced by
§3.2 narrowing). The child therefore structurally cannot exercise
authority the parent does not hold: a parent that holds only
`ReadOnlyFilesystem` cannot bundle `Filesystem` into a child spec
because it has no `Filesystem` to bundle. The invariant is enforced
by the type system, not by runtime check.

If the child's declared `main` parameter list names a capability the
spec did not bundle, `spawn` fails at spawn time. A dedicated
`missing_capability` variant on `process.SpawnError` is locked design;
today's stdlib `SpawnError` carries `executable_not_found`,
`not_in_allowlist`, `cwd_outside_scope`, and `spawn_failed`, and the
mismatch surfaces as `spawn_failed`. (Once a wasm-component-model
linkage story matures, this check hoists to link-of-component time and
becomes static.)

### 3.7 Per-target capability availability

Not every locked capability exists on every build target. WASI
preview 1 has no process-spawn syscall, so `Subprocess` cannot be
acquired on `wasm32-wasi-preview1`. Freestanding `bare_metal` targets
have neither `Filesystem` nor `Network`. The language answers two
questions:

- **Statically**: given a target triple, which capabilities can a
  program acquire?
- **In code**: how does a cross-target library gate its dependence on
  a capability?

#### `target.supports(T: Type) -> bool` — comptime predicate

A comptime built-in in the `Type` family (see
[04-specs-comptime.md §4.3](04-specs-comptime.md)):

```edda
let has_subp = comptime target.supports(Subprocess)
```

The call returns `bool`.

> **Pending.** The `target.supports` surface is **not yet
> callable** from user code: the evaluator half is implemented (the cteval
> builtin registry, the per-`(cap, target)` query, and the
> `comptime_target_supports_non_capability` diagnostic all exist), but the
> resolver does not wire the dotted `target.` namespace, so a write of
> `target.supports(...)` currently fails with
> `import_resolution_error: unresolved module path target`. The working
> capability-availability mechanisms today are `@target_requires(T)` (below)
> for whole-function gating and `target_has("feature")` for named-feature
> gating; the `target.supports` predicate lands when the resolver wires the
> name.

`target.supports` is comptime-pure (admissible in `where` clauses,
refinement predicates, and `requires`/`ensures`) and is one of two
built-ins whose value varies across builds — `target_has` (named-
feature gating) being the other. The type argument must be one of
the locked nominal capability types (the eighteen of §3.1 plus the four
browser-target capabilities); passing a non-capability type is a compile
error (`comptime_target_supports_non_capability`).

The predicate consults the **cap-availability table**, locked per
(capability, target) pair. The table grows monotonically: new
targets and new capabilities extend it, ✗ → ✓ transitions are
admissible (as WASI preview 2 will do for `Subprocess`), and entries
do not transition ✓ → ✗.

The table is keyed by target **operating system** — it mirrors exactly the
`supports(triple, cap)` function (the locked per-`(cap, target)` table).
"Hosted" is `linux` / `windows` / `macos` / `freebsd`:

| Capability | hosted | wasi | bare_metal | browser |
|---|---|---|---|---|
| `Filesystem` / `ReadOnlyFilesystem` / `SandboxedFilesystem` | ✓ | ✓ | ✗ | ✗ |
| `Network` / `LocalhostNetwork` / `RestrictedNetwork` | ✓ | ✓ | ✗ | ✗ |
| `Clock` | ✓ | ✓ | ✗ | ✓ |
| `MonotonicClock` | ✓ | ✓ | ✗ | ✓ |
| `Random` / `DeterministicRandom` | ✓ | ✓ | ✗ | ✓ |
| `Allocator` / `BoundedAllocator` | ✓ | ✓ | ✗ | ✓ |
| `Executor` | ✓ | ✓ | ✓ | ✓ |
| `Stdin` / `Stdout` / `Stderr` | ✓ | ✓ | ✗ | ✓ |
| `Subprocess` | ✓ | ✗ | ✗ | ✗ |
| `Debugger` | ✓ | ✗ | ✗ | ✗ |
| `Dom` / `Window` / `ExtensionContent` / `ExtensionWorker` | ✗ | ✗ | ✗ | ✓ |

`Executor` is the one capability available on every target (single-threaded on
`bare_metal` / `browser`); `bare_metal` admits nothing else. The four
browser/WebExtension capabilities are the inverse: present only on `browser`.
The table grows monotonically — new targets and capabilities extend it, ✗ → ✓
transitions are admissible (e.g. WASI preview 2 is expected to add
`Subprocess`), and no entry transitions ✓ → ✗.

#### `@target_requires(T: Type)` — function-level gate

A function whose entire signature only makes sense on supporting
targets carries an attribute:

```edda
@target_requires(Subprocess)
public function link(p: Subprocess, plan: LinkPlan, allocator: Allocator) -> ExitOutcome
    with {p, allocator, err: link.LinkError, err: process.SpawnError, err: alloc.AllocError}
{ ... }
```

Compiling for a target where `target.supports(T)` is false rejects
the function declaration with the diagnostic class
`capability_not_available_on_target`:

```
error[capability_not_available_on_target]: `Subprocess` is not available on `wasm32-wasi-preview1`
  --> lib/link/src/lib.ea:42:5
   |
42 | @target_requires(Subprocess)
   |                  ^^^^^^^^^^
   = note: WASI preview 1 has no process-spawn syscall.
   = help: provide a target-conditional alternative or omit this function for this target.
```

`@target_requires(T)` is also the only form that admits naming a
target-restricted capability type in the function's parameter list.
Without the attribute, naming `Subprocess` in a parameter on an
unsupported target fails at the parameter site itself with the same
diagnostic.

#### `comptime if` — branch on cap availability

For callers with a genuine fallback when a capability is absent,
branching is provided by extending `comptime` to the `if` expression:

```edda
public function compile_and_link(plan: BuildPlan, allocator: Allocator, out: Stdout) -> ()
    with {allocator, out, err: build.BuildError, err: alloc.AllocError}
{
    let objects = compile(plan, allocator)?
    comptime if target.supports(Subprocess) {
        let subp = acquire_subprocess()
        let _ = link(subp, LinkPlan.from(objects), allocator)?
    } else {
        out.print_line("link step skipped: target lacks Subprocess")
    }
}
```

The `comptime if` branch typechecks only on targets supporting
`Subprocess` — the `link` reference inside it is
`@target_requires(Subprocess)` and is reachable only there. The `else`
fallback branch typechecks on every target.

The form is `comptime if <pred> { <true-branch> } else { <false-branch> }`.
The predicate must be comptime-decidable. The dead branch is
**elided before typecheck**: references inside it to capabilities the
target does not admit are not flagged, because that branch does not
exist for this build. Both branches' value types must join on
targets where both survive; on targets where only one survives, the
expression's type is the surviving branch's type. The `comptime if` form
itself — including dead-branch elision before comptime-eval/typecheck — is
implemented; the predicate is `target_has("feature")` today, with
`target.supports(Cap)` (used in the example above) pending resolver wiring,
as noted in §3.7's `target.supports` block.

`comptime if` is one of the **five `comptime` keyword positions**,
alongside `comptime <expr>`, `comptime { ... }`, the
`<comptime <param>>` parameter form, and `comptime for`. Its full
grammar lives in [04-specs-comptime.md §3.1](04-specs-comptime.md).

#### Which mechanism

- Whole function only makes sense on supporting target →
  `@target_requires(T)`. No fallback; on unsupported targets the
  function does not exist.
- Caller has a fallback path → `comptime if target.supports(T) { ... } else { ... }`.
- Querying availability for a refinement or `where` clause →
  `target.supports(T)` directly.

The two mechanisms compose: a function gated by `@target_requires(T)`
may internally use `comptime if target.supports(U) { ... }` for a
different capability `U`.

---

## 4. Effect rows

### 4.1 Row shape

The row is introduced by `with` and surrounded by `{ }`. Entries are
comma-separated. A pure function with no effects has the empty row, which may
be written either as `with {}` or omitted entirely — both denote the same
empty row, and the compiler accepts both forms.

```edda
function add(x: i32, y: i32) -> i32 { return x + y }

function load(fs: Filesystem, path: String) -> Bytes
    with {fs, err: stream.IoError}
{ ... }
```

`add` is pure (no `with` clause); `load` carries a capability entry and an
error entry. Two kinds of entries are admitted:

- **Capability entries** — a bare identifier matching a parameter name.
- **Pure-effect entries** — a kind keyword, optionally followed by `:` and
  a payload type.

### 4.2 Pure-effect kinds (locked)

The locked pure-effect kinds and their semantics:

| Kind | Payload | Originator | Handler |
|---|---|---|---|
| `err: T` | error value | `raise <expr>` | `handle err: T as <name> -> <recovery> { ... }` |
| `panic` | none (message routed to runtime) | `panic <expr>` | not handlable from user code |
| `yield: T` | produced value | `yield <expr>` (iterator surface still maturing) | `for x in <expr>` |
| `cancellation` | none | runtime, on scope cancel | `handle cancellation -> <cleanup> { ... }` |
| `divergence` | none | potentially-non-terminating loop | `handle divergence -> <fallback> { ... }` |
| `nondet` | none | capability methods whose result depends on runtime | no handler (erase by capability substitution) |

`panic` is unrecoverable from within user code; it always exits the program
unless the runtime is configured to catch it at the program boundary.
`nondet` does not have a handler form: to erase nondeterminism, replace
the underlying capability with a deterministic variant (e.g.
`Random.deterministic(seed)`).

### 4.3 Rows are sets

A row is a *set* of entries. The canonical form is sorted and deduplicated:
two rows `{a, b, c}` and `{c, b, a, b}` are equivalent. The parser
accepts any order; the typechecker normalises before comparison.

Two implications:

- A row never lists the same entry twice. Writing `with {err: stream.IoError, err:
  stream.IoError}` is the same row as `with {err: stream.IoError}`.
- Two error effects with the same type spelling refer to the same effect.
  Qualified names disambiguate when two error types share a simple name
  across modules (see *Qualified type names in row entries* in
  [01-syntax.md](01-syntax.md)).

### 4.4 Worked examples

```edda
function double(x: i32) -> i32 { return x + x }

function read_payload(fs: Filesystem, path: String) -> [u8] with {fs, err: fs.FsError}
{ ... }

function load_json(fs: Filesystem, path: String) -> Json
    with {fs, err: fs.FsError, err: ParseError}
{ ... }

function build_buffer(allocator: Allocator, n: usize) -> [u8]
    with {allocator, err: alloc.AllocError}
{ ... }

function commit(fs: Filesystem, allocator: Allocator, txn: take Txn) -> Receipt
    with {fs, allocator, err: fs.FsError, err: alloc.AllocError, panic}
{ ... }
```

Reading the rows top to bottom: `double` is pure and total; `read_payload`
reads the filesystem and may produce `fs.FsError`; `load_json` may produce
`fs.FsError` or an application-local `ParseError`; `build_buffer` allocates
and may produce `alloc.AllocError`; `commit` mixes everything — a capability,
multiple errors, and `panic`.

The row is the *contract*: the caller commits to passing the named
capabilities and to handling (or further propagating) the named effects.
Any callee whose row is not a subset of the caller's row (modulo `?` /
handler discharge) is a compile error at the call site.

---

## 5. Graded effects

### 5.1 Motivation

A row entry says *which* effects a function exhibits. A graded entry adds
*how much* — quantitative bounds on resource consumption, expressed as
refinement predicates over a hidden resource variable.

The motivating use case is precise resource accounting at API boundaries:
a "read at most one 4-KiB block from disk" function is *categorically*
different from a "read the whole file" function, but in plain effect-row
notation both carry `with {fs, err: stream.IoError}`. Graded effects close the
gap.

### 5.2 The locked graded kinds

Three resources are graded in V1.0:

- **`alloc(bytes <= N)`** — the body allocates at most `N` bytes through
  the held `Allocator` capabilities, summed over all paths.
- **`io(calls <= N)`** — the body makes at most `N` external I/O calls
  (filesystem, network, stdin/stdout/stderr). Counted by call site, not
  by bytes.
- **`time(ops <= N)`** — the body executes at most `N` operations.
  "Operation" is counted-step: one op per non-spec function call by
  default. Wall-clock time is not bounded by this; it's a structural
  bound on call-graph size.

The bound expression `N` must be in LIA (linear integer arithmetic) over
constants and parameters. Non-linear bounds are deferred to post-V1.0 (see
*Reserved for post-V1.0* below).

### 5.3 Worked example

```edda
function read_chunk(fs: Filesystem, path: String) -> [u8]
    with {fs, err: fs.FsError, alloc(bytes <= 4096), io(calls <= 1)}
{ ... }

function process_batch(fs: Filesystem, paths: [String]) -> usize
    with {fs, err: fs.FsError, alloc(bytes <= 4096 * paths.len()), io(calls <= paths.len())}
{
    var count: usize = 0
    for path in paths {
        let _ = read_chunk(fs, path)?
        count += 1
    }
    return count
}
```

`process_batch` declares bounds that scale linearly with `paths.len()`.
The discharge rule (below) checks that the body's actual resource use
fits within the declared bound.

### 5.4 The discharge rule

The caller's bound must cover the sum of callee bounds along every path
through the body. Three structural rules:

- **Straight-line code** — bounds add. Two sequential calls with bounds
  `alloc(bytes <= A)` and `alloc(bytes <= B)` consume up to `A + B`
  bytes.
- **Branches** — bounds take the maximum. An `if`/`match` with branches
  costing `A` and `B` consumes up to `max(A, B)`.
- **Bounded loops over slices** — the per-iteration bound lifts to
  `slice.len() * per_iter_bound`. Loops without a static iteration bound
  (`loop { ... }`) cannot satisfy a graded bound unless the body
  short-circuits with a static count.

For `process_batch` above, the loop body calls `read_chunk` once per
iteration. `read_chunk`'s bound is `alloc(bytes <= 4096)`; the loop runs
`paths.len()` times; the lifted bound is `4096 * paths.len()`. The
declared bound on `process_batch` is `4096 * paths.len()` — covers the
loop, discharge succeeds.

### 5.5 Time bounds and counted-step semantics

`time(ops <= N)` is *structural*, not wall-clock. One op is one non-spec
call. Spec invocations (which are codegen events, not runtime events)
don't count. Calls into capability methods count as one op each;
arithmetic, indexing, and field access don't count.

This bound is checked at the static call graph: the verifier walks the
body, counts non-spec call sites along each path, and discharges against
the declared bound. There is no runtime check.

The intent is "is this function bounded in work, or could it run away?"
The answer is precise enough to gate hot-path code at API boundaries
without paying for instrumentation.

### 5.6 Mixing graded and ungraded entries

Mixing a graded and an ungraded entry of the *same kind* in one row is a
parse error: `with {alloc, alloc(bytes <= 4096)}` is rejected. A row
either bounds a resource or doesn't; declaring both is contradictory.

A row may carry a graded `alloc(bytes <= N)` alongside an *ungraded*
`io` — bounded allocation, unbounded I/O. The grades are per-kind, not
per-row.

### 5.7 Discharge fragment

Graded-effect predicates are in LIA, already in the locked decidable
fragment (see *Refinement clauses* below). No new theory is required;
the existing SMT discharge handles graded bounds.

### 5.8 Diagnostic on bound exceeded

When a callee's bound exceeds the caller's, the diagnostic shows the path
and the arithmetic:

```
error[effect_graded_bound_exceeded]: graded bound exceeded
  --> src/main.ea:14:9
   |
14 |     for path in paths {
   |     ^^^^^^^^^^^^^^^^^ loop body adds up to 4096 * paths.len()
15 |         let bytes = read_chunk(fs, path)?
   |                     ----------------- alloc(bytes <= 4096)
16 |         let extra = allocator.alloc(8192)?
   |                     ------------------ alloc(bytes <= 8192)
   |
help: function declares `alloc(bytes <= 4096 * paths.len())`
help: body consumes up to `(4096 + 8192) * paths.len() == 12288 * paths.len()`
help: raise the declared bound to `alloc(bytes <= 12288 * paths.len())`, or
      reduce per-iteration allocation
```

---

## 6. `?` propagation and handlers

### 6.1 `?` is error-only

The postfix `?` propagates one and only one effect kind: `err: T`. The
operator looks at the callee's row, picks out each `err: T` entry, and
requires the enclosing function's row to contain a matching entry.

```edda
function load(rfs: ReadOnlyFilesystem, path: String, allocator: Allocator) -> Config
    with {rfs, allocator, err: fs.FsError, err: ParseError}
{
    let bytes = fs.read_bytes(rfs, path, allocator)?
    return parse_config(bytes)?
}
```

The first `?` propagates `err: fs.FsError`; the second propagates an
application-local `err: ParseError`. `?` does *not* unwrap `Option(T)` or `Outcome(T, E)`. The stdlib `Option`
type is a sum type, handled by `match`; `Outcome(T, E)` exists only as a
carrier for storage scenarios (parallel-task join, batch retry) and is
forbidden as a fallible function's return type. The single mechanism for
fallibility is the effect row.

### 6.2 Row-membership rule

The error type must be present in the enclosing function's declared row.
The match is by qualified type name; no subtyping, no implicit conversion.
A function whose body uses `expr?` where `expr` returns `err: stream.IoError` but
whose declared row does not contain `err: stream.IoError` is a compile error.

### 6.3 Handler form

```edda
let content = handle err: stream.IoError as e -> log_and_default(e) {
    read_config(fs)?
}
```

The form is `handle <kind>: <Type> as <name> -> <recovery-expr> { <body>
}`. Inside the body, errors of the named type are caught; the `as <name>`
binds the caught error value into scope for the recovery expression. The
recovery expression is evaluated only on the error path.

The handler discharges the matched effect kind from the body's row: the
expression `handle err: stream.IoError as e -> default { body }` has a row equal
to `body`'s row minus `err: stream.IoError`, plus whatever the recovery expression's
row contributes.

The body's value type and the recovery's value type must join — typically
they're the same type; alternatively the joined type is a sum.

```edda
function safe_read(rfs: ReadOnlyFilesystem, path: String, allocator: Allocator) -> String
    with {rfs, allocator, err: alloc.AllocError}
{
    return handle err: fs.FsError as e -> "<failed to read>" {
        fs.read_to_string(rfs, path, allocator)?
    }
}
```

`safe_read` has row `{rfs, allocator, err: alloc.AllocError}`: the
`err: fs.FsError` raised inside the body is caught by the handler, so it
doesn't propagate; the allocation error does.

### 6.4 Worked example — `?` chains

```edda
function pipeline(rfs: ReadOnlyFilesystem, allocator: Allocator, path: String) -> Report
    with {rfs, allocator, err: fs.FsError, err: ParseError, err: alloc.AllocError}
{
    let bytes  = fs.read_bytes(rfs, path, allocator)?
    let text   = string.from_owned_utf8(take bytes)
    let parsed = parse_report(text, allocator)?
    return parsed.summarise(allocator)?
}
```

Each `?` discharges by row-membership: `fs.read_bytes` raises
`err: fs.FsError`, `parse_report` raises both `err: ParseError` (an
application-local type) and `err: alloc.AllocError`, and `summarise` raises
`err: alloc.AllocError` — the three error kinds across the body all appear in
the function's row. `string.from_owned_utf8` is infallible, so it takes no
`?`.

### 6.5 Worked example — handler shape

```edda
function load_with_fallback(rfs: ReadOnlyFilesystem, allocator: Allocator, primary: String, fallback: String) -> Config
    with {rfs, allocator, err: fs.FsError, err: ParseError, err: alloc.AllocError}
{
    return handle err: fs.FsError as primary_err -> {
        load(rfs, fallback, allocator)?
    } {
        load(rfs, primary, allocator)?
    }
}
```

The body attempts `primary`. On `err: fs.FsError`, the handler runs and
retries with `fallback`. The retry's `?` re-enters the function's
row, so a second `fs.FsError` propagates out — the handler is not infinitely
recursive.

---

## 7. Refinement clauses

### 7.1 The four positions

Refinement predicates appear in four positions:

1. **Inline on a parameter type.** Constrains a single parameter:
   ```edda
   function at(v: Vec, i: usize where i < v.len()) -> T { ... }
   ```
2. **On a record field.** Constrains the field's value at every
   construction and mutation site:
   ```edda
   type Buffer {
       items: [u8]
       len: usize where len <= items.len()
   }
   ```
3. **Top-level `requires` clause.** Precondition over the whole signature:
   ```edda
   function clamp(value: take T, lo: take T, hi: take T) -> T
       requires lo <= hi
   { ... }
   ```
4. **Top-level `ensures` clause.** Postcondition; `result` names the return
   value:
   ```edda
   function clamp(value: take T, lo: take T, hi: take T) -> T
       requires lo <= hi
       ensures  result >= lo
       ensures  result <= hi
   { ... }
   ```

Multiple `requires` / `ensures` clauses are admitted and conjoin.

### 7.2 The predicate fragment (V1.0)

The locked decidable fragment:

- **EUF** — equality (and disequality) over arbitrary types: `x == y`,
  `x != y`.
- **LIA** — integer comparison and linear arithmetic: `<`, `<=`, `>`,
  `>=`, `+`, `-`, multiplication by a *constant*.
- **Boolean** — `&&`, `||`, `!`.
- **Arrays** — index `xs[i]`, length `xs.len()`, extensional array
  equality.
- **Bounded quantifiers** — `forall i in 0..<n: P(i)` and
  `exists i in 0..<n: P(i)`, where the iteration domain is a range or slice.
  The bounded fragment stays decidable.

Non-linear multiplication (`x * y` with both variables), bitvectors,
floating-point predicates beyond comparison, and *unbounded* quantifiers are
*deferred to post-V1.0* — see *Reserved for post-V1.0* below.

### 7.3 Worked example

```edda
public spec Clamp(comptime T: Type where T provides <=, ==) {
    public function clamp(value: take T, lo: take T, hi: take T) -> T
        requires lo <= hi
        ensures  result >= lo
        ensures  result <= hi
    {
        if value < lo { return lo }
        if value > hi { return hi }
        return value
    }
}
```

The contract:

- **Precondition** — caller must establish `lo <= hi`.
- **Postcondition** — callee guarantees the result is in `[lo, hi]`.

Both clauses are SMT-discharged at compile time. The body's three return
paths are checked against the postcondition; the precondition is assumed
on entry.

### 7.4 Built-in obligations

Every program carries refinement obligations that the language inserts
automatically, regardless of user-written clauses:

- **Integer overflow on `+`, `-`, `*`, `/`** — the default trapping
  operators carry `result fits in T's range`. Discharge by showing the
  operation cannot overflow, *or* by using an explicit-mode operator
  (`+%`, `+|`, `+?`).
- **Slice indexing `xs[i]`** — carries `i < xs.len()`.
- **Float division `a / b`** — carries `b != 0.0`.
- **Narrowing cast `value as T`** — carries `value in T's range`.

These are not optional. A compile that fails on a built-in obligation
gives a precise message naming the obligation and the unproven term.

### 7.5 `decreases` for termination

A function may carry a `decreases <expr>` clause to prove termination.
The expression must strictly decrease across every recursive call and
loop iteration, and be bounded below.

```edda
function factorial(n: u64) -> u64
    requires n <= 20
    ensures  result >= 1
    decreases n
{
    if n == 0 { return 1 }
    return n * factorial(n - 1)
}
```

Detailed termination semantics (the metric, loop integration,
mutual-recursion clusters) live in
[03-verification.md](03-verification.md).

### 7.6 Trust hatches

Two annotations bypass verification, intentionally and auditably:

- **`@unverified(reason: "...")`** on a whole function — declares the
  function's contract without proving it. The function's signature still
  participates in row composition and mode checking; only the refinement
  discharge is skipped.
- **`@trust(reason: "...")`** on a single expression — accepts an
  obligation at a specific call site that the verifier cannot discharge.

Both are listed by `edda lint --trust-points`. The reason string is
mandatory; an audit reviewer can see every trust point in the program with
one command.

---

## 8. Composition examples

### 8.1 The full signature shape

A function combining all four pieces:

```edda
function read_section(
    fs: ReadOnlyFilesystem,
    allocator: BoundedAllocator,
    path: String,
    offset: u64,
    length: usize where length <= 65536,
) -> [u8]
    with {fs, allocator, err: fs.FsError, err: alloc.AllocError,
          alloc(bytes <= length), io(calls <= 1)}
    requires offset < 18_446_744_073_709_486_079
    ensures  result.len() == length
{ ... }
```

The signature tells the caller everything:

- **Modes** — all parameters are `let`; nothing is consumed.
- **Capabilities** — `fs` (read-only filesystem) and `allocator` (bounded
  allocator) are required.
- **Effects** — `fs.FsError` and `alloc.AllocError` are the failure modes.
- **Graded effects** — at most `length` bytes allocated, at most one I/O
  call.
- **Refinements** — `length <= 65536` constrains the parameter; the
  `offset` bound keeps `offset + length` below the `u64` range so the sum
  won't overflow; the returned slice is exactly `length` bytes.

This is a complete contract. An LLM author has every piece of context
needed to call this function correctly, with no need to read the body.

### 8.2 How rows aggregate at the call site

```edda
function read_two_sections(
    fs: ReadOnlyFilesystem,
    allocator: BoundedAllocator,
    path: String,
) -> ([u8], [u8])
    with {fs, allocator, err: fs.FsError, err: alloc.AllocError,
          alloc(bytes <= 8192), io(calls <= 2)}
{
    let a = read_section(fs, allocator, path, 0, 4096)?
    let b = read_section(fs, allocator, path, 4096, 4096)?
    return (a, b)
}
```

Each `read_section` call contributes `alloc(bytes <= 4096)` and `io(calls
<= 1)`. The two calls run sequentially; bounds add: `alloc(bytes <= 8192)`,
`io(calls <= 2)`. Both `?` operators discharge against the declared row.

### 8.3 How `?` discharges

A `?` is admitted iff the callee's `err: T` matches an entry in the
caller's row. In the example above, `read_section` raises `err: stream.IoError`
and `err: alloc.AllocError`; both appear in `read_two_sections`'s row;
both propagate cleanly.

If `read_two_sections` declared only `with {fs, allocator, err: stream.IoError,
alloc(bytes <= 8192), io(calls <= 2)}` (dropping `alloc.AllocError`), the `?` on
`read_section` would be a compile error: the alloc error has nowhere to
go.

---

## 9. Mode + effect + refinement interactions

### 9.1 `mutable` parameter with `ensures` on its post-state

A function that takes a `mutable` parameter can constrain the value's
state after the call via `ensures`. The post-state name is the parameter
name; refinements may reference it like any other binding.

```edda
function clear(buf: mutable [u8]) -> ()
    ensures buf.len() == 0
{ ... }

function push_one(buf: mutable [u8], byte: u8) -> ()
    requires buf.len() < 4_294_967_296
    ensures  buf.len() == old(buf.len()) + 1
{ ... }
```

(`old(...)` is deferred to post-V1.0 — see *Reserved for post-V1.0*. In
V1.0 the `push_one` postcondition is approximated by an inline parameter
refinement.)

### 9.2 `take` parameter consumed inside a `handle` block

A `take` parameter passes ownership into the function body. If the body
contains a `handle` block, the parameter must be consumed (or escape) on
*every* path through the handler — both the success and recovery branches.

```edda
function commit_or_drop(allocator: Allocator, txn: take Txn) -> bool
    with {allocator, err: TxnError}
{
    return handle err: TxnError as _ -> {
        drop(take txn)
        false
    } {
        commit(take txn)?
        true
    }
}
```

The recovery path consumes `txn` via `drop`; the success path consumes it
via `commit`. If either branch omitted the `take txn` consumption and `Txn` were
declared `linear`, the mode tracker rejects the function.

### 9.3 Refinement-bound integer feeding a graded `alloc` bound

```edda
function build(allocator: Allocator, count: usize where count <= 1024) -> [Entry]
    with {allocator, err: alloc.AllocError,
          alloc(bytes <= 32 * count)}
{ ... }
```

The graded bound references `count`; the inline refinement bounds
`count`. The SMT discharge can prove the bound expression is non-negative
and bounded above (because `count <= 1024` => `32 * count <= 32768`), so
the bound is well-formed in LIA.

---

## 10. Stability and linear types — forward references

### 10.1 `stable function`

A `stable function` constrains both its row and its callee set. The full
discipline lives in [03-verification.md](03-verification.md). Briefly: a
stable function's row contains only `err: T`, `panic`, `alloc`, and
`yield: T` (no `nondet`, no `divergence`, no `cancellation`; ambient
`Random` is excluded, though `DeterministicRandom` is admitted —
reproducible by construction), and every function it calls is itself
stable. The intent is reproducibility — a stable function gives the same
result for the same inputs, modulo declared errors and panics.

### 10.2 `linear` / `affine` type modifiers

The `linear` and `affine` flags on a type declaration tighten the mode
tracker's exit condition: a `linear T` value must be consumed exactly
once on every path. See *Linear-flag and affine-flag types* above and
the type-declaration form in [01-syntax.md](01-syntax.md).

---

## 11. Reserved for post-V1.0

The following forms are *not admitted* in V1.0 but are held by design
intent for a post-V1.0 expansion. Listed here so authors know what to
*avoid spelling* and what to expect later:

- **Unbounded quantifiers in refinements** — `forall x: P(x)` and
  `exists x: P(x)` over an unbounded domain. The *bounded* forms
  (`forall i in 0..<n: P(i)` / `exists i in 0..<n: P(i)`) are admitted in
  V1.0; only the unbounded form stays deferred, because it is undecidable.
- **NLA sub-fragment** — multiplication and division by *non-constant*
  variables. Some sub-fragments (linear-by-cases, polynomial up to small
  degree) may admit. The boundary will be drawn at post-V1.0.
- **Bitvector theory** — for crypto / parser refinements that need
  exact-width bit reasoning. The QF_BV fragment is decidable and
  well-established in off-the-shelf solvers (Z3, CVC5); adding a bitvector
  theory solver to the native in-tree solver (see
  [03-verification.md §The V1.0 solver](03-verification.md)) alongside LIA
  is engineering.
- **`old(...)` pre-state references in `ensures`** — to express "the new
  value is the old value plus one" cleanly. V1.0 lacks this; postconditions
  on `mutable` parameters can name the parameter only post-mutation.
- **Loop invariants** — orthogonal to `decreases`. Decreases proves
  termination; invariants prove correctness of the loop body's
  cumulative effect.
- **Polynomial graded-effect bounds** — current bounds are LIA;
  polynomial allows `alloc(bytes <= n * n)` for matrix-shaped allocations.
- **Refinements on capability identity** — beyond type-state. Today the
  type carries the state; refinements over the *identity* of the
  capability (e.g., "this `Allocator` is a child of `parent`") are
  reserved.
- **Floating-point predicates beyond comparison** — IEEE-754 axioms,
  NaN propagation, rounding-mode reasoning. V1.0 admits float
  comparisons (`<`, `<=`, `==`) only.

When you find yourself wanting one of these, the answer in V1.0 is "use
`@unverified` or `@trust`, record the obligation in the annotation's
mandatory `reason:` string, and revisit when the post-V1.0 expansion
lands." The trust point will be in the audit list and can be retired when
the language admits the relevant form.

---

## See also

- [01-syntax.md](01-syntax.md) — lexical and declaration syntax,
  including the binding-form / mode interaction.
- [03-verification.md](03-verification.md) — SMT discharge, proof
  certificates, `decreases` semantics, stability.
- [04-specs-comptime.md](04-specs-comptime.md) — `spec` declarations and
  comptime constraint discharge (`where T provides <=`).
- [05-concurrency-coherence.md](05-concurrency-coherence.md) — how `scope`
  blocks compose with effect rows; cancellation-effect handlers in detail.
