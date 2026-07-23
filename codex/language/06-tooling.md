# 06 — Tooling

## Article VIII: The compiler IS the tooling

Articles I through VII established what the language *is*. Article VIII is the harvest. Because Edda is concrete, local, inspectable, verified, effect-typed, linear, and comptime-first, the compiler can natively serve everything the LLM author and the IDE need — typed queries, structural edits, diagnostics with counterexamples, structural indices, contract diffs, typed completion, goal-directed synthesis — through a single typed query API. No external tooling is necessary. No annotation scrapers, no doc generators, no AST-walking linters that re-derive what the typechecker already knows. The compiler computes these facts to do its job; the daemon serves them.

This is the consequence Articles I–VII were paying for. The earlier articles invested verbosity, redundancy, locality, and inspectability in the source surface. Article VIII collects the dividend: the model author and the IDE talk to the same long-lived process, through the same typed protocol, and that process is the compiler itself.

The CLI binary is not the compiler. The CLI is one client of the compiler-as-service. The IDE (via LSP) is another client. The LLM author (via MCP) is a third. All three speak to a single long-lived daemon over a typed protocol, and the daemon is the only thing that ever parses Edda source, typechecks it, runs the SMT discharge, materializes specs, or applies edits.

This document specifies the V1.0 lock for that protocol surface: daemon architecture, MCP wire format, LSP mapping, structural edit grammar, compiler-emitted structmap, diagnostics format, and the bidirectional synthesis surface.

---

## 1. The daemon (compiler-as-service)

> **Implementation status.** The bootstrap's `edda-daemon` crate (Wave
> 1) is today a synchronous in-process library, not yet a standalone
> multi-transport server. It uses `parking_lot::RwLock` for its state
> guard — that dependency is real — but has **no `tokio` anywhere in
> the bootstrap workspace** (not even at the transport edge) and **no
> `crossbeam` dependency in `edda-daemon` itself** (`crossbeam-channel`
> is a dependency of `edda-lsp`, for its own stdio server loop, not the
> daemon's internal fan-out). There is no PID file, no `--transport`
> flag, and no `stdio`/`pipe`/`socket`/`tcp` listener implemented yet;
> the 1.0s/200ms figures below are unmeasured target budgets, not
> current benchmarks. The architecture and lifecycle described in
> §1.1–§1.3 are the locked V1.0 design, not the current build.

### 1.1 Architecture

The Edda daemon is a long-lived process. It holds the parsed AST, the elaborated MIR, the type environment, the refinement obligation cache, the spec materialization cache, and the structural index — all in memory, all live, all keyed by content hash.

The core is synchronous. The daemon uses `parking_lot` for mutual exclusion, a thread pool for per-pass parallelism, and `crossbeam` channels for fan-out. Tokio appears only at the transport edge — the LSP stdio adapter, the MCP transport, the named-pipe listener — never in the daemon core itself.

This is a deliberate choice. The compiler's work is CPU-bound, sequential within a pass, and order-sensitive across passes. Async non-determinism in the core would make incremental rebuilds unreproducible. The sync core guarantees that a given (project state, query) pair always produces the same answer, byte-identical, across runs.

The daemon manages one `Driver` per active project. A `Driver` owns:

- The project's `package.toml` and resolved workspace graph.
- The in-memory document overlay (unsaved buffers from the IDE).
- The filesystem watcher that invalidates entries when on-disk files change.
- The pass cache: parse → resolve → elaborate → typecheck → refine → codegen, each keyed by content hash.
- The structural index — the compiler-emitted structmap, kept live.

Multiple projects can be open simultaneously — the locked design. Wave 1 of the bootstrap implements a single-project daemon (`Daemon` holds `Option<ProjectState>`, not a map); multi-project hosting (`HashMap<ProjectId, ProjectState>`) is deferred to a later wave. Clients select which project a request applies to via `client.open_project`.

### 1.2 Lifecycle

```
edda daemon [--transport stdio|pipe|socket|tcp] [--listen <addr>]
```

The default transport is `stdio` (for LSP integration). Named pipe and Unix domain socket are for local multi-client (one daemon, multiple IDE windows or shell sessions). TCP is for remote scenarios (containerized dev environments, devcontainer, codespaces); V1.0 binds loopback only by default.

The daemon writes a PID file under `${XDG_RUNTIME_DIR}/edda/<project-hash>.pid` (or the platform equivalent) when started in non-stdio mode. The CLI binary checks for this file before forking a new daemon; if a daemon for the project is already running, the CLI connects to it instead of starting a duplicate.

**Cold-start budget.** The daemon must be ready to serve queries within 1.0s on a project of up to 50k LOC, cold cache. Warm restarts (cache present under `.edda/cache/index/`) target 200ms.

### 1.3 Concurrency model

The daemon's request loop is single-threaded: requests arrive on a crossbeam channel, are routed to a per-namespace handler, and either complete synchronously (cheap queries — hover, completion seed) or are dispatched to the worker pool (typecheck, full build, synthesis search).

Worker results return on a reply channel. The request loop reassembles them into protocol responses. There is no `async` in this loop; the `tokio` layer outside the daemon serializes responses back to the transport.

The filesystem watcher runs on a single dedicated thread. When a file changes, it sends an invalidation message; the request loop processes it before serving the next query. Watcher-driven invalidations are coalesced — multiple changes to the same file within a 50ms window collapse into one.

See [05-concurrency-coherence.md](05-concurrency-coherence.md) for the broader concurrency model; the daemon obeys the same rules as user code.

---

## 2. MCP — Model Context Protocol

### 2.1 Wire format

The MCP transport carries JSON-RPC 2.0 framed messages. Each request is:

```json
{
  "jsonrpc": "2.0",
  "id": <integer>,
  "method": "<namespace>.<operation>",
  "params": { ... }
}
```

Responses carry either `result` or `error`. Errors carry an integer code (mapped from a locked class catalogue) and a structured `data` field.

The transport itself is locked at JSON-RPC 2.0 for V1.0. Binary framing (CBOR, MessagePack) is reserved for post-V1.0 once we have measurements that justify it.

### 2.2 Namespaces

Eight namespaces are locked for V1.0 — the bootstrap daemon's method catalogue, reconciled against the implementation as the canonical wire surface. The method name within each namespace is locked; agents and IDEs that depend on these names will continue to work across all V1.x compilers. A locked name does not imply a wired body — several leaves still return `method_not_implemented` in the current build; that is noted per namespace below.

**`client.*` — handshake and lifecycle.**

- `client.handshake(version, capabilities) -> server_capabilities` — first request on every session; negotiates protocol version and features.
- `client.cancel(request_id)` — notification cancelling an in-flight request; not a request itself.
- `client.server_info() -> server_info` — static server name/version/namespace list; no open project required.
- `client.open_project(root_path) -> project_id`
- `client.close_project(project_id)`
- `client.open_document(project_id, uri, text, version) -> doc_id`
- `client.apply_change(doc_id, edits, version)` — text-level overlay update (LSP-shaped).
- `client.close_document(doc_id)`

**`build.*` — build/run/test verbs.** 1:1 with `edda-driver`'s `Command` and the CLI's `Verb` catalogue (§8) — note the CLI's `edda check`/`edda build` map onto `build.typecheck`/`build.compile`, not `build.check`/`build.build`.

- `build.compile(project_id, target?) -> build_report` — `edda build` equivalent.
- `build.typecheck(project_id, target?) -> build_report` — `edda check` equivalent; stops after typecheck.
- `build.run(project_id, entry, args) -> run_handle` — `edda run` equivalent.
- `build.test(project_id, filter?, with_properties?) -> test_report` — `edda test` equivalent.
- `build.bench(project_id, filter?) -> bench_report` — `edda bench` equivalent.
- `build.format(project_id) -> format_report` — `edda fmt` equivalent.
- `build.lint(project_id) -> lint_report` — `edda lint` equivalent.
- `build.clean(project_id)` — `edda clean` equivalent.

Every `build.*` leaf is `method_not_implemented` in the current build — `edda-driver` does not yet expose a "run this verb against an already-open project" entry point distinct from the `client.open_project` cascade.

**`codegen.*` — artifact tier and cache management.**

- `codegen.promote(materialized_qualified_name)` — move an artifact from cache tier to repo tier.
- `codegen.demote(materialized_qualified_name)` — move an artifact from repo tier to cache tier.
- `codegen.regenerate(materialized_qualified_name)` — force-regenerate an artifact (single name or wildcard).
- `codegen.gc(tier?)` — garbage-collect by tier.
- `codegen.full_hash(short_name) -> hash` — resolve a short artifact name to the full 64-character content hash.

**`inspect.*` — structural queries.** 17 leaves. Only `inspect.parsed_ast` and `inspect.diagnostics` route end-to-end through the daemon in the current build; the rest return `method_not_implemented` until the daemon's persistent artifact index lands.

- `inspect.parsed_ast(file) -> {available, top_level_items?}` — overlay-aware parsed-AST availability for a file.
- `inspect.diagnostics(file) -> {diagnostics}` — diagnostics whose primary span points at a file.
- `inspect.artifact_of_invocation(...)`
- `inspect.artifact_of_name(...)`
- `inspect.artifact_of_spec_body_item(...)`
- `inspect.source_of_artifact(...)`
- `inspect.source_of_artifact_item(...)`
- `inspect.invocation_sites_of_artifact(...)`
- `inspect.nested_deps(...)`
- `inspect.transitive_deps(...)`
- `inspect.direct_consumers(...)`
- `inspect.transitive_consumers(...)`
- `inspect.live_artifacts(...)` — streamable, rides `stream.chunk`.
- `inspect.stale_artifacts(...)` — streamable, rides `stream.chunk`.
- `inspect.gc_eligible_artifacts(...)`
- `inspect.body_diff(...)`
- `inspect.cascade_from_edit(...)`

**`edit.*` — structural edits.** Transaction-based, not the bare per-field operations an earlier draft of this section described: every mutation is issued as (or wrapped in) `edit.transaction`. `method_not_implemented` in the current build — `edda-daemon` does not yet expose the structural-edit surface.

- `edit.transaction(operations) -> transaction_result` — all-or-nothing multi-edit transaction.
- `edit.declaration.rename(...)`
- `edit.signature.parameter.add(...)` / `edit.signature.parameter.remove(...)`
- `edit.signature.return_type.set(...)`
- `edit.effect_row.add(...)` / `edit.effect_row.remove(...)`
- `edit.refactor.rename_with_cascade(...)`
- `edit.refactor.extract_function(...)`
- `edit.refactor.inline_function(...)`

The contract edits (`signature.requires.add` / `signature.requires.remove`, `signature.ensures.add` / `signature.ensures.remove`, `signature.decreases.set`) are operation kinds from the §4.2 grammar, carried inside an `edit.transaction`'s operation list — they are not standalone wire methods and carry no method constant of their own.

**`typecheck.*` — refinement and inference query surface.** `method_not_implemented` in the current build — the daemon's query layer does not yet expose typed information by position.

- `typecheck.type_at(file, position) -> type_expr`
- `typecheck.mode_at(file, position) -> mode`
- `typecheck.effect_row_at(file, position) -> effect_row`
- `typecheck.refinement_obligations_at(file, position) -> [obligation]`
- `typecheck.trust_points_in_scope(file, position) -> [trust_point]`
- `typecheck.comptime_pure_status(file, position) -> bool`
- `typecheck.discharged_refinements(file) -> [obligation]`

**`layout.*` — comptime layout queries.** `method_not_implemented` in the current build — `edda-comptime`'s `Layout::of_ty` is reachable through `edda-types` but not yet through the daemon's query layer.

- `layout.size_of(type_expr) -> bytes`
- `layout.align_of(type_expr) -> bytes`
- `layout.offset_of(type_expr, field_path) -> bytes`
- `layout.attributes_of(decl) -> [attribute]`
- `layout.repr_of(type_expr) -> repr_kind`
- `layout.field_layout(type_expr) -> [field_layout]`
- `layout.abi_of(function) -> abi_convention`

These mirror the comptime operators of the same names (see [04-specs-comptime.md](04-specs-comptime.md)) and are how external tooling — debuggers, hex inspectors, profilers — query Edda layout without re-implementing the layout algorithm.

**`stream.*` — the eighth namespace: chunked-response notifications.**

- `stream.chunk(request_id, chunk)` — server → client notification carrying one chunk of a streaming response (e.g. `inspect.live_artifacts`, `inspect.stale_artifacts`).

> **Reconciled.** §3.1's LSP table, §5.5, §7, and `03-verification.md`'s contract-diff section each named methods absent from the catalogue above (`inspect.structmap_for_directory`/`structmap_diff`, `inspect.binding_at`, `inspect.completions_at`, `inspect.synthesize`) or a fictional `inspect.contract_diff`. Per-site implementation-status notes now mark each as a still-roadmapped, unlocked extension to `inspect.*` — proposed shape only, no stub constant, not part of the 8-namespace/63-method wire surface above. `edda contract-diff`'s actual behavior is documented accurately at [08-packages.md](08-packages.md) §8.5; `03-verification.md` §8 now defers to it.

### 2.3 Error class catalogue

JSON-RPC integer codes 1000–1999 are reserved for Edda. The mapping is locked:

| Code | Class |
|------|-------|
| 1001 | `protocol_violation` |
| 1002 | `unknown_method` |
| 1003 | `invalid_params` |
| 1100 | `project_not_open` |
| 1101 | `document_not_open` |
| 1102 | `document_version_mismatch` |
| 1200 | `build_failed` |
| 1201 | `typecheck_failed` |
| 1202 | `refinement_unproven` |
| 1300 | `edit_rejected` |
| 1301 | `generated_artifact_immutable` |
| 1302 | `edit_target_not_found` |
| 1303 | `edit_would_violate_invariant` |
| 1400 | `synthesis_no_candidates` |
| 1401 | `synthesis_timeout` |

Standard JSON-RPC codes (-32700 through -32603) retain their JSON-RPC meanings.

The `class` string field on the error object remains the canonical identifier — class-aware clients dispatch on it, and it names the precise error (e.g. `"no_project_open"`, `"cascade_failed"`, `"method_not_implemented"`). The integer code above is the compat shim, now emitted by the bootstrap implementation. Because the daemon's internal error-class catalogue is finer-grained than this 15-entry table (dozens of diagnostic-projected classes covering parse/typecheck/refinement/lint outcomes), each internal class buckets onto the locked code for its family — e.g. every typecheck-phase diagnostic class carries `1201 typecheck_failed` regardless of which specific diagnostic fired. A class with no clear family (e.g. an internal daemon-init failure) falls back to the standard JSON-RPC `-32000` server-error code rather than a misleading 1000-series guess.

### 2.4 Worked session

A canonical agent session for "add a precondition to `f` and verify":

```
→ client.handshake({version: "0.1", capabilities: ["mcp/0.1"]})
← {result: {server_version: "0.1.0", capabilities: [...]}}

→ client.open_project({root: "/repo/myproj"})
← {result: {project_id: "p1"}}

→ client.open_document({project_id: "p1", uri: "file:///repo/myproj/src/lib.ea", text: "...", version: 1})
← {result: {doc_id: "d1"}}

→ build.typecheck({project_id: "p1"})
← {result: {ok: true, diagnostics: []}}

→ edit.transaction({
    project_id: "p1",
    operations: [{
      kind: "signature.requires.add",
      target: {qualified_name: "myproj.geom.midpoint"},
      args: {predicate: "lo <= hi"}
    }]
  })
← {result: {ok: true, applied: {file: "...", edit_id: "e1"}}}

→ build.typecheck({project_id: "p1"})
← {result: {ok: false, diagnostics: [{class: "refinement_unproven", ...}]}}

→ inspect.diagnostics({project_id: "p1", file: "src/lib.ea"})
← {result: [<diagnostic with counterexample lo=5, hi=3>]}
```

Note that `build.typecheck` and the structural edit are *both* served by the daemon, against the same in-memory state. There is no file-system round-trip between them.

---

## 3. LSP — Language Server Protocol

### 3.1 Layered over the daemon

`edda-lsp` is a thin stdio adapter that wraps the daemon. It speaks LSP to the IDE on stdin/stdout; conceptually every LSP method maps to one or more MCP calls, so no LSP method does work that the daemon does not also do for non-LSP clients. **Implementation status:** today `edda-lsp` holds an in-process `edda_daemon::Daemon` handle and calls it directly (`LspState` wraps a `Daemon` value) — there is no MCP/JSON-RPC round-trip or separate pipe between the two in the current build. Routing LSP through the same wire-level MCP calls a remote agent would use is the locked V1.0 design, not the present architecture.

Locked LSP request mappings for V1.0:

| LSP method | MCP operation |
|------------|---------------|
| `initialize` | `client.handshake` + capability negotiation |
| `textDocument/didOpen` | `client.open_document` |
| `textDocument/didChange` | `client.apply_change` |
| `textDocument/didClose` | `client.close_document` |
| `textDocument/publishDiagnostics` | server-push after every overlay transition |
| `textDocument/semanticTokens/full` | custom Edda token legend (see §3.3) |
| `textDocument/completion` | `inspect.completions_at` |
| `textDocument/hover` | `inspect.binding_at` |
| `textDocument/codeAction` | `edit.*` catalogue, filtered by cursor context |
| `textDocument/definition` | `inspect.binding_at` → declaration site |
| `textDocument/references` | structural index lookup via `inspect.structmap_for_directory` |
| `workspace/symbol` | structmap-driven query |

**Implementation status.** `inspect.completions_at`, `inspect.binding_at`, and the structmap-service query backing `references`/`workspace/symbol` are not in the §2.2 locked catalogue — no stub constant exists for any of them today. They are proposed shapes for a still-roadmapped extension to `inspect.*`; until that lands, `textDocument/completion`, `hover`, `definition`, `references`, and `workspace/symbol` have no MCP backing.

V1.0 supports a single LSP client per daemon project. Multi-client (multiple IDE windows on the same project, Live-Share style co-authoring) is reserved for post-V1.0.

### 3.2 Position encoding

LSP's default position encoding is UTF-16, inherited from JavaScript. Edda spans are byte-based UTF-8. The LSP adapter negotiates UTF-8 position encoding at `initialize` time using the LSP 3.17 `positionEncodings` capability. If the client does not support UTF-8, the adapter falls back to UTF-16 with on-the-fly conversion at the protocol edge.

The daemon's MCP surface always uses UTF-8 byte offsets. Tooling that targets the daemon directly (non-LSP clients, agents) sees a single canonical encoding.

### 3.3 Semantic token legend

The Edda semantic token legend extends the LSP standard token types with Edda-specific types:

**Token types (locked for V1.0):**

- Standard: `function`, `type`, `variable`, `parameter`, `property`, `enumMember`, `keyword`, `comment`, `string`, `number`, `operator`
- Edda-specific: `capability`, `effect`, `spec`, `refinement`, `comptime`

**Token modifiers (locked for V1.0):**

- Standard: `declaration`, `readonly`, `static`, `deprecated`
- Edda-specific: `stable`, `unstable`, `linear`, `affine`, `mutable`, `take`

The V1.0 modifier list is deliberately short. Custom modifiers for capability narrowing scopes, refinement-bound bindings, and comptime evaluation contexts are reserved for post-V1.0 once we have IDE experience guiding which visual distinctions matter.

---

## 4. Structural edits

**Implementation status:** the `edit.*` namespace this section specifies is `method_not_implemented` in the current bootstrap build — `edda-daemon` does not yet expose the structural-edit surface (see §2.2). Everything below is the locked V1.0 grammar and operation catalogue, not a description of working code.

### 4.1 Grammar

Every structural edit has the shape:

```
edit ::= (kind, target, args, options)
```

- **kind** — operation namespace path (e.g. `signature.parameter.add`).
- **target** — structured path identifying the affected item. Paths are sequences of `(container, selector)` pairs starting at the module root: `(module "geom", item "midpoint", parameter "lo")`. Targets are stable across edits to surrounding code; they identify items by qualified name, not by file/line.
- **args** — operation-specific payload (e.g. for `parameter.add`: name, type, mode, default).
- **options** — cross-cutting flags (atomic, dry-run, format-after).

Edits are pure functions of (source tree, edit spec, build target). They are deterministic, side-effect-free at the spec level, and observable only through the resulting source tree. The daemon applies them as in-memory transactions: the edit either succeeds and the new tree is committed, or it fails and no change is observable.

### 4.2 Locked operation namespaces

**`declaration.*`** — top-level item operations.

- `declaration.add(target_module, decl_kind, name, args)` — add a function, type, spec, or constant.
- `declaration.remove(target)` — remove the item; fails if there are live references.
- `declaration.rename(target, new_name)` — rename and update all references in the project.

**`signature.parameter.*`** — function signature edits.

- `signature.parameter.add(function_target, name, type, mode, position?, default?)`
- `signature.parameter.remove(function_target, parameter_name)`
- `signature.parameter.reorder(function_target, new_order)`

**`signature.effect.*`** — effect row edits.

- `signature.effect.add(function_target, capability_or_effect)`
- `signature.effect.remove(function_target, capability_or_effect)`

**`signature.return.*`** — return type changes.

- `signature.return.change(function_target, new_type)`

**`signature.requires.*` / `signature.ensures.*` / `signature.decreases.*`** — contract edits.

- `signature.requires.add(function_target, predicate)`
- `signature.requires.remove(function_target, predicate_id)`
- `signature.ensures.add(function_target, predicate)`
- `signature.ensures.remove(function_target, predicate_id)`
- `signature.decreases.set(function_target, measure_expression)`

**`type.*`** — type declaration edits.

- `type.field.add(type_target, name, field_type, position?)`
- `type.field.remove(type_target, field_name)`
- `type.field.rename(type_target, field_name, new_name)` — propagates to all use sites.
- `type.variant.add(type_target, variant_name, payload_type?)`
- `type.variant.remove(type_target, variant_name)`

**`body.*`** — expression-level body edits.

- `body.replace_at(function_target, path, new_expression)` — path is a structured walk into the AST.

### 4.3 Generated artifacts are immutable

Spec materializations (see [04-specs-comptime.md](04-specs-comptime.md)) live under `codegen/` with mangled qualified names. Structural edits whose target resolves to a generated artifact are rejected with `generated_artifact_immutable`. The error response includes:

- The generating spec invocation (qualified name + arguments).
- The source location of the invocation.
- A redirect suggestion: "edit the spec source, then re-materialize".

This is enforced both at edit-application time and at filesystem-watcher time — if a generated file is hand-edited on disk, the daemon flags it as a build error and refuses to load the stale artifact.

### 4.4 Worked examples

**Adding an effect to a function row.**

```
edit.signature.effect.add({
  target: {qualified_name: "myproj.io.write_log"},
  capability: "Filesystem"
})
```

The daemon: locates `write_log`, parses its current effect row, computes the new row with `Filesystem` added in canonical order, re-typechecks the function and all callers, and either commits or rolls back atomically.

**Renaming a struct field.**

```
edit.type.field.rename({
  target: {qualified_name: "myproj.geom.Point"},
  field_name: "x_coord",
  new_name: "x"
})
```

The daemon: locates `Point`, walks the project structmap for all field-access sites, renames the field declaration, rewrites every `.x_coord` to `.x` in the same atomic transaction. If any rewrite fails (e.g. shadowed by a local `x`), the entire edit rolls back.

**Adding a `take` parameter.**

```
edit.signature.parameter.add({
  target: {qualified_name: "myproj.alloc.dispose"},
  name: "buffer",
  type: "Buffer",
  mode: "take",
  position: 0
})
```

The daemon adds the parameter, re-elaborates the function body, and surfaces any linearity violations as diagnostics in the normal way.

---

## 5. Compiler-emitted structmap

This is the load-bearing addition. The structural index that every other language's bootstrap relies on a side-band tool to maintain — Edda emits it from the compiler.

### 5.1 What it is

For every directory containing Edda source files, the compiler writes an `index.toon` file. The format is TOON (token-oriented object notation).

The emitted filename is `index.toon`; schema v3 renamed it from an earlier internal convention (see the schema history in §5.2).

Generation triggers:

- `edda structmap` CLI verb — explicit regeneration of the entire project's structmaps.
- As a side-effect of `edda build` and `edda check`, controlled by `[build] emit_structmap = true | false` in `package.toml` (default: `true`).
- Live in the daemon — `inspect.structmap_for_directory` always returns the up-to-date in-memory structmap, regardless of whether on-disk files have been refreshed.

### 5.2 Content

Each `index.toon` contains:

**Header.** The root `index.toon` carries a slim three-field header; every non-root file carries a single `loc: <rel>` line (its path relative to the package root) and no other header.
- `project` — project name from `package.toml` (root only).
- `compiler_version` — full version string of the emitting compiler (root only).
- `schema_version` — TOON schema version (`8` for V1.0; root only). History: `2`→`3` moved the emitted filename from `STRUCTURE.toon` to `index.toon` and locked the density-guidance fields in §5.6; `3`→`4` removed the doc-comment importance rows with the comment surface itself; `4`→`6` tracked intervening emitter column changes — including dropping the per-file-churning `generated_at` timestamp; `6`→`7` removed the `deferred[]` rows with the atomic-defer change; `7`→`8` added the `end` span column to `functions[]`/`types[]` and normalized the `line` start over leading attributes.

There is no `generated_at` field — it was retired at schema v6 because a per-file timestamp churns the emit on every build and defeats content-addressed reuse.

**`children[]`** — subdirectories that themselves contain Edda source, each with the item count below them. The root `index.toon` is a project-wide index that links downward; every non-root file carries its `loc:` line so subtree readers resolve their position. Per-package `children[]` rows carry each child's **own** `(types, functions)` counts (not a subtree rollup), so a subdirectory that contains only further subdirectories lists as `0,0` — a deliberate "own-counts" schema decision (see §5.6). The workspace aggregator's `children[]` rows instead carry rolled-up member totals.

**`modules[]`** — modules declared in this directory. Each entry: name, file, line, visibility.

**`types[]`** — type declarations. Each entry: name, kind (`struct`/`enum`/`alias`/`spec`), file, `line`, `end`, visibility, stability marker, `generics` (the comptime parameters of a `spec`), fields or variants (with their types and any per-field stability), attached refinements (`where` clauses). `line` is the item's first source line *including* any leading attribute lines; `end` is the closing `}` of the field/variant block, inclusive — so `[line, end]` is a self-contained read of the whole declaration (valuable for wide enums/structs).

**`effects[]`** — the per-file effect-row legend: `{id, row}`. The distinct effect-row texts among the directory's functions are deduplicated into this table and assigned ids in sorted-text order; `functions[]` then references a row by id (its `eff` / `cone` columns) instead of repeating the row text on every line. This is what keeps signature-dense directories from paying the effect-row text cost once per function. The legend is built from all functions and emitted only when there is at least one non-empty row (schema v7's adaptive emission — empty section tables are never written).

**`functions[]`** — function declarations. Each entry: qualified name, file, `line`, `end`, visibility, stability marker, `sig` (the full signature — parameters with modes, return type, and the `requires` / `ensures` / `decreases` contract clauses), `eff` (the declared effect row, as an id into `effects[]`), `cone` (the effect cone — the union of effects reachable transitively — as an id into `effects[]`, emitted only when it is not set-equal to the declared row), and `calls` (which functions in the project this one calls, by qualified name). `line` is the item's first source line *including* any leading attribute lines (e.g. `@trust(...)`); `end` is the closing-brace line of the body, inclusive — so `[line, end]` covers attributes, signature, contract clauses, and body as one bounded read.

**`invariants[]`** — refinement predicates attached to items in this directory. Derived directly from `where`/`requires`/`ensures` clauses, *not* from comment annotations.

**`patterns[]`** — items that are spec invocations or materializations. Derived directly from spec call sites, *not* from `@pattern` comments. The pattern name is the qualified name of the spec.

**`trust_points[]`** — `@unverified` and `@trust` annotations in this directory; an auditable list of every place the verifier was told "take my word for it".

### 5.3 Why this lives in the compiler

Other languages need external structmap tools because their source syntax does not carry the structural facts inline. A C++ function signature does not declare its effects; a Python function does not declare its preconditions; a Rust function does not declare which capabilities it consumes. To build an index of these facts, you must scrape comments (`@invariant`, `@pattern`, `@stable`) and hope the discipline holds.

Edda's syntax carries every fact the structmap needs:

- Effects — declared in the `with` row.
- Modes — declared at each parameter binding.
- Refinements — declared in `where` / `requires` / `ensures`.
- Capability use — visible in the effect row and in the function body.
- Spec invocations — first-class expressions, not comment markers.
- Stability — first-class `stable` / `unstable` keywords on declarations.
- Deprecation — first-class `@deprecated(reason: "...", since: "v0.2")` attribute.

The compiler already computes all this for typechecking. Serializing it to TOON is a small additional step. There is no external annotation parser, no risk of the annotations drifting from the code, no `@pattern: foo` comment that lies because someone refactored the body.

### 5.4 The annotation collapse

The six annotation classes used by the bootstrap-side structmap protocol are explicitly replaced by checked Edda forms:

| Bootstrap annotation | Edda replacement |
|----------------------|------------------|
| `@invariant <text>` | `where` clause on type / `requires` / `ensures` on function |
| `@pattern <name>: <text>` | Spec invocation; the qualified spec name *is* the pattern name |
| `@stable` | Removed; use the `stable` **keyword** on function and type declarations (`stable function`, `stable type`) — a verifier-enforced modifier, never an attribute. See [03-verification.md](03-verification.md) §7. |
| `@unstable` | Removed; use the `unstable` **keyword** on function and type declarations |
| `@internal` | Absence of `public` |
| `@deprecated(reason)` | `@deprecated(reason: "...", since: "v0.2")` first-class attribute |

The replacement is not partial but total. Edda source admits no comments at all — there is no `@invariant` comment to write, redundant or otherwise, because there is no comment token to carry it. Every structmap fact is emitted from the typed AST (signature, effect row, refinements, `calls`, `effect_cone`), never derived from comment scraping; there is no source-side annotation surface left for the structmap to read.

### 5.5 MCP queries

**Implementation status:** neither leaf below is in the §2.2 locked catalogue — no stub constant exists for either today. Both describe a still-roadmapped extension to `inspect.*`; what follows is target design.

- `inspect.structmap_for_directory(path)` — returns the live in-memory structmap for `path`. The daemon does not re-read the on-disk file; it serves the current authoritative state.
- `inspect.structmap_diff(ref_a, ref_b)` — returns the structural diff between two git refs. Used by code review tooling: "what types/functions/effects changed between these commits?"

The diff is structured, not textual. Adding a parameter to a function shows up as a `signature.parameter.add` event with the parameter details; renaming a field shows up as a `type.field.rename` event with both names. Diff reviewers can read intent without parsing source.

### 5.6 Structure-map density and the modularization compact

Edda's verbosity is the language's positive trade. The `with`-row, the parameter modes, the `where`/`requires`/`ensures` clauses, the `calls` graphs that flow into the structmap — all of it produces ~2× the line count of an equivalent C++ implementation, with C++ in turn being slightly leaner than Rust. The language pays this LOC tax because every line is information the next reader — model or human — would otherwise have to reconstruct.

The trade only works if the **unit of reading** stays small. That unit is the directory, not the file. Each `index.toon` is the canonical entry-point an LLM consults before opening source; if a single `index.toon` exceeds the model's instant-ingestion budget, the agent must summarize instead of fully read, and the verbosity-for-context trade collapses. The verbosity stays; the context the verbosity was bought for goes missing.

For this reason the compiler treats directory-level structural density as a first-class concern and emits two diagnostics during `check`, `parse-roundtrip`, and `build`:

#### 5.6.1 `structure_map_too_dense` — token-cost density gate

The density gate is **token-cost based, not line-count based**. Line count was retired as the density metric: it decoupled from the real read cost by roughly an order of magnitude on dense indices — a 205-line index can carry ~43k tokens, *safe* by line count yet far over budget. Lines are anti-correlated with the property the gate is named for, so the line metric is no longer a gate. (`density_warn_loc = 250` survives only as an optional, non-blocking readability signal, never as a build gate.)

**Metric — real BPE tokens.** The byte→token ratio is unstable across TOON content (signature-dense rows ≈1.4 chars/token; routing/count rows ≈4 chars/token), so the gate measures real tokens with a BPE tokenizer (`o200k_base`), not bytes×constant. Token cost is reported in *consuming-model* units, scaled by a `model_calibration` factor (default `2.5`); the effective substrate ceiling is therefore `node_green_max / model_calibration ≈ 6000 / 2.5 ≈ 2400` `o200k` tokens. The cap is reached by row **weight** — heavy `calls` columns — not by raw function count.

**Gate A — per-node cap (PRIMARY, the modularization driver).** Each `index.toon`'s *own* token cost is banded against `node_green_max` (default `6000`). The bands are configurable, but in the default configuration `node_amber_max == node_green_max`, so the amber band is empty and the step is green→red at one token over the ceiling. A separate under-provisioned warning fires on a near-empty node (under ~1000 tokens) that nonetheless carries many exports. A directory that hoards too much *local interface* errors **on that directory**; the remediation is to push files down into child directories, where their interface lives behind a `children[]` link instead of inlined here. This is the proper token-based successor to the retired line gate.

**Exemption law (schema v7).** A single call-cohesive file with no partition seam is a non-problem — there is no modularization move for one cohesive file, so gating it would yield only information loss. Such a file is **exempt-atomic** (its intra-file call graph admits no cut; a types-only file with no call graph is exempt by the same rule), and its interface cost is **excluded from the Gate-A projection**. It still renders in full in its directory's `index.toon` under the identical schema — v7 never destroys a file's interface expression.

**Atomic-hoard gate (schema v7).** Multiple exempt-atomic files in one directory *is* a genuine, structurally splittable multi-file problem. The trigger is: **≥2 mutually call-disjoint exempt-atomic files in the directory AND their combined exempt interface exceeds the read cap.** The directive is to distribute each atomic file into its own leaf directory. This is surfaced through Gate B.

**Gate B — scale-free structural laws (SECONDARY, depth backstop).** Gate B carries **no token budget**. It is two dimensionless structural laws over the directory tree:
- **Law 1 — lean hub.** A directory's own interface should be small relative to the subtree beneath it: `own/subtree ≤ 1/3` is green, `> 1/2` is red. This catches a fat node that the per-node cap alone would tolerate so long as it sits under the absolute ceiling.
- **Law 2 — earn your place.** A single-child empty wrapper directory (a "vine" that adds a path segment without holding any interface of its own) is flagged; intermediate directories must earn their existence.

Gate B replaced the earlier *spine token-budget* model (a root→`D` token sum banded 8k/12k). A spine sum is a budget, not a distributor: it tolerates a degenerate "one fat node + thin everything-else" shape under ceiling and misblames innocent deep leaves for a fat ancestor. The scale-free laws self-localize the diagnostic to the directory actually at fault, which is why Gate A (per-node) is primary and Gate B (structure) is the backstop, not a second budget.

Both Gate A and Gate B surface through the single `structure_map_too_dense` diagnostic (default severity `error` — escalated with the other structural lints because the remediation is mechanical) carrying the per-directory worklist of offending nodes and the remediation directive. The `deferred[]` table is gone (schema v7) — the gate never collapses a file's interface to a count.

**Model assumption (confirmed).** Indices are non-recursive: an ancestor carries only a `children[]` counts table (`path, types, functions`), never a descendant's interface. This is the precondition that makes both gates *local* — a directory's cost is a function of its own rows plus its children's counts, never of any descendant's full interface.

**Composition rationale.** Ceilings stay conservatively below the agent's working-zone budget. The total reading budget decomposes as `C ≥ spine + lateral + destination_interface + source + reasoning + headroom` (anchor `C ≈ 100k`); the static gates bound the statically-knowable node and structure cost and guarantee room for the task-dependent terms by construction.

**Phase 2 (planned, not yet specified).** A future routing/interface split of the `index.toon` format — where a spine sums routing-only content and per-file interface slices load on demand against `destination_interface` — is the planned resolution for genuinely dense-cohesive cores that collide head-on with `file_low_cohesion` (a cohesive cluster the gate wants split but cohesion forbids splitting). The format for that split is deferred; this section specifies only the Phase-1 measure/gate/diagnose model, with the index format unchanged.

#### 5.6.2 `filename_encodes_hierarchy` — flat-directory antipattern

**Trigger.** Either of the following holds inside a directory containing `.ea` files:

- **Cluster condition** — two or more `.ea` files in the directory share a non-trivial leading token. Tokens are delimited by `_`; the shared token must itself be a candidate identifier (≥2 characters). Examples: `queue.ea` + `queue_error.ea` (cluster `queue`, two members); `scenarios_v2_audit.ea` + `scenarios_v2_cancel.ea` + `scenarios_v2_cross.ea` (cluster `scenarios`, three members; sub-cluster `v2` within that).
- **Underscore condition** — any `.ea` filename contains an underscore. `_` in an Edda filename is itself a smell: it almost always encodes a hierarchy boundary that should be a directory.

Both conditions emit through the same lint key. A single file may trigger via underscore alone (`test_support.ea` with no `test_*` siblings still fires); a directory of underscore-free files may trigger via cluster (`queue.ea` + `queueing.ea` — strict prefix without an underscore).

**Remediation message.** The diagnostic emits explicit before/after path mappings so the agent's fix-up cannot recreate the antipattern by literal restatement. For the `scenarios_v2_*` example:

```
help: cluster `scenarios_v2_*` (3 files) should live in scenarios_v2/. Rename on move:
        scenarios_v2_audit.ea  → scenarios_v2/audit.ea
        scenarios_v2_cancel.ea → scenarios_v2/cancel.ea
        scenarios_v2_cross.ea  → scenarios_v2/cross.ea
```

The rename half of the remediation is what prevents endless cascade: after the move the new directory's files no longer share the redundant prefix, so the diagnostic does not re-fire at the next level.

**Default severity:** `error`.

#### 5.6.3 Why these defaults are tight

The `6000`-token per-node cap is deliberately aggressive — its effective `o200k` substrate ceiling (~2400 tokens after `model_calibration`) sits close to the budget a frontier model can ingest in one shot without summarization pressure, leaving the rest of the working-zone budget for the task. The cluster threshold of 2 is the smallest non-trivial signal — one shared prefix is a coincidence; two is a hierarchy. Both defaults exist to **pull the language toward depth-first organization from the first file written**, not to tolerate density until it becomes a problem.

The compiler will tell the agent at every emission. The agent will refactor. The directory structure will deepen. Each `index.toon` will stay short enough for the next reader to ingest in full. The verbosity-for-context trade keeps paying out.

### 5.7 Reading discipline: structure-map gating

Article II requires every writer to declare effects, modes, and refinements on the signature so a reader never has to chase context. The reading-discipline contract is the same requirement pointed the other way: before an LLM author edits a `.ea` file, it must first consume the compiler-emitted facts about what that edit touches. A structmap nobody reads is a signature nobody wrote — the signal density Articles I–VII pay for on the writer's side is wasted if the reader's side reverts to guessing.

**The contract.** Before modifying a `.ea` file, an LLM author reads that file's `index.toon` chain: the compiler-emitted index at every directory from the project root down to the target directory, read top-down. This chain is the minimal structmap coverage for an edit at that location — the target directory's own `functions[]` / `types[]` / `invariants[]` rows (§5.2), plus the ancestor `children[]` links (§5.2) that place the directory in the project. When an edit could change a dependency's contract — its signature, effect row, or refinements — the read extends into that dependency's own `index.toon`, not just the editor's local chain.

Once a directory's chain is read, source is opened by **focused span**, not by whole file, for any file large enough that reading it in full would exceed a single-ingestion budget. Each `functions[]` / `types[]` row carries the item's `line,end` span (§5.2); that span is self-contained — it already covers any leading attributes, the full signature and contract clauses, and the body — so reading the declared span is sufficient without additionally reading the surrounding file.

**Reconciling with "no external tooling necessary."** This chapter opens by ruling out annotation scrapers and AST-walking linters that re-derive what the typechecker already knows. The reading-discipline gate does not violate that rule: it computes nothing about Edda source and re-derives no fact. Its only inputs are which `index.toon` files exist on a path and which of them the current session has already read; its only output is permit-or-deny on an edit. It is a sequencing constraint over the one structural-truth surface the compiler emits (§5.4), not a second surface alongside it — the gate enforces *consumption* of compiler-emitted facts, it does not compute them.

**Enforceability.** The contract is mechanically enforceable, not advisory, through a two-part mechanism at the editor/agent-harness boundary:

- A **pre-edit gate** — before an edit to a `.ea` file is allowed to proceed, checks whether every `index.toon` on the root-to-target chain has been read in the current session; if any is missing, the edit is denied, and the denial names the exact unread maps in root-to-leaf order.
- A **read ledger** — records, per session, which `index.toon` files have been consumed, so the gate clears once the chain is complete.

A reference implementation of this two-part contract exists in this project's authoring harness — a pre-tool-use gate paired with a post-tool-use read ledger, enforcing exactly the two behaviors above. Any IDE or agent integration that wants the same guarantee can implement the same two-part contract at its own hook points, against the same `index.toon` emission this chapter already specifies; the gate and ledger are harness configuration, not daemon protocol surface, so they carry no MCP namespace and no wire format of their own. The concrete hook implementation and its tuning are documented with the project's own authoring tooling rather than the language reference — the same carve-out already drawn for source-mirror publishing in [07-distribution.md](07-distribution.md) §10.

---

## 6. Diagnostics discipline

### 6.1 Format

Every diagnostic is a structured object. The locked V1.0 shape:

```
{
  class: <DiagnosticClass>,
  severity: error | warn | info,
  primary_message: <string>,
  primary_span: {file, byte_start, byte_end, line_col_start, line_col_end},
  canonical_form: <string>,
  obligation_trace: [<predicate>],
  counterexample: <model> | null,
  suggested_edits: [<structural_edit>],
  effect_row_context: <effect_row> | null,
  notes: [{message, span?}]
}
```

### 6.2 Diagnostic classes (locked)

The V1.0 enum locks the original 19 classes (the 16 listed in [03-verification.md §The `DiagnosticClass` enum](03-verification.md) plus `capability_not_available_on_target` from the cap-availability table at [02-modes-effects-refinements.md §3.7](02-modes-effects-refinements.md), plus `capability_escalation` and `lockfile_tampered` from the Mímir package-management surface at [08-packages.md](08-packages.md)). New classes are added in minor versions and never renumbered. The structural-density classes locked in §5.6 and the strictly-bad-behaviour warning set added in subsequent minor versions are part of the V1.0 surface and listed below.

The **canonical enumeration of the full `DiagnosticClass` set lives in [03-verification.md](03-verification.md)**; this section is the cross-listed tooling view and lists the full 46-member enum with each class's default severity. The implemented enum has grown past the original 19 through minor-version additions — the bootstrap currently carries 46 variants (the 19-class core, plus the stability/termination/coherence classes, the structural-density and strictly-bad-behaviour warnings, the `unknown_attribute` / `comment_not_admitted` sterility classes and `file_low_cohesion`, `non_exhaustive_match`, `unprovided_runtime_extern`, `executor_missing_in_row`, and the most recent addition, `duplicate_runtime_extern`). The "19" is the *original locked* count, not the live total; the live count is tracked authoritatively in ch03.

**This table enumerates the bootstrap's `DiagnosticClass`, not the native self-host's diagnostic-code catalogue.** The native compiler (`compiler/lib/diagnostics/src/code.ea`) currently emits 70-odd flat `code.*() -> String` codes rather than a `DiagnosticClass` enum, and the two sets are not 1:1 — this is by design, not naming drift. Three things are true simultaneously:
- Where a name appears in **both** sets — the criterion is name presence in both catalogues; currently 35 of the 46, running from `parse_error` and `typecheck_error` through the structural lints (`structure_map_too_dense`, `file_low_cohesion`) to the link-time classes (`unprovided_runtime_extern`, `duplicate_runtime_extern`) — the string must stay byte-identical — this is the actual parity obligation (§6.4). This shared set grows as native implements more locked classes under their canonical names, so its count is a snapshot rather than a fixed number.
- Granularity runs **both directions**, not just one: `refinement_unproven` collapses five native SMT-discharge codes (`refine_failed`/`refine_timeout`/`refine_unknown`/`refine_solver_internal`/`refine_encoding_unsupported`) — native finer than bootstrap — while the reverse holds for `stability_callee`/`stability_effect`/`stability_unverified`, three separate locked classes that all report through one native code, `stability_violation` — native coarser than bootstrap. Native also carries a `comptime_*` family (6 codes) and a `spec_*` family (6 codes) subdividing comptime-evaluation and spec-resolution failures at a grain the bootstrap enum does not classify at all, plus pipeline-stage buckets with no bootstrap counterpart (`manifest_error`, `cli_error`, `link_error`, `codegen_error`, `emit_error`, `hir_error`, `mir_error`, `cache_error`, `internal_error`) because the bootstrap's Rust type system already separates those stages outside the `DiagnosticClass` mechanism.
- Conversely, native has **not yet implemented** roughly seven of the locked classes below — chiefly the coherence-region, graded-effect-bound, and termination obligations (`coherence_mutable_refinement_invalidated`, `coherence_init_param_written`, `effect_graded_bound_exceeded`, `termination_unproven`), the target/codegen classes (`simd_target_unsupported`, `unknown_target_feature`), and `executor_missing_in_row`. **This set is a moving snapshot — it shrinks every time native lands another class under its canonical name (the hygiene lints, the drift/signal warnings, and the Mímir package-management classes have all crossed into the shared set above), so the live not-yet-implemented set is tracked in the issue tracker rather than frozen here.** `unknown_manifest_key` and a `[lints]` severity-override / `default_severity` dispatch mechanism have landed natively — `compiler/lib/manifest` now parses a `[lints]` block (`diagnostics.emit.lint.config`'s `LintConfig`/`effective_severity`, consulted through `diagnostic.lint_at`) and native's own diagnostic-code catalogue is validated against it, though the dispatch mechanism is not yet wired into any lint beyond that one. These remaining gaps are real self-hosting work toward the §6.4 bootstrap-parity commitment, not a documentation defect in this table.

| Class | Default severity |
|-------|------------------|
| `parse_error` | error |
| `import_resolution_error` | error |
| `import_cycle` | error |
| `typecheck_error` | error |
| `refinement_unproven` | error |
| `effect_row_mismatch` | error |
| `mode_violation` | error |
| `simd_target_unsupported` | error |
| `unknown_target_feature` | error |
| `stable_contract_revision` | warning |
| `unaligned_field_access` | warning |
| `comptime_purity_loss` | warning |
| `deprecated_use` | warning |
| `unused_import` | error |
| `unknown_manifest_key` | error |
| `gc_recoverable` | info |
| `effect_graded_bound_exceeded` | error |
| `stability_callee` | error |
| `stability_effect` | error |
| `stability_hash_iter` | error |
| `stability_unverified` | error |
| `termination_unproven` | error |
| `divergence_not_admitted` | error |
| `coherence_mutable_refinement_invalidated` | error |
| `coherence_init_param_written` | error |
| `structure_map_too_dense` | error |
| `filename_encodes_hierarchy` | error |
| `mode_overgrab` | warning |
| `trust_hatch_too_dense` | warning |
| `refinement_trivially_true` | warning |
| `binding_should_be_let` | error |
| `duplicate_import` | warning |
| `dead_private_function` | warning |
| `unused_closure_capture` | warning |
| `exec_scope_without_spawn` | warning |
| `duplicate_spec_invocation` | warning |
| `capability_not_available_on_target` | error |
| `capability_escalation` | error |
| `lockfile_tampered` | error |
| `file_low_cohesion` | error |
| `unknown_attribute` | error |
| `comment_not_admitted` | error |
| `non_exhaustive_match` | error |
| `unprovided_runtime_extern` | error |
| `executor_missing_in_row` | error |
| `duplicate_runtime_extern` | warning |

32 classes default to error, 13 to warning, 1 (`gc_recoverable`) to info — the split is a deliberate design choice, not incidental: `unused_import`, `unknown_manifest_key`, and `binding_should_be_let` default to **error** despite reading like lints, because their resolution is mechanical (remove the leaf import, fix the typo'd key, change `var` to `let`) and a warning-severity mechanical fix predictably ages into ignored noise. The remaining eight warning-severity entries are the **strictly-bad-behaviour** set: each fires only on a pattern that has no legitimate use (defensive over-grab of `mutable`/`take`, trivially-true refinements, duplicate imports, dead private functions, unused closure captures, `scope(exec)` blocks without `spawn`, redundant `spec` invocations, audit-relevant `@unverified`/`@trust` density). The lints exist as a smoke detector: when they fire on competent code, it is almost always a real defect waiting to be cleaned up. The other five warning entries (`stable_contract_revision`, `unaligned_field_access`, `comptime_purity_loss`, `deprecated_use`, `duplicate_runtime_extern`) are drift/signal warnings rather than strictly-bad-behaviour lints — each flags a state that is sometimes intentional or survivable (an in-progress signature revision, a deliberate layout choice, a refactor that cost purity, a deprecated call site not yet migrated, a duplicate `__edda_*` extern definition across link inputs — advisory because the linker resolves the clash and the link proceeds, though a stray duplicate silently shadows the intended definition).

Per-class severity is overridable in `package.toml` with one of `"warn"`, `"deny"`, or `"error"` (`"deny"` and `"error"` are synonyms). There is no suppression spelling — the `"allow"` opt-out was removed, so every class is emitted at its resolved severity, never dropped:

```toml
[lints]
unused_import = "error"
unknown_target_feature = "warn"
```

The CLI flag `--warn-as-error` promotes every warning to error for a single invocation.

### 6.3 Required fields

Every diagnostic must carry:

- **Class + severity + primary message** — the human-facing summary.
- **Primary span** — source location with byte offsets *and* line/column.
- **Canonical form** — the fully-elaborated expression that failed, with implicit conversions, defaulted parameters, and inferred types all made explicit. The user sees what the typechecker actually saw, not what they typed.
- **Obligation trace** — for refinement and effect diagnostics, the chain of in-scope predicates that the discharge context assembled. The user can see exactly which assumptions were available and which were not.
- **Counterexample** — when SMT returns `sat`, the model rendered as concrete Edda values. Not raw `(model (define-fun lo () Int 5))`; the user sees `lo = 5, hi = 3` in Edda syntax.
- **Suggested edits** — structured patches in the LSP code-action shape. Even when the diagnostic is informational, suggested edits give the agent something to apply directly.
- **Effect-row context** — when the diagnostic concerns effects, the enclosing function's declared row is included for reference.

See [03-verification.md](03-verification.md) for the canonical-form and counterexample discipline; this section locks the wire-level shape.

### 6.4 Bootstrap parity

This format is a V1.0 commitment. The Rust bootstrap compiler must emit this exact structure. Native parity is non-negotiable: tools that target the bootstrap must continue to work, byte-for-byte, against the native compiler.

### 6.5 Worked example

A `refinement_unproven` on `requires lo <= hi`:

```
{
  class: "refinement_unproven",
  severity: "error",
  primary_message: "precondition `lo <= hi` of `geom.midpoint` not proven at call site",
  primary_span: {file: "src/main.ea", line_col_start: [42, 17], line_col_end: [42, 35], ...},
  canonical_form: "geom.midpoint(lo: 5, hi: 3)",
  obligation_trace: [
    "5 : i64",
    "3 : i64",
    "<no in-scope predicate constrains 5 <= 3>"
  ],
  counterexample: {
    "lo": 5,
    "hi": 3
  },
  suggested_edits: [
    {
      kind: "signature.requires.add",
      target: {qualified_name: "main.compute_midpoint"},
      args: {predicate: "lo <= hi"},
      rationale: "propagate the obligation to the caller"
    }
  ],
  effect_row_context: null,
  notes: [
    {message: "called from", span: {file: "src/main.ea", line: 41}},
    {message: "declared at", span: {file: "src/geom.ea", line: 12}}
  ]
}
```

---

## 7. Bidirectional synthesis surface

The author writes code; the compiler verifies it. Bidirectional synthesis closes the loop: the compiler can also propose code that satisfies a partial specification.

### 7.1 Level 1: typed completion

**Implementation status:** `inspect.completions_at` is not in the §2.2 locked catalogue — no stub constant exists today. What follows is target design for a still-roadmapped extension to `inspect.*`.

```
inspect.completions_at(file, position, prefix?) -> [completion_candidate]
```

Returns expressions whose type is compatible with the expected type at `position`, ranked by:

1. Refinement satisfaction — candidates whose refinements discharge against the in-scope obligations rank higher than those that introduce new obligations.
2. Effect compatibility — candidates whose effect row is a subset of the enclosing function's row rank higher.
3. Locality — bindings in scope at `position` rank higher than imports.
4. Stability — `stable` items rank higher than `unstable`.

Each candidate carries: the qualified name, the type at this position, the effect impact, the refinement effect (which obligations it discharges, which it introduces), and a confidence score.

The LSP `textDocument/completion` request is wired to this. The IDE sees typed, ranked completions; the LLM author querying directly through MCP sees the same surface.

### 7.2 Level 2: goal-directed synthesis

**Implementation status:** `inspect.synthesize` is not in the §2.2 locked catalogue and carries no implementation today — not even an unrouted stub constant. The search strategy and ranking below are the target design.

```
inspect.synthesize(signature_spec) -> [body_candidate]
```

Given a function signature — parameter types and modes, return type, effect row, `requires` / `ensures` / `decreases` — the daemon proposes function bodies that satisfy the obligation.

The search is Synquid-style: refinement-typed search over the decidable fragment. The daemon:

1. Enumerates candidate program shapes from the available stdlib and project surface, filtered by type.
2. Discharges the `ensures` postcondition against each candidate using the same SMT discharge as normal verification.
3. Returns the candidates that prove, ranked by complexity (Occam's razor) and effect-row tightness.

For V1.0, synthesis is best-effort. It will succeed on simple cases (arithmetic with refinements, linear container manipulation, single-effect composition); it will time out on the hard ones. Post-V1.0 makes the engine production-quality with proper search heuristics, caching, and time budgets.

### 7.3 Why daemon-side, not source-syntax

There is no synthesis surface in the source language. No `synth { ... }` block, no `???` holes that the compiler tries to fill. The language surface from Articles I–VII is unchanged.

Synthesis is a service the daemon offers to clients. The LLM author queries it via MCP and gets candidates it can then write into the source. The IDE wraps it as a code action ("synthesize body matching this signature"). The CLI surfaces it as `edda synth <function>` for explicit invocation.

Keeping synthesis out of the source surface means: (a) the source remains the authoritative spec, (b) synthesized code is committed as ordinary source after the author accepts it, (c) the verification story does not depend on the synthesizer.

---

## 8. CLI verbs (locked V1.0 surface)

Each verb has a 1:1 MCP-operation counterpart. The CLI is a thin client of the daemon; running `edda check` spawns or connects to a daemon, sends `build.typecheck`, and prints the response.

**Build / test verbs:**

- `edda build [--target <name>]` — full build (link + codegen).
- `edda check [--target <name>]` — typecheck + refinement discharge, no codegen.
- `edda run [<member>]` — build and run. In a workspace, `<member>` selects the member to launch (resolving to `lib/<member>/package.toml`); a bare `edda run` at a workspace root launches the member named by `[workspace] default_run`, or, when that key is unset, reports the selectable members.
- `edda test [--filter <pattern>] [--properties]` — run tests; `--properties` enables derived PBT (see [03-verification.md](03-verification.md)).
- `edda bench [--filter <pattern>]` — run benchmarks.

**Cache management:**

- `edda gc` — garbage-collect content-addressed cache entries not referenced by the current workspace.
- `edda promote <hash>` — pin a cache entry against GC; moves the artifact up a cache tier (see [07-distribution.md §3.3](07-distribution.md) for tier semantics). Not yet implemented — stubbed in the bootstrap dispatcher.
- `edda demote <hash>` — unpin a cache entry. Not yet implemented — stubbed in the bootstrap dispatcher.

**Utilities:**

- `edda regenerate` — re-materialize all spec invocations under `codegen/`.
- `edda clean` — wipe build outputs (preserves the content-addressed cache).
- `edda fmt` — format Edda source (canonicalize layout).
- `edda synth <function>` — explicit-invocation CLI surface for goal-directed synthesis (§7.2/§7.3); a thin client of `inspect.synthesize`, which is not in the §2.2 locked catalogue and carries no implementation today — the verb is locked V1.0 surface, not yet wired.
- `edda lint` — run lints. The `--trust-points` subflag lists every `@unverified` / `@trust` annotation in the project (the audit surface) as `Info` diagnostics naming the item and its `reason`. The `--capability-safe-stdlib` subflag enforces the stdlib capability discipline as `Error` findings: no item may shadow a locked capability nominal type, and no function's effect row may name an ambient capability not backed by one of its own parameters. Both analyses are **implemented in the bootstrap CLI** (gated, off by default); the full alias-traced capability-laundering check (a narrowed capability re-widened and returned/passed) over the typed capability graph remains a follow-up.

**Service / metadata:**

- `edda daemon [--transport ...]` — start the daemon.
- `edda structmap [path]` — emit structmaps for the current project. The `--check` flag is **implemented in the bootstrap CLI**: it compares each emitted `index.toon` against the on-disk file (per member and at every workspace-aggregator directory) and exits non-zero with a `parse_error` per stale or missing map, **without** rewriting anything — the side-effect-free CI staleness gate. A synced tree exits `0`.
- `edda contract-diff <a> <b>` — human-readable rune-to-rune surface/effect SemVer-impact diff (each arg a `<name>@<version>` registry spec or a local `.rune` path); see [08-packages.md](08-packages.md) §8.5 for the shipped behavior. `03-verification.md` §8 documents a finer-grained, per-function contract-hash delta query under the same verb name — that shape is still-roadmapped target design, not what the verb does today.
- `edda version` — print compiler, daemon, and protocol versions. (Implemented as a pre-dispatch intercept, so `version` is not a member of the locked `Verb` catalogue, but `edda version` works as documented.)

**Package management (Mímir).** The `edda add` / `update` / `audit` / `publish` / `why` verbs and the `edda key` publisher-keypair verb are part of the CLI surface; they are specified in [08-packages.md §8](08-packages.md). A hot-reload `edda hot` verb also exists (driver-side).

**Toolchain:**

- `edda tc status` — the verify-latest board: source `HEAD` vs `origin/main`, and the active compiler binary's recorded provenance vs the bootstrap repo's `origin/main`. Exits non-zero when the binary is stale or dirty.
- `edda tc sync` — rebuild the active compiler binary from the bootstrap repo's `origin/main`.
- `edda tc which` — print the active binary plus the resolved `std`/`runes` roots.

`edda` itself is a verified launcher on `PATH`: it resolves `std` and `runes` from the surrounding monorepo worktree and execs the content-addressed store binary, with no environment to set. The five trees (`compiler/`, `std/`, `runes/`, `web/`, `codex/`) are consolidated in one monorepo — there are no submodules and no toolchain bundle. The `tc` verbs are **launcher-provided**: they manage and verify the toolchain binary itself, so — unlike the build/inspect/edit verbs — they have no daemon/MCP counterpart and are not members of the bootstrap CLI's `Verb` catalogue.

---

## 9. Package layout and manifest

### 9.1 Manifest format

The manifest is `package.toml`, in TOML. The structural index uses TOON; the package manifest uses TOML. They are different formats for different audiences — the manifest is human-edited; the structmap is machine-emitted.

### 9.2 Layout

**Single-package:**

```
my-project/
  package.toml
  src/
    lib.ea
    ...
```

**Workspace:**

```
my-workspace/
  package.toml
  lib/
    member-a/
      src/
        lib.ea
    member-b/
      src/
        lib.ea
```

Workspace members are implicitly registered as dependencies of the root by their `root_namespace`. No `[dependencies]` entries are needed for intra-workspace references.

### 9.3 Manifest blocks

The following top-level blocks are locked for V1.0:

- `[package]` — `name`, `version`, `root_namespace`, `max_trust` (the trust-hatch ceiling), plus the descriptive keys `edition` / `authors` / `license` / `description`. The bootstrap manifest reader now parses and retains the descriptive keys (`edition` / `license` / `description` are strings; `authors` is an array of strings); they are captured verbatim on `PackageManifest` and do not yet drive any build behavior.
- `[workspace]` — `members = [...]`, the optional `default_run` (names the member a bare `edda run` launches at a workspace root), workspace-wide defaults.
- `[dependencies]` — external package dependencies, content-addressed (see [07-distribution.md](07-distribution.md)).
- `[build]` — build configuration, `emit_structmap`, target features.
- `[profiles]` — per-profile codegen options as named sub-tables (`debug`, `release`, custom). (The bootstrap parses a single `[profiles]` table whose keys are the profile names, rather than separate `[profile.<name>]` tables.)
- `[lints]` — per-class severity overrides for diagnostics.
- `[codegen]` — spec materialization options, output directory (default `codegen/`).
- `[structmap]` — structure-map density-gate configuration (the token-budget knobs of §5.6; see also the retired `density_warn_loc` readability signal).

### 9.4 Reserved namespaces

The following root namespaces cannot be used as `root_namespace`:

- `std` — standard library.
- `codegen` — reserved for generated artifacts.
- `tests` — reserved for test modules.
- `bench` — reserved for benchmark modules.
- `examples` — reserved for example programs.

### 9.5 Lockfile

The lockfile schema is part of the V1.0 surface; full distribution mechanics are specified in [07-distribution.md](07-distribution.md).

---

## 10. Reserved for post-V1.0

The following are deferred from V1.0, with their place in the protocol reserved so V1.0 clients will continue to interoperate with post-V1.0 daemons.

**Near-term (next minor release):**

- Custom semantic-token modifiers for capability narrowing scopes, refinement-bound bindings, comptime evaluation contexts.
- Production-quality goal-directed synthesis (V1.0 is best-effort).
- Binary MCP framing (CBOR / MessagePack) as a negotiated alternative to JSON-RPC.

**Longer-term:**

- Multi-client / Live-Share LSP — multiple IDE clients on the same daemon project, with shared overlay state.
- Notebook LSP integration — Edda code cells with daemon-served diagnostics and completion.
- Daemon-to-daemon federation — remote project access across daemon instances.
- MCP resource model for source files — agents subscribing to file content as MCP resources rather than via document overlay.
- `edda.aliasGeneratedName` language form — allow source to reference a generated artifact by a stable alias rather than the mangled qualified name.

---

## 11. The protocol surface as the deliverable

Articles I–VII produce a language that an LLM author can reason about locally and the compiler can verify globally. Article VIII produces a *protocol* — a typed, locked, daemon-served query API — that lets any author (human, agent, IDE) talk to that compiler through a single surface. The protocol is what makes the language usable. The locks in this document are what make the protocol durable.

A V1.0 client written against `client.handshake`, `inspect.diagnostics`, `edit.signature.parameter.add` will continue to work against every V1.x compiler. New methods may be added; existing methods will not change shape. This is the contract between the compiler and every tool that ever talks to it — and, by extension, between the compiler and the LLM authors who depend on those tools to author Edda safely.
