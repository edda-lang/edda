# 05 — Concurrency and Coherence

## 1. Overview

Edda has two structured-execution forms. They look syntactically related but address orthogonal failure modes that LLM authors are demonstrably prone to producing.

`scope(exec)` introduces structured concurrency. Every task is owned by a lexical scope; no task outlives its parent; failure of one sibling cancels the others. The detached-task footgun — `spawn(work)` returning a handle that no one tracks, the program exiting while the task is still running, the task panicking in the dark — is removed at the type level. There is no path through the surface language by which an LLM author can write a fire-and-forget task.

`scope(coherence)` introduces observational atomicity. Inside the region, intermediate effects (mutations, allocations, partial state) are not observable from the outside; the region either commits a single coherent result or propagates a diverging effect. The half-built-data-structure footgun — an LLM author writing `index.insert(...); index.shrink_to_fit()` where a caller observes the index between the two operations and sees an internally inconsistent state — is also removed at the type level.

Both forms compose. Both interact with the capability and effect rows defined in [02-modes-effects-refinements.md](02-modes-effects-refinements.md). Both compose with type-state on capabilities and with `linear`-flagged types to produce a resource discipline that is leak-free, protocol-aware, and statically checked.

This document covers the two `scope` forms, the `cancellation` effect, the `nondet` effect, bounded coherence regions, type-state on capabilities, linear and affine types, and the interaction matrix between these mechanisms and the rest of the language.

## 2. `scope(exec)` — structured concurrency

> **Implementation status (re-audited 2026-07-10).** The design below is locked, and its core now runs: `scope(exec)` parses, type-checks, and **lowers** on both compilers, and the spawn/await path executes end-to-end in bootstrap-built binaries — task groups open and join at region entry/exit, spawned bodies run on the task pool, `.await` yields real results. Wired enforcement: region bodies type-check (wrong-arity and type-mismatch calls inside a region diagnose); the mandatory-`Executor`-in-row check fires (`executor_missing_in_row`); the `exec_scope_without_spawn` lint is live; and `group.spawn(take x = v) { … }` admits **only** `take` captures (`group.spawn(mutable x = v)` is a parse error). Two enforcement diagnostics named in §2.2–§2.5 remain **not yet wired**: the spawn-body-no-`err` check and the `await?` prohibition. Two further §2 mechanisms are likewise design-normative today: the checker types task handles transparently, so §2.2's `linear_unconsumed` discipline does not yet fire on a dropped `Task(T)`; and the `group.race` / `group.any` primitives of §2.5 have not landed, so `nondet` origination from completion-order-observable scopes is not yet checked. The native self-host's task runtime is younger than the bootstrap's — binaries it emits still misbehave on some concurrency paths, and the differential corpus tracks the gap — so treat bootstrap-built output as the runtime authority for this chapter's semantics while that closes.

### 2.1 Form

```edda
function fetch_pair(net: Network, exec: Executor, a: String, b: String) -> (Body, Body)
    with {net, exec, err: net.NetError}
{
    scope(exec) group {
        let ta = group.spawn { net.get_safe(a) }
        let tb = group.spawn { net.get_safe(b) }
        return match (ta.await, tb.await) {
            case (.ok(let ba), .ok(let bb)) => (ba, bb)
            case (.err(let e), _)           => raise e
            case (_, .err(let e))           => raise e
        }
    }
}
```

The `scope(exec)` form takes a binder (here `group`) for the scope handle and a body. The body is a normal block. Tasks are spawned by calling `group.spawn { body }`, which materialises a `linear Task(T)` handle from `std.task`, where `T` is the body's return type. Handles are consumed by `await` (returns the value), `detach` (discharges linearity, result lost), or `cancel_and_await` (signals cancellation and joins). The `Task(T)` type is `linear`, so the typechecker rejects any code path that drops a task handle without consuming it via one of these three operations.

### 2.2 Locked semantics

The following rules are locked for V1.0.

**Mandatory `Executor` capability.** The enclosing function must declare an `Executor`-typed parameter and carry its bare name in the effect row (e.g. `exec: Executor` in the parameter list, `exec` in the row) — the same capability-entry rule as every other capability (`fs: Filesystem` for filesystem operations, bare `fs` in the row). The `Executor` capability is what makes `scope(exec)` admissible. A function without `Executor` in its row cannot open an `exec` scope, and the diagnostic is `executor_missing_in_row`. Capability requirements are declared at the function boundary, not inferred or threaded implicitly.

**No detached tasks at the surface.** Every task lives inside a scope. The surface language has no syntax for spawning a task that outlives the enclosing function. Detached spawns are the canonical LLM-prone concurrency footgun (they are common in Python, JavaScript, and Rust where they appear superficially convenient), and Edda removes them at the grammar level. The `detach(t: take Task)` operation in `std.task` discharges linearity within a scope — it does not extend the task's lifetime past scope exit. An LLM author cannot write a detached spawn even if it would compile in another language they have been trained on.

**`group.spawn { body }` returns `linear Task(T)`.** `T` is the body's return type. The spec is single-parameter, and the `linear` flag sits on the inner `type`, not on the `spec` keyword (there is no `linear spec` form — `linear`/`affine` are type-declaration modifiers). The shape as it ships in `std/lib/task/src/task.ea` is:

```edda
public spec Task(comptime T: Type) {
    public linear type Task { raw: i32 }

    public function detach(t: take Task) -> ()                extern "__edda_task_detach"
    public function cancel(t: mutable Task) -> ()             extern "__edda_task_cancel"
    public function cancel_and_await(t: take Task) -> ()
        with {cancellation}                                   extern "__edda_task_cancel_and_await"
}
```

The body's outer effect row may carry capability entries and `cancellation`, but **not** `err: E`. Cross-task error transport is not modelled through the effect row — it is modelled through the value shape. A fallible body returns `Outcome(T, E)` from `std.core.outcome`; the await join pattern-matches on the value. The "outer row" qualifier matters: a body may internally `?` against `err: E` and then `handle err: E as e -> Outcome.err(e) { ... }` to lift the error into the value shape; the *outer* row of the body (what crosses the spawn boundary) carries no `err:` entries.

**`std.task` operations.** Four operations consume or signal a `Task(T)`. Three are spec member functions (`extern`-bodied, shown above); `await` is **not** a `std.task` function — it is a resolver intrinsic keyed in the bootstrap's primitive-intrinsic catalogue and invoked postfix as `t.await` (no parens), yielding the body's value of type `T`:

```edda
t.await                            -> T   with {cancellation}     (resolver intrinsic, postfix)
detach(t: take Task) -> ()                                        (std.task spec fn)
cancel(t: mutable Task) -> ()                                     (std.task spec fn)
cancel_and_await(t: take Task) -> ()  with {cancellation}         (std.task spec fn)
```

- `await` joins the task and returns its value. Row is `{cancellation}` only. (Intrinsic, postfix `t.await`; not a declared module function.)
- `detach` discharges the linear obligation; the task continues, the result is unobservable. No effect row.
- `cancel` is signal-only — takes `mutable`, leaves the handle linear. Must be followed by `await` / `detach` / `cancel_and_await` to discharge.
- `cancel_and_await` is the convenience composite: signals cancellation and joins.

Losing a `Task(T)` without one of the three consuming operations is `linear_unconsumed` — the locked discipline; per the §2 status banner, this check does not yet fire on task handles. This is the same lever as `linear ChildHandle` from `Subprocess` ([02-modes-effects-refinements.md §3.5](02-modes-effects-refinements.md)) — the resource-leak class is closed at the type level.

**Failure propagation via the value join.** If a spawned task's body returns `Outcome.err(e)`, the await yields `.err(e)` and the join's `match` decides what to do — typically `raise e`. The scope cancels remaining siblings cooperatively when a sibling's failure causes the join to `raise`. The author writes "first error wins" by ordering match arms; the language does not impose its own race-resolution policy on value-shape failures.

**Sibling cancellation.** Any task failure that causes the enclosing function to `raise` cancels its siblings cooperatively. Cancellation is an effect, not a preemptive signal. Tasks check for cancellation at every `await`, every `?`, and at scope-internal boundaries (loop iteration, block exit). A task that never reaches such a checkpoint is not cancelled — this is documented behaviour, not a defect.

**`?` does not propagate cancellation.** Per AGENTS.md's effect-row rule, `?` propagates only `err: T`. The `cancellation` entry on `await`'s row must be either handled with `handle cancellation -> cleanup-expr { ... }` or absorbed by the enclosing `scope(exec)` — there is no `await?` shortcut, and there is no second-letter operator for cancellation. This keeps the spelling-to-meaning mapping 1:1: `?` means "this err propagates"; cancellation routes through `handle` or scope absorption.

**Mutable references do not cross the spawn boundary.** A `mutable T` reference is bound to its capture frame and cannot be captured by a spawned task. Capabilities that need to be moved into a task are passed by `take` using the explicit argument form:

```edda
let ta = group.spawn(take owned = clone(shared)) {
    mutate(mutable owned)
}
```

The `take owned = clone(shared)` form gives the task its own value to consume; the surrounding scope retains `shared`. This is the only admissible way to give a task ownership of a value the parent also wants to use afterward. The pattern follows the explicit-cost authoring rule: cloning is visible at the call site.

### 2.3 Why errors-as-values across the spawn boundary

The "spawn-body outer row carries no `err:`" rule is load-bearing for the language's simplicity. The alternative — lifting the body's err row into a comptime spec parameter `E` on `Task(T, E)` — was considered and rejected. Three reasons:

1. **`err: T` is the form for synchronous call frames.** It carries the contract through the call stack and is discharged by `?` row-membership. Once a value crosses a task boundary (spawn / await), there is no longer a single call stack to carry the contract. The storage shape is what crosses the boundary, and the storage shape for fallibility is `Outcome(T, E)` — already cited by AGENTS.md as "the value-shaped success/failure carrier" for collections, channels, and task-join.
2. **Single-parameter `Task(T)` matches every other transport spec.** `Box(T)`, `Vec(T)`, `Option(T)`, `Channel(T)`, `Outcome(T, E)` (which takes a second `Type` arg, not a row). No higher-kinded container in Edda is parameterised over an `EffectRow`. Locking `Task` as single-`Type` preserves uniformity.
3. **No file-scope-spec exception needed.** `group.spawn { body }` materialises `spec std.task.Task(T)` per the body's return type. The set of distinct `Task_T` materialisations in a program is bounded by the set of distinct return types — no `(T, E)` combinatorial pressure on the cache.

The ergonomic cost is real: `(fa.await?, fb.await?)` becomes a `match (fa.await, fb.await) { ... }`. The honesty win is also real: the join site spells out which of the two failure modes (body-err vs cancellation) each arm handles, and `?` propagates only err — never the silent two-thing-one-spelling that a row-polymorphic `await?` would carry.

### 2.4 Cancellation as an effect

Cancellation is a reserved pure-effect kind with the following properties.

- The effect keyword is `cancellation`. It is locked.
- It is originated implicitly by `scope(exec)` when the enclosing scope cancels the task.
- It carries no payload. A cancellation is identified solely by its origination point (the scope that triggered it).
- It is handled with `handle cancellation -> cleanup-expr { body }`. The handler runs the cleanup expression and then re-raises cancellation upward unless the handler explicitly returns. This is the same handler form documented in [02-modes-effects-refinements.md](02-modes-effects-refinements.md). *(Implementation status, re-audited 2026-07-10: the payload-less `handle cancellation -> … { … }` / `handle divergence -> … { … }` forms **parse** on both compilers. Discharge semantics remain unimplemented: the type checker still rejects non-`err` effect labels in handler position, and the handler-frame machinery is `err`-routing-specific — there is no cancellation row-kind plumbed through lowering yet — so the example below is design-normative rather than runnable until that lands.)*
- Cancellation is cooperative. It is checked at every `await`, every `?`, and at scope boundaries (loop heads, block exits). Cancellation is not preemptive; a tight loop that does not contain a checkpoint is not cancellable.

Example: a task that holds a temporary file must clean it up if cancelled.

```edda
function process_chunk(fs: Filesystem, chunk: Chunk) -> ProcessedChunk
    with {fs, err: stream.IoError, cancellation}
{
    let tmp = fs.create_temp()?
    handle cancellation -> fs.unlink(tmp.path()) {
        let processed = process(mutable tmp, chunk)?
        return finalise(take tmp, processed)?
    }
}
```

The handler runs `fs.unlink(tmp.path())` if the task is cancelled, then propagates cancellation upward. The author writes cleanup in one place; the surrounding effect row makes the obligation visible.

`divergence` carries the parallel handler form — `handle divergence -> recovery-expr { body }` — with the same shape and discharge position as the `err: T` form, and the same implementation status as the cancellation form above.

### 2.5 `nondet` effect for parallelism

Parallel execution can introduce non-determinism into the observed return value. Edda makes this visible in the effect row via `nondet`.

A `scope(exec)` introduces `nondet` only when task-completion order is observable in the value flowing out of the scope. The canonical case is a select-style scope returning the first-completed task:

```edda
function first_response(net: Network, exec: Executor, primary: String, mirror: String) -> Body
    with {net, exec, err: net.NetError, nondet}
{
    scope(exec) group {
        let a = group.spawn { net.get_safe(primary) }
        let b = group.spawn { net.get_safe(mirror) }
        return match group.race(a, b) {
            case .ok(let body) => body
            case .err(let e)   => raise e
        }
    }
}
```

Most scopes are deterministic by construction — they spawn N tasks, await all of them, and return a tuple. The return value is determined by the inputs alone, regardless of which task completes first. Such scopes do not contribute `nondet` to the row.

A scope contributes `nondet` only if its body uses `group.race`, `group.any`, or a structurally similar primitive that returns a value depending on completion order. The compiler determines this from the body's expression tree, not from the presence of `scope(exec)` alone.

## 3. `scope(coherence)` — observational atomicity

> **Implementation status (re-audited 2026-07-10).** `scope(coherence)` is **implemented**: it parses, type-checks its region-specific obligations, lowers, and runs. The two structural checks below are enforced; their emitted diagnostic class names are flat (`coherence_mutable_refinement_invalidated`, `coherence_init_param_written`), not the dotted forms used in earlier drafts. Mutating an **outer** primitive `var` via a binary operator inside the region (`acc = acc + x`) lowers and runs correctly — no workaround needed.

### 3.1 Form

```edda
function build_index(allocator: Allocator, entries: [Entry]) -> Index
    with {allocator, err: alloc.AllocError}
{
    var index: Index = Index.empty()
    scope(coherence) build {
        for entry in entries {
            index.insert(entry.key, entry.value)?
        }
        index.shrink_to_fit()?
    }
    return index
}
```

A `scope(coherence)` region takes a binder (here `build`) and a body. Inside the body, the author can perform a sequence of operations that are conceptually part of building a single coherent value. From outside the region, the intermediate states of `index` are not observable; only the value after the region commits is observed.

### 3.2 Locked semantics

The following rules are locked for V1.0.

**Lexical region with hidden intermediate effects.** A coherence region is a lexical block. Effects fired inside the region (allocations, mutations, capability calls) are not observable outside the region until the region commits. The mode tracker treats the entire region as a single statement at the enclosing call site: any analysis that asks "what is the state of `index` at the line where the region appears?" answers with the post-region state, not any intermediate state.

**Single committed result on exit.** When the region exits normally, its committed value is the state at the closing brace. Any escaping diverging effect (`raise`, `panic`, `cancellation`) propagates and the region terminates without commit.

**Observational, not transactional.** This is a critical distinction. Edda's coherence regions provide observational atomicity, not transactional rollback. If `index.insert(...)?` raises `alloc.AllocError` partway through the loop, the partial state of `index` is what remains. The region does not undo the inserts that already happened. The semantics are: "no caller observes the partial state" — but the partial state still exists.

This decision is deliberate. Rollback requires either persistent data structures (so the pre-region snapshot is retained) or an undo log (so mutations can be reversed). Both designs are admissible but neither is locked. A future `scope(transactional)` form (see section 8) may add rollback once a primary use case forces the design decision. Coherence regions are the conservative subset that closes the half-built-data-structure footgun without committing to a rollback discipline.

**Mode tracker treats the region as a single statement.** From the perspective of code that follows the region, the only observable state change is the net effect of the region. This is what enables `scope(coherence)` to wrap a sequence of operations that the author conceptually means as one — for example, a fluent-API chain that mutates a builder across several method calls.

**`mutable` parameter re-validation at exit.** A `mutable T` parameter entering a coherence region is re-validated at region exit: its refinement predicates must hold under the values produced inside the region. If a `mutable points: [Point] where len(self) > 0` enters the region and the body's effects leave the slice empty at exit, the region rejects the commit with the diagnostic `coherence_mutable_refinement_invalidated`. The check runs at exit, not at every internal step, because internal intermediate states are not observable.

**`take` parameters consumed at entry.** A `take T` parameter is consumed when control enters the region. There is no "uncommit" of the take. Once entered, the parameter is owned by the region body. If the region diverges, the value is dropped via its destructor (if `linear`) or its drop semantics (if non-linear), as documented in section 6.

**`init` parameters not admitted.** A coherence region does not accept `init T` parameters. The initialisation-state tracker (see [02-modes-effects-refinements.md](02-modes-effects-refinements.md)) is responsible for tracking which fields of an `init` value have been written; combining that with the commit-or-diverge semantics of coherence introduces a state-tracker interaction we are holding indefinitely until a concrete use case demands it. The diagnostic is `coherence_init_param_written` — the check fires when an `init` parameter is **written inside** the region (the `Uninit → Valid` transition would otherwise be exposed as observationally atomic at the region close).

**Bindings declared inside the region do not escape.** A `let` or `var` declared inside the body is scoped to the body. Returning a value from the region is admissible; the value is the committed result. Returning a binding by reference is not — the reference would point into a region whose lifetime has ended.

**Effect row contribution.** The region's effect-row contribution is the union of all effects fired in the body, minus those discharged by handlers inside the body. This is identical to the rule for any compound block.

**Diverging effects propagate immediately.** If `raise`, `panic`, or `cancellation` fires inside the region, it propagates upward without commit. Mutations performed before the divergence remain — see the observational-not-transactional rule above. The author should write divergence-aware cleanup using `handle` or by structuring the region so that the only mutations are to local bindings until the final commit step.

### 3.3 Composition with `scope(exec)`

The two `scope` forms compose in both nesting orders.

**`scope(exec)` inside `scope(coherence)`.** Spawned tasks must complete (or cancel) before the coherence region commits — this is the same task-lifetime rule as section 2. The tasks' intermediate effects are hidden until the coherence region commits, which means an external observer sees neither the in-flight task work nor the partial state of values being built. This composition is the canonical way to build a coherent result in parallel.

```edda
spec std.collections.vec.Vec(Chunk)

function build_chunks(allocator: Allocator, exec: Executor, left: Source, right: Source) -> Vec_Chunk.Vec
    with {allocator, exec, err: alloc.AllocError}
{
    uninit chunks: Vec_Chunk.Vec
    Vec_Chunk.new(init chunks, allocator)?
    scope(coherence) assembly {
        scope(exec) group {
            let ta = group.spawn(take own = clone(left))  { build_one_safe(allocator, own) }
            let tb = group.spawn(take own = clone(right)) { build_one_safe(allocator, own) }
            let a = match ta.await { case .ok(let c) => c  case .err(let e) => raise e }
            let b = match tb.await { case .ok(let c) => c  case .err(let e) => raise e }
            Vec_Chunk.push(mutable chunks, take a, allocator)?
            Vec_Chunk.push(mutable chunks, take b, allocator)?
        }
    }
    return chunks
}
```

**`scope(coherence)` inside `scope(exec)`.** Admitted. A coherence region inside a task acts as in-task hiding: the task's own caller (which is awaiting the task) does not observe intermediate state. This composition is less common but is admitted for symmetry — there is no scenario where coherence-inside-exec is unsafe and exec-inside-coherence is safe, so both directions are allowed.

### 3.4 Diagnostic on mode re-validation failure

```edda
function trim_points(points: mutable PointBuf where points.len() > 0) -> ()
    with {err: ValidateError}
{
    scope(coherence) trim {
        drop_far_points(mutable points)
    }
}
```

If `drop_far_points` filters every element out, the post-region value violates `points.len() > 0`. The diagnostic surfaces at the `scope(coherence) trim` region. The bootstrap emits it as a single prose message plus the three structured fields every diagnostic carries (`canonical_form`, `obligation_trace`, `counterexample`):

```
error[coherence_mutable_refinement_invalidated]: mutable parameter `points` may
have been mutated inside this `scope(coherence)` region; its refinement requires
re-validation that the body does not prove. Either prove the refinement holds at
region exit (e.g. via an explicit guard that propagates on violation) or
restructure so the parameter isn't mutated inside the region.
```

The author has two locked options: validate inside the region and `raise` on violation (so the region diverges before commit), or restructure so the region's commit point is conditioned on the refinement holding.

## 4. Bounded coherence regions

### 4.1 Form

A coherence region can be combined with graded effects to produce a "resource-capped atomic action."

```edda
function compress_chunk(allocator: Allocator, data: [u8]) -> [u8]
    with {allocator, err: alloc.AllocError, alloc(bytes <= 65536)}
{
    var out: [u8] = data[..0]
    scope(coherence) compress {
        out = run_compression(allocator, data)?
        out = postprocess(allocator, out)?
    }
    return out
}
```

### 4.2 Semantics

Graded effect bounds aggregate across the region's body. The region's body contributes to the enclosing function's bound the same way a straight-line block does — the bound `alloc(bytes <= 65536)` is the sum of bytes allocated inside the region plus any bytes allocated outside the region. The coherence region does not get its own separate bound; it shares the enclosing function's bound.

The combined effect is observational atomicity (no caller sees the intermediate partial result) plus bounded execution (the region's allocations are counted against the function's cap). The author authoring `compress_chunk` is guaranteed that the function as a whole allocates no more than 64 KiB, regardless of whether the work is structured as a coherence region or a straight-line sequence.

This composition is the canonical way to write resource-disciplined builder code: bound the resource at the row level, and use the coherence region to hide the partial state from observers.

## 5. Type-state on capabilities

> **Implementation status (audited 2026-06-29 against the current Rust bootstrap).** The mechanism — a state index as a comptime spec parameter, each invocation mangling to a distinct module — works today **for primitive comptime parameters**: `spec FileHandle(comptime State: usize)` + `spec FileHandle(0)` materialises module `FileHandle_0`. The worked examples in this section use a comptime **user-enum** parameter (`comptime State: FileState`), which is **not yet accepted** — a user-defined value argument trips `parse_error … argument has kind tag 0x01`, because the `UserDefined` (0x04) comptime-argument kind is deferred (see [04-specs-comptime.md](04-specs-comptime.md) §argument kinds / D-22). Until 0x04 lands, the `FileState.open`/`FileState.closed` form below is aspirational, and the mangled module names resolve from the argument's value spelling (e.g. `FileHandle_0` for a `usize` index), not the capitalised `FileHandle_Open` shown here.

### 5.1 Form

Capabilities can carry a state index expressed as a comptime parameter on a `spec`. There are no bracketed type arguments in Edda — the state-indexed family is a `spec` over a comptime `State` parameter, and each invocation mangles to a named concrete module. A transition produces a different module type, so a function expecting the wrong state is a compile-time error, not a runtime check.

The mechanism above is what a package author reaches for to build a new state-indexed capability. Two built-in capability state machines already exist in the stdlib: `Allocator` transitions `open → closed` via `alloc.close`, and a `Network` connection transitions `dialing → connected → closing → closed` (this transition table is design-locked). Both are enforced the same way as any user-defined state-indexed spec — an operation invalid in the current state is a `typestate_violation` compile error, with no runtime check inserted.

```edda
type FileState {
    case open
    case closed
}

spec std.os.file.FileHandle(comptime State: FileState) {
    type FileHandle {
        fd: i32
        path: String
    }
}

spec std.os.file.FileHandle(FileState.open)
spec std.os.file.FileHandle(FileState.closed)

function open_file(fs: Filesystem, path: String) -> FileHandle_Open.FileHandle
    with {fs, err: stream.IoError}
{ ... }

function read(h: mutable FileHandle_Open.FileHandle, buf: mutable [u8]) -> usize
    with {err: stream.IoError}
{ ... }

function close(h: take FileHandle_Open.FileHandle) -> FileHandle_Closed.FileHandle
{ ... }
```

The state parameter is comptime-evaluated; each instantiation produces a distinct module (`FileHandle_Open`, `FileHandle_Closed`). Calling `read(h, buf)` where `h: FileHandle_Closed.FileHandle` is a type error at the call site: `FileHandle_Open.FileHandle` does not unify with `FileHandle_Closed.FileHandle`.

### 5.2 Use-before-open and use-after-close

The type system rejects both classic protocol violations.

**Use-before-open** is impossible because no constructor produces a `FileHandle_Open.FileHandle` other than `open_file` (or equivalent capability-method openers). There is no way to fabricate an open handle.

**Use-after-close** is impossible because `close` consumes the open handle via `take` and returns a closed handle. The closed handle has no `read`/`write` functions (or, equivalently, those functions require `FileHandle_Open.FileHandle` and the closed handle is `FileHandle_Closed.FileHandle`).

```edda
spec std.mem.alloc.Array(u8)

function example(fs: Filesystem, allocator: Allocator, path: String) -> ()
    with {fs, allocator, err: stream.IoError, err: alloc.AllocError}
{
    let h = open_file(fs, path)?
    var buf: [u8] = Array_u8.alloc(allocator, 64)?
    let n = read(mutable h, mutable buf)?
    let closed = close(take h)
    return ()
}
```

A follow-up `read(mutable closed, mutable buf)?` on `closed` would be a compile error: `read` expects `FileHandle_Open.FileHandle`, but `closed` is `FileHandle_Closed.FileHandle`.

### 5.3 Composition with modes and linearity

Type-state composes naturally with the existing `take` mode and with `linear` flagging. A typical file handle is declared `linear` inside the state-indexed spec:

```edda
spec std.os.file.FileHandle(comptime State: FileState) {
    linear type FileHandle {
        fd: i32
        path: String
    }
}
```

The combination produces a complete protocol:

- The handle must be consumed exactly once (linear).
- Consumption transitions state (take + state index on return).
- Functions requiring a specific state reject mismatched states at compile time.
- Cleanup is guaranteed because the linear discipline forbids dropping the handle.

### 5.4 Worked example: full file lifecycle

```edda
spec std.mem.alloc.Array(u8)
spec std.collections.vec.Vec(u8)

function read_file_contents(fs: Filesystem, allocator: Allocator, path: String) -> String
    with {fs, allocator, err: stream.IoError, err: alloc.AllocError, divergence}
{
    let h = open_file(fs, path)?
    uninit contents: Vec_u8.Vec
    Vec_u8.new(init contents, allocator)?
    handle err: stream.IoError as e -> {
        let _ = close(take h)
        raise e
    } {
        var buf: [u8] = Array_u8.alloc(allocator, 4096)?
        loop {
            let n = read(mutable h, mutable buf)?
            if n == 0 {
                break
            }
            Vec_u8.extend_from_slice(mutable contents, buf[..n], allocator)?
        }
    }
    let _ = close(take h)
    return string.from_owned_utf8(take Vec_u8.into_array(take contents, allocator))
}
```

The handler on `err: stream.IoError` closes `h` before re-raising. The `linear` discipline ensures `h` is consumed on every path: the success path calls `close(take h)` at the end; the error path runs the handler which calls `close(take h)` and re-raises. If the author omitted either close, the typechecker emits `linear_unconsumed` and the function does not compile.

## 6. Linear-flagged types

### 6.1 Form

```edda
linear type FileHandle {
    fd: i32
    path: String
}

affine type Counter {
    n: i32
}
```

A type declaration prefixed with `linear` is a linear type. A type declaration prefixed with `affine` is an affine type. Types without either prefix are normal (unrestricted) types: they may be copied, dropped, or consumed any number of times subject to their mode-system obligations.

### 6.2 Semantics

**`linear T` — exactly-once consumption.** A value of a `linear` type must be consumed exactly once on every code path: dropping it unconsumed is rejected as `linear_unconsumed`, and consuming it twice is rejected (move tracker).

**`affine T` — at-most-once consumption.** A value of an `affine` type must not be consumed more than once. Dropping is admitted. Consuming it twice is rejected (move tracker); there is no error for dropping.

> **Implementation status (re-audited 2026-07-10).** Both halves are enforced by the build authority. **Double-consume / use-after-move** is rejected — but the emitted class is the generic `typecheck_error` (message: *"binding `…` is consumed (moved out)"*) / `use_after_move`, **not** the fine-grained `linear_double_consume` / `affine_double_consume` names, which do not exist in the bootstrap diagnostic enum. **Unconsumed** (`linear_unconsumed`) is also rejected — a dropped `linear` local, an unconsumed `take` parameter, or a returned-then-dropped `linear` all fail `edda check` — but again under the generic `typecheck_error` class tag on the bootstrap, not a dedicated tag. The fine-grained `linear_unconsumed` class name is the native self-host's diagnostic (`compiler/lib/diagnostics/src/code.ea`, `compiler/lib/types/src/check/consume/walk/walk.ea` `sweep_unconsumed`); the bootstrap and native self-host now agree on *behavior* (both reject), but not yet on the emitted diagnostic *class name* for either half.

### 6.3 What "consumed" means

"Consumed" has a single, locked definition. A value is consumed if and only if one of the following holds:

- It is passed as a `take` argument to a function or method call.
- It is assigned to a `mutable` or `init` target (the assignment moves it).
- It is destructured by a pattern match that binds its fields by `take`.

Passing by `let` (the borrow mode) is not consumption. Passing by `mutable` (the borrow-mutable mode) is not consumption. Reading a field is not consumption. This means a `linear` value can be borrowed any number of times before it is consumed — the linear obligation is about the final fate of the value, not about every intermediate operation.

### 6.4 Constructors and obligations

Constructors of `linear` types return their value; the caller assumes the consumption obligation. The same applies to `affine` types — the caller assumes the at-most-once obligation, but is allowed to drop.

```edda
function open_file(fs: Filesystem, path: String) -> FileHandle
    with {fs, err: stream.IoError}
{
    let fd = fs.open(path)?
    return FileHandle { fd, path }
}
```

The caller assumes the obligation to consume the returned `FileHandle`.

### 6.5 Exception-safe destructors

> **Implementation status (audited 2026-06-29 against the current Rust bootstrap):** aspirational. The form shown below places a `function` body **inside** a `type` declaration; that does not parse today (`error[parse_error]: expected field name …`) — Edda methods are free functions whose first parameter is the receiver, and a type declaration body holds only fields (see [01-syntax.md](01-syntax.md) §Records, AGENTS.md anti-patterns). The `linear_destructor_missing_capability` class is likewise not in the diagnostic enum. Exception-safe destructor invocation is pending both the unconsumed-linear enforcement (§6.2) and a decided surface for declaring `on_drop`.

`linear` types declare a destructor that runs on `panic` and `raise` paths to discharge the consumption obligation. This is the only path on which a `linear` value can be dropped without violating the linear discipline.

```edda
linear type FileHandle {
    fd: i32
    path: String

    function on_drop(self: take FileHandle) -> ()
        with {fs: Filesystem}
    {
        let _ = fs.close(self.fd)
    }
}
```

The `on_drop` method is invoked by the runtime when control unwinds past the binding due to `panic` or `raise`. The destructor's effect row must be a subset of the function's row, which is checked at every binding site (the binding is admissible only if the enclosing function carries the destructor's required capabilities).

This rule means panic-safety and error-safety are not free in Edda: a function that opens a `linear FileHandle` must declare `fs: Filesystem` in its row to admit the destructor's effect. The diagnostic on omission is `linear_destructor_missing_capability`, which surfaces at the binding site with a fix-it suggesting the row addition.

### 6.6 Worked examples

**Mutex guard:** the guard is a `linear` type defined inside a `spec` over a comptime `T: Type`, so each instantiation mangles to a named module (`MutexGuard_i32`, `Mutex_i32`):

```edda
spec std.sync.mutex.Mutex(comptime T: Type) {
    type Mutex { inner: MutexInner_T }

    linear type MutexGuard { inner: MutexInner_T }

    function lock(m: mutable Mutex) -> MutexGuard
        with {err: PoisonError}
    { ... }

    function unlock(g: take MutexGuard) -> () { ... }
}

spec std.sync.mutex.Mutex(i32)

function with_lock(m: mutable Mutex_i32.Mutex) -> ()
    with {err: PoisonError}
{
    let g = Mutex_i32.lock(mutable m)?
    Mutex_i32.unlock(take g)
}
```

The guard must be `unlock`ed exactly once. The typechecker rejects any path that escapes without consuming `g`. The runtime destructor releases the lock on `panic` so the mutex does not stay poisoned.

**Capability token:**

```edda
linear type ApiToken {
    bearer: String
    expires_at: Instant
}

function issue(auth: Auth, user: User) -> ApiToken
    with {auth, err: AuthError}
{ ... }

function consume(token: take ApiToken) -> Session { ... }
```

A token is single-use: issuing it produces a `linear` value, and consuming it is the only way to discharge the obligation. The type system rejects code that obtains a token and then forgets it.

## 7. Interaction summary

This section enumerates every locked interaction between the mechanisms in this document and the rest of the language.

**`stable function` and `scope(coherence)`.** A stable function may contain a coherence region. The region body must itself be structurally stable: no `Stdin`, `Stdout`, `Stderr`, `Filesystem`, `Clock`, `MonotonicClock`, `Random`, or `Network` capabilities may appear in the region's effect row. This is enforced today by the general stability effect-row whitelist (see [02-modes-effects-refinements.md §7](02-modes-effects-refinements.md)): an unstable capability used in the region surfaces in the function's row and is rejected as `stability_effect` ("row contains `…`, which is not in the §7 whitelist"). There is no separate `stable.unstable_effect_in_coherence` diagnostic class — the row-whitelist check covers it.

**`stable function` and `scope(exec)`.** A stable function may NOT contain `scope(exec)`. Spawn-and-await is observable-time-dependent: even when the value returned from the scope is deterministic, the time taken to compute it depends on the scheduler. Stable functions rely on the ability to be re-run identically across compilations, which is incompatible with execution-dependent timing. This is enforced today: a stable function containing `scope(exec)` is rejected as `stability_callee` ("contains a `scope(exec)` block — spawn-and-await timing is observable …"), with `stability_effect` also flagging the required `exec` capability row entry as outside the §7 whitelist. (There is no distinct `stable.exec_scope_forbidden` class.) Authors needing stable parallelism are intended to use `std.parallel.map` — a locked stable primitive, not yet in the stdlib — which yields the same result as a sequential map but is admissible to run in parallel by the runtime if it chooses.

**`linear` types and modes.** A `linear` type passed by `let` mode (the borrow mode) is borrowed, not consumed. The caller retains the consumption obligation. This is what enables `read(h: mutable FileHandle_Open.FileHandle, ...)` to operate on a file without closing it — the function borrows the handle mutably, performs its work, and returns control. The caller continues to own the obligation and must eventually call `close(take h)`.

**Type-state and refinements.** A capability's state index is a comptime value that is visible to refinements. A function may constrain the state in a refinement clause (a bare predicate, no braces):

```edda
function read_n(h: mutable FileHandle, n: usize) -> [u8]
    with {err: stream.IoError}
    where h.state == FileState.open
{ ... }
```

The refinement is a redundant statement of what the type signature already says (the function could equivalently take `FileHandle_Open.FileHandle` in the parameter list). Refinements over state are admissible for cases where the state is derived from a comptime expression rather than spelled directly. *(Implementation status: depends on the comptime user-enum state parameter, which is deferred — see the §5 banner.)*

**Cancellation and coherence.** A cancellation propagated into a coherence region terminates the region. There is no rollback — partial mutations made before the cancellation point remain. The `handle cancellation -> cleanup` form inside the region runs the cleanup before propagation. *(Implementation status: the `handle cancellation` form parses — see §2.4 — and `scope(exec)` lowering is in, but this interaction is reachable only once real cancellation-handler discharge semantics land.)* The author is responsible for writing cleanup that leaves the partial state in a safe shape; the language guarantees no observer sees the cleanup itself (the region is still hidden from observers), but the post-region state is the partial state at the cancellation point.

## 8. Reserved for post-V1.0 / indefinite

The following are deliberately not locked and are held for a post-V1.0 revision.

**`scope(transactional)` — coherence regions with rollback.** A future form that adds undo semantics on divergence. This requires either persistent data structures (so the pre-region snapshot is retained for restore) or an undo log (so mutations can be replayed in reverse). Both designs are admissible. Locking this form is held until a primary use case forces the choice. Authors needing rollback today can build it explicitly with snapshot-and-restore patterns.

**Per-task max-of-resource bound in `scope(exec)` for graded effects.** The current rule is that graded effects in a `scope(exec)` sum across tasks: if each of N tasks may allocate up to K bytes, the scope contributes `alloc(bytes <= N * K)` to the enclosing function. This is conservative (correct in the worst case, possibly overestimating in practice). A future refinement could express "max of K across tasks executing in parallel" with a `max` form on graded effects. The sum-form is always correct and is locked; the max-form is not yet locked.

**Wall-clock time bounds.** A `time(seconds <= N)` form is out of scope. Wall-clock time depends on the host and is not statically verifiable. The counted-step form `time(ops <= N)` (where `ops` is a comptime-counted abstract step) is the locked time-bounding mechanism for stable code.

**`init` parameters into coherence regions.** As noted in section 3, the initialisation-state tracker's interaction with the region's commit-or-diverge semantics is held indefinitely. The conservative position is to forbid `init` in coherence regions; a future revision may add admissibility once a concrete use case is presented.

These deferrals are listed here so an LLM author who reasons about the language will not assume they exist. If a feature is not listed in sections 1–7, it is either locked-and-described there or reserved-and-listed here. There is no third category.
