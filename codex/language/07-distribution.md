# Distribution: content addressing, packs, caches, verifiers

> The shipping layer. Specs are codegen templates; their instantiations are
> real artifacts that must travel. Refinements produce certificates;
> certificates are verifiable proofs that travel alongside artifacts.
> Distribution is the mechanism that lets verified, content-addressed
> outputs SHIP — between machines, between teams, between projects,
> between revisions. Every artifact carries proofs; every proof is
> independently verifiable; every cache hit is mechanically trustable.

This doc covers the layer beneath the compiler: the bytes that move
between developer machines, CI runners, and shipped binaries. The
[verification](03-verification.md) chapter describes how proof
certificates are produced. The [specs](04-specs-comptime.md) chapter
describes how concrete artifacts are generated from spec templates. The
[tooling](06-tooling.md) chapter describes the CLI verbs and daemon that
drive the workflow. This chapter describes the wire formats, the cache
hierarchy, and the trust path from "the compiler emitted this byte" to
"a downstream consumer verified it independently".

The principle is simple: identity is hash, trust is certificate. Two
machines that feed the same inputs into the same compiler version
produce byte-identical outputs and byte-identical certificates. A
consumer who fetches an artifact from any cache tier can recompute its
hash and re-run its certificates without trusting the producer. The
publisher's reputation buys nothing the verifier cannot check.

---

## 1. Why distribution matters for Edda's thesis

Edda's thesis is that the LLM author receives all the context needed
to generate correctly. That context is not just the local file in
front of the model — it is the precondition that every call resolves
to a function whose contract has been verified, whose obligations have
been discharged, and whose artifact is the one the author is reading.
If a function `parse_url` lives in a stdlib pack, the author's signature
view must agree with the bytes the linker pulls in. If a spec
`std.collections.vec.Vec(i32)` instantiates into an artifact on machine A, that
same artifact must be byte-identical on machine B, in CI, in the
published binary, and in the consumer's reconstruction.

Three properties follow from this:

1. **Identity is mechanical.** The artifact's name is its content hash.
   No machine-local timestamps, no path-dependent identifiers, no
   "last modified" sorting. Two artifacts with the same hash are the
   same artifact; two artifacts with different hashes differ in their
   inputs.
2. **Proofs travel with bytes.** Every refinement obligation that was
   discharged at compile time produces a certificate. Certificates are
   independently checkable. A cache that serves an artifact also serves
   its certificate; a consumer that doesn't trust the cache re-runs the
   certificate before linking.
3. **Specs and refinements compose with caching.** A spec
   instantiation that succeeded for one project is reusable by another;
   a refinement that was discharged for one call site applies to every
   call site with the same context. The cache is what makes
   verification affordable.

This is what makes **Article IV — verified over hoped** durable across
the development lifecycle. Verification is not a build-time event that
evaporates at the artifact boundary; it is a property the artifact
carries.

---

## 2. Content addressing

### 2.1 BLAKE3 everywhere

Every content-addressed identity in Edda is a BLAKE3 hash. The choice
is locked: no other hash function is admitted, and no construct in the
language reaches for one. BLAKE3 was chosen for three properties: it
is fast enough that hashing every blob during a build is not a
bottleneck, it produces a fixed-size 32-byte output that fits cleanly
in `manifest.toon` fields and 12-hex-prefix filenames, and its tree
structure permits streaming verification of large blobs without
buffering the whole payload.

The principle is canonicalization before hashing. Every input to a
BLAKE3 call must be a canonical byte sequence — the same logical
content must produce the same bytes on every machine. Map ordering,
field insertion order, trailing whitespace, line endings, and integer
endianness are fixed by the schema, not by the producer.

### 2.2 The locked uses of BLAKE3

The compiler computes five distinct hashes at the build layer, each
with a fixed input shape (the `.rune` pack layer's three load-bearing
hashes are specified in [08-packages.md](08-packages.md)):

- **Spec artifact hash.** BLAKE3 over the canonical encoding of the
  spec's qualified name, its comptime argument tuple, its canonical
  body bytes, and the transitive hashes of every nested spec
  invocation reachable from the body. Two instantiations of
  `std.collections.vec.Vec(i32)` produce the same artifact hash on every machine
  because every input is canonical. A change to a nested helper's
  body changes the helper's hash, which changes the outer artifact's
  hash through the transitive component.
- **Obligation hash.** BLAKE3 over the canonical encoding of a
  refinement obligation's predicate. This is the certificate cache
  key: an obligation that was discharged in one context is reusable
  when the same predicate arises elsewhere with a compatible context.
- **Context hash.** BLAKE3 over the canonical conjunction of context
  predicates at a call site (the path conditions, the parameter
  refinements, the captured environment). Combined with the
  obligation hash, this keys the certificate cache:
  `(obligation_hash, context_hash) -> certificate`.
- **Contract hash.** BLAKE3 over the canonical function signature
  (parameter modes, parameter types, return type, effect row,
  refinements). This is the function-level identity for contract diff
  — see [03-verification.md](03-verification.md) for how contract diff
  uses the hash to localize re-verification.
- **Artifact filename.** The 32-byte hash is rendered as 12 hex
  characters and appended to a short mangled name:
  `<short-mangled-name>__<12-hex-prefix>.ea`. The full 32-byte hash
  lives in `manifest.toon`; the filename prefix exists only for
  human-readable directory listings and shard distribution.

The filename grammar `<short>__<12-hex-prefix>` is locked. Both the
double underscore and the 12-hex-character prefix are part of the cache
lookup; changing either invalidates every cache lookup against
historical caches.

### 2.3 Determinism in practice

The workspace's single-binding rule is what enforces this in code:
every BLAKE3 invocation in the compiler routes through
`edda_cache::hash_bytes`, which is the only public entry point and the
only point at which a hash is computed. Auditing determinism reduces
to auditing one function. The function takes canonical bytes and
returns a 32-byte digest; it never sees a non-canonical input because
the canonicalization step happens upstream, at the schema layer.

Two machines that run the same compiler version against the same
sources produce byte-identical artifacts and byte-identical
certificates. A CI runner that publishes an artifact and a developer
machine that rebuilds the same artifact agree on every byte; a
mismatch is a compiler bug or a tampered cache, never a benign
divergence.

---

## 3. Cache hierarchy

### 3.1 Three tiers

Edda caches sit at three tiers, layered so that the lowest-cost tier
serves the most reads and the highest-cost tier is the source of
authority:

- **Project cache** (`<project>/.edda/cache/`). Gitignored, writable,
  populated by the build process on the developer's machine. This is
  the only writable tier from a developer's day-to-day perspective.
  It holds artifacts produced for the current project, including
  spec instantiations and their proof certificates.
- **Team cache** (optional, **not yet implemented**). A shared
  filesystem path or HTTP endpoint, populated by CI. Read-only from the
  developer's perspective. Holds artifacts that the team has agreed to
  share — typically the outputs of merged pull requests, published
  packs, and certificates that have survived CI's verifier. The
  bootstrap currently implements only the project and global tiers; the
  team tier is the optional middle tier and is planned but not yet
  present in the cache layer (its HTTP/S3 backends are separately
  deferred — see §12).
- **Global cache** (`~/.edda/global-cache/`). Populated by published
  packs. Read-only from the build's perspective. The stdlib lives
  here as a precomputed pack, as do third-party libraries the
  developer has explicitly installed. Persists across projects on the
  same machine.

The tiers are independent by design — this holds for the locked
three-tier model, though V1.0 ships only two of the three (see above):
a developer with no global cache configured still benefits from the
project cache alone; once the team tier lands, a CI runner with no
global cache configured will still benefit from project + team.
Misconfiguration or absence of one tier degrades performance, never
correctness.

### 3.2 Lookup order

Lookup is project → team → global (currently project → global, until
the team tier lands — see §3.1). The first hit serves the read; the
compiler does not consult lower tiers once a hit is found. This is
deterministic: the project cache cannot serve a stale artifact under a
hash, because the hash is a function of the inputs and every layer
agrees on the BLAKE3 function. A "hit" at any tier means the bytes
match the requested hash, which means the bytes are the artifact.

If a hash misses at every tier, the compiler treats the artifact as
needing construction. For a spec instantiation, this triggers comptime
evaluation; for a certificate, this triggers SMT discharge; for a
blob, this is an error — the upstream stage should have produced it.

### 3.3 Promotion

**Implementation status:** `edda promote` and `edda demote` are locked
V1.0 verbs; neither is implemented in the bootstrap yet — the
dispatcher stubs both (`emit_pending`, exit `SYSTEM_ERROR`) for every
invocation, and the CLI parser accepts only a single `<artifact>`
positional for each, no tier selector, no `--sign` flag — matching
[06-tooling.md §8](06-tooling.md)'s locked catalog form: `edda promote
<artifact>` / `edda demote <artifact>`.

Promotion moves an artifact between the two project-local tiers.
`edda promote <artifact>` moves a generated artifact from the
gitignored cache tier (`.edda/cache/codegen/`) into the
version-controlled repo tier (`<project>/codegen/`), so the artifact
ships with the project's source; `edda demote <artifact>` is the
inverse. Tier placement otherwise follows the chain-origin rule — an
artifact whose instantiation chain originates in project source lands
in the repo tier; one reached only through other generated artifacts
lands in the cache tier — with `package.toml`'s
`codegen.default_tier` (`auto` | `cache`) as the override: under
`cache`, every artifact starts in the cache tier and only an explicit
promote places it in the repo. Promotion is atomic: the artifact and
its manifest entry move together, or neither moves.

The team and global tiers are not populated by promotion: the team
tier (when it lands) is populated by CI from its own builds, and the
global tier is populated by installed and published `.rune` packs
(§5, §8.3). Promotion never modifies an artifact's bytes. The hash of
a promoted artifact equals the hash of the source artifact; the only
thing that changes is the tier from which it is served.

### 3.4 Storage layout

Each tier uses the same hash-sharded layout. The first **two bytes**
(four hex characters) of the BLAKE3 prefix select a shard directory; the
full twelve-hex prefix appears in the filename:

```
.edda/cache/
  abcd/
    parse_url__abcdef012345.ea
    parse_url__abcdef012345.manifest.toon
  cd98/
    vec_i32__cd9876543210.ea
    vec_i32__cd9876543210.manifest.toon
```

Each artifact carries a sibling `manifest.toon` file with schema
version 1. The manifest records the artifact's full 32-byte hash, its
inputs (spec name, comptime arguments, transitive hash list), its
blob index (which blob kinds are present in the artifact), and its
provenance (compiler version, build target, optional signing
identity).

The filename grammar — short mangled name, double underscore, twelve
hex characters, `.ea` extension — is locked across all three tiers.
A change to the grammar would invalidate every cache lookup against
historical artifacts, so the grammar itself is a versioned surface
treated with the same weight as the `.rune` pack format.

### 3.5 Reachability-driven garbage collection

**Implementation status:** `edda gc` is a locked V1.0 verb, currently
stubbed in the bootstrap dispatcher; the schedule and prune machinery
described below exist in the cache layer but are not yet driven by
builds.

The project cache grows over time. `edda gc` removes artifacts that
are not reachable from any active build target. Reachability is
computed by walking the dependency graph from each target's root set
through every spec instantiation, every refinement obligation, and
every artifact-to-artifact edge.

GC behavior is named, not numeric, and configured per tier in
`package.toml`:

```toml
[codegen.gc_schedule]
cache_tier = "weekly"
```

The sub-block carries one tag per tier — `cache_tier`, `repo_tier`,
`global_cache` — each one of `never` / `daily` / `weekly`. Locked
defaults are `weekly` for `cache_tier` and `never` for `repo_tier` and
`global_cache` (a version-controlled or published artifact is not
garbage-collected automatically).

Manual `edda gc` always runs regardless of schedule.

Reachability includes generated-module item edges. When a comptime
form generates a module containing function items, each item is a
reachability root in its own right; the GC does not collapse the
generated module into a single node and therefore does not over-eagerly
collect items the linker still needs.

---

## 4. Per-pass blob format

> **Implementation status (V1.0 in progress).** The per-pass blob
> format below — the 43-byte blob header (§4.2) and the five blob kinds
> (§4.1) — is **not yet implemented** in the bootstrap. The current
> cache stores opaque `.ea` artifact files with no blob-kind framing;
> per-pass blob layout is an explicit scope cut for the current wave.
> This section specifies the reserved wire format, not the current
> on-disk reality.

### 4.1 The five blob kinds

A single artifact is not a single file. It is a collection of blobs,
each produced by a distinct compiler pass and each addressable in its
own right. The compiler emits up to five blob kinds per artifact:

- **AST** — the parsed syntax tree, after the parser has run but
  before name resolution.
- **typecheck** — the typed HIR, including refinement obligations and
  effect rows attached to every function.
- **proofs** — the proof certificates discharged for the typecheck
  pass's obligations. One certificate per `(obligation_hash,
  context_hash)` pair.
- **IR** — the serialized typed mid-level IR (MIR) consumed by both
  compilers. This blob is the input to native code generation; the
  native backend lowers MIR → HLIR → LIR → machine code and emits no
  LLVM bitcode. (The bootstrap's internal hand-off to LLVM is private
  to the bootstrap, not a distributed blob kind.) The MIR serialization
  for this blob kind is not yet locked.
- **obj** — the native object file (format version v1.0), ready for
  linking.

Each blob is keyed by the triple `(artifact_hash, blob_kind,
blob_version)`. Two blobs with the same triple are byte-identical;
two blobs that differ in any field of the triple are distinct artifacts
to the cache.

### 4.2 Blob header

Every blob begins with a 43-byte header:

| Bytes | Field |
|-------|-------|
| 0 | Version byte (currently `0x01`) |
| 1–32 | Artifact hash (BLAKE3 digest) |
| 33 | Body version (per-kind monotonic) |
| 34 | Blob kind tag |
| 35–42 | Payload length, little-endian u64 |

The header is fixed-size and self-describing. A reader can identify a
blob's kind and version from the first 35 bytes; the payload length
permits skipping a blob without parsing its body.

### 4.3 Versioning trajectory

V1.0 ships AST, typecheck, and proofs. These three blob kinds are
"write-only" in V1.0: they are produced and stored but not yet read
back for incremental rebuilds. The proofs blob is consumed by the
verifier (see section 6).

Post-V1.0 adds IR and obj. With those two kinds available, a full
incremental rebuild can be served from cache hits at every stage —
parse, typecheck, prove, lower, link — touching disk only for the
final binary.

Per-kind body versions advance independently. A change to the AST
serialization bumps the AST body version without affecting typecheck
or proofs body versions. A reader rejects a blob whose body version
exceeds the compiler's known maximum for that kind.

---

## 5. The `.rune` pack format

The `.rune` archive format — the on-disk packaging of a rune — its
container choice, internal layout,
trust chain, three load-bearing hashes — is specified in
[08-packages.md §3 and §4](08-packages.md). At a glance: a single
`tar.zst` archive with sorted entry order and pinned compression
flags (`--long=27 -19`), whose internal layout is `manifest.toml`,
`surface/`, `mir/`, `objects/<triple>/`, `index.toon`, `hashes.toon`,
`signature.bin`, and `publisher.key`. The tar.zst choice is a
deliberate reversal of an earlier custom-container design (`EPK1`
magic plus binary index plus per-blob zstd); the rationale — tooling
ubiquity, debuggability, deterministic reproducibility against the
canonicalization story used everywhere else in the corpus — is
recorded in [08 §3.1](08-packages.md).

This section covers two concerns that remain at the distribution
layer rather than the packaging layer: the trust posture each cache
tier requires, and the V1.0 → post-V1.0 reader/writer trajectory.

### 5.1 Trust posture per cache tier

This is the locked trust posture for the full three-tier model (§3.1):
archives in the global cache must be signed; archives in the team
cache may be signed; archives in the project cache are never signed.
**Implementation status:** only the project and global tiers exist in
V1.0 — the team tier's signing policy is specified here for when it
lands, not configurable today (see §3.1). The signing key identifies
the publisher; the trust roots that recognize the key ship with the
V1.0 compiler. An archive with a missing or invalid signature is
rejected when consumed from a tier that requires signing.

The signature itself is over `hashes.toon`, not over the archive
bytes. The trust chain — signature verifies `hashes.toon`,
`hashes.toon`'s per-file BLAKE3s verify each file, and the archive's
`rune_hash` verifies the bytes — is specified in
[08 §3.3](08-packages.md).

Trust-by-hash for signed archives is held indefinitely. Once an
archive's `rune_hash` has been recognized by a trust root and its
signature has verified, future consumers may serve the archive's
contents from any tier without re-verifying the signature, provided
the bytes still hash to the recognized value. This deferral is
conservative: it survives until post-V1.0 benchmarking demonstrates
that signature verification is a measurable cost relative to
certificate re-verification.

### 5.2 Reader/writer trajectory

V1.0 ships the reader and writer. The reader supports unsigned and
signed archives; the writer emits unsigned archives by default and
signed archives when invoked via `edda publish` against a configured
signing key. V1.0 defaults to packed storage for the global cache
and ships signing trust roots so that published stdlib archives
verify out of the box.

---

## 6. The proof certificate verifier

### 6.1 What the verifier does

The V1.0 compiler ships a small (~500 LOC) certificate verifier as a
standalone component. Its job is straightforward: read every cached
`unsat` claim and re-verify it independently of the SMT solver that
produced it. The verifier is not the solver; it is a re-checker that
takes the solver's certificate and confirms that the conclusion
follows from the premises.

The verifier exists because the certificate cache is a trust surface.
A cached certificate that was produced legitimately and a tampered
certificate inserted by a malicious cache cannot be distinguished by
their hashes alone — the hash is over the predicate and context, not
over the certificate body. The verifier closes that gap: an unsigned
cache entry is rejected outright, a signed entry's signature is
verified against the trust root, and a verified entry's certificate
is re-checked before the obligation is considered discharged.

> **Implementation status (V1.0 in progress).** Certificates are minted
> and serialized in the verification layer today, but the on-disk
> certificate cache this verifier reads from (`certificate-index.toon`,
> §9) is **not yet persisted** — so the re-check loop runs in-process,
> not yet against a cross-build cache. The certificate witness variants
> (`Smt` / `Comptime` / `Implicit` / `Unverified` / `Trust`) match the
> implementation; the certificate's on-disk *header* layout is owned by
> [03-verification.md](03-verification.md) and is audited there.

### 6.2 The verifier as Article IV trust root

The verifier is what makes "verified over hoped" durable. Without it,
a consumer that pulls a certificate from a cache would have to trust
the cache; with it, the consumer trusts only the verifier's own
correctness. Cache poisoning is detectable: a tampered certificate
fails the re-check, and the consumer falls back to re-running the
SMT solver against the original obligation.

The verifier's small size is intentional. Its correctness is what the
entire certificate cache rests on; a 500-LOC component can be audited
in a single sitting, while a 50,000-LOC solver cannot. The asymmetry
between solver and verifier — large producer, small checker — is the
standard proof-carrying-code shape.

### 6.3 Performance posture

Trust-by-hash for signed packs is deferred to post-V1.0 benchmarking.
The expectation is that for large stdlib packs, signature verification
is dominated by certificate re-verification once the cache is warm;
the benchmark will determine whether re-verification at every consumer
is the right policy or whether trust-by-hash should be enabled once a
pack's signature has been verified once on a given machine.

---

## 7. Reachability-driven materialization

The compiler does not write every intermediate artifact to disk. It
writes only those artifacts that are reachable from the active
command's root set. A reachability graph is built from the command's
explicit targets and walked through every spec instantiation,
refinement obligation, and module edge.

Per-target reachability roots differ:

- `edda build --target wasm32-wasi-preview1` rooted at the wasm
  entrypoint pulls in the no-std subset of the stdlib, the
  refinement-checked allocator, and the bounded-recursion proof
  templates.
- `edda build --target x86-64-linux-gnu` rooted at the native
  entrypoint pulls in the full stdlib, the heap allocator, and the
  threading primitives in `std.thread`.

Two `edda build` invocations on the same project may materialize
disjoint artifact sets if their targets differ. The compiler does not
materialize the union; it materializes only what each target needs.
This reduces cache bloat dramatically and keeps the project cache
proportional to the active development surface, not the project's
historical breadth.

Generated-module item edges are tracked. When a comptime form emits a
module containing function items, each generated item participates in
reachability — the generated module is not collapsed to a single node.
This matters because spec instantiations frequently produce generated
modules with many items; collapsing would either over-materialize (if
the module is reached at all, every item is written) or
under-materialize (if any item is unreached, the module is treated as
dead). Per-item tracking is the only correct policy.

---

## 8. Package layout

### 8.1 The two shapes

Edda projects have two locked layouts:

- **Single-package.** A `package.toml` at the project root and a
  bare `src/` directory containing `.ea` files. The package's name
  comes from `package.toml`; its root namespace is the package name.
- **Workspace.** A `package.toml` at the project root and a `lib/`
  directory whose children are member packages, each with its own
  `<member>/src/`. Cross-member dependencies are registered
  implicitly by `root_namespace`: a workspace member declares its
  root namespace in its own metadata, and other members import from
  it by that namespace without any explicit dependency edge in
  `package.toml`.

The bare-`src/` rule for single-package is intentional: the absence
of a `lib/` wrapper signals "this is not a workspace" to every reader
without requiring a config field. Symmetrically, the presence of
`lib/<member>/src/` for any member signals a workspace and switches
the resolver into workspace mode.

### 8.2 Reserved root namespaces

Five root namespaces are reserved across every package:

- `std` — the standard library.
- `codegen` — generated modules produced by comptime forms.
- `tests` — the test harness's module tree.
- `bench` — the benchmark harness's module tree.
- `examples` — example programs that ship alongside a library.

A package may not declare a root namespace that collides with any of
these. The reservation is total — no package, workspace member, or
third-party library may shadow them.

### 8.3 Stdlib as a precomputed pack

The stdlib lives in the global cache as a precomputed `.rune` pack.
A fresh install of the V1.0 compiler ships the stdlib pack
pre-positioned in `~/.edda/global-cache/`; the first build on a fresh
machine reads from the global cache rather than recompiling the
stdlib from source. The stdlib's hashes are stable across compiler
patch releases; a minor compiler upgrade that does not change the
emitted bytecode does not invalidate the cached stdlib pack.

---

## 9. Locked TOON wire formats

TOON is the canonical wire format for compiler outputs whose
consumers are humans, structmap, or downstream tooling. (Packed
binary bytes use `.rune`; TOON does not duplicate that role.) Three
TOON schemas are locked:

- **`manifest.toon`** — schema version 1. One per cache root, recording
  per artifact: its repo-relative path, its full hash, its mangled
  short name, its tier, its hash inputs, the sources and artifacts
  that reach it, and its generation timestamp. Read by the compiler on
  cache lookup. The schema is versioned so that future fields can be
  added without invalidating historical manifests.
- **`index.toon`** — schema described in
  [06-tooling.md](06-tooling.md). The compiler-emitted structural
  index for source directories. One file per source directory; the
  project root holds the index and a `children[]` list pointing to
  subdirectories.
- **`certificate-index.toon`** (**not yet implemented**) — the
  certificate cache's directory layout. Records, per cache shard, the
  `(obligation_hash, context_hash)` pairs present and the certificate
  hashes they map to. Read by the verifier on cache lookup. The
  bootstrap mints and serializes proof certificates today but does not
  yet persist a certificate index to disk; this schema is reserved for
  the certificate-persistence layer.

All three schemas share the same canonicalization rules: map ordering
is alphabetical by key, field values are encoded with fixed numeric
formatting, and lists are encoded in the order specified by the
schema (insertion-order for unsorted lists, sort-order for sorted
ones). The canonicalization is what allows the files to be hashed
deterministically and shipped across machines.

---

## 10. Two publish verbs

Edda has two distinct publish flows, disambiguated by their leading
verb:

- **`edda publish`** — the registry flow. Signs and uploads an `.rune`
  pack to Mímir for consumption as a dependency. This is the verb
  relevant to distributing reusable packages; it is specified in
  [08-packages.md §8.4](08-packages.md).
- **Source-mirror publishing** — the development flow. The public
  `edda` repository is a sanitized, generated mirror of a private dev
  tree: fresh commits, never a history copy, so private history cannot
  leak. The mirror is produced by tooling that runs outside the
  language and is not part of the distribution format; its contract
  lives with the project's development docs rather than this language
  reference.

---

## 11. Performance baselines

The post-V1.0 performance commitments shape the architecture above.
Caches, content addressing, reachability-driven materialization, and
the persistent index in the daemon all exist to meet these numbers:

- **Clean build.** Under one second for the stdlib-consuming reference
  project, starting from an empty project cache but a warm global
  cache. This number depends on parallel comptime evaluation and on
  the global cache serving stdlib artifacts without recomputation.
- **Incremental build.** Under two hundred milliseconds for a
  single-function change. This number depends on contract diff (see
  [03-verification.md](03-verification.md)) localizing
  re-verification to the changed function and its dependents, and on
  the certificate cache serving every other obligation unchanged.
- **Daemon cold start.** Under one second on a project with an
  up-to-date persistent index. The persistent index is what permits
  the daemon to skip a full directory walk on startup; see
  [06-tooling.md](06-tooling.md) for the daemon's process model.

These are post-V1.0 commitments, not V1.0 commitments. The V1.0
compiler ships without the IR and obj blob kinds and without the
global cache pre-positioning; V1.0 builds will not hit the numbers
above, and the V1.0 baseline is measured against its own scope
rather than the post-V1.0 targets. The architecture is sized to meet
the post-V1.0 numbers; V1.0 is a subset implementation.

---

## 12. Reserved for post-V1.0

The V1.0 surface excludes several capabilities that are sketched in
the architecture but deferred to post-V1.0. None of them are required
to ship V1.0; they are listed here so that the V1.0 surface can be
read as a deliberate subset rather than a missing feature set.

- **HTTP and S3 team-cache backends.** V1.0 ships filesystem-path
  team caches only. HTTP and S3 are deferred until the
  authentication and rate-limiting story is concrete.
- **Overlay packs.** Delta packs layered on a base pack, for
  shipping incremental updates to large libraries without
  re-emitting the whole pack. The format is reserved; the V1.0
  emitter does not produce them.
- **Cross-language obligation reuse.** Verified FFI participating
  in Edda's certificate cache, so that a C function with a verified
  refinement contract can be called from Edda without re-discharging
  the obligation. The mechanism is reserved; the V1.0 compiler does
  not implement it.
- **Distributed verifier audit.** A network protocol by which an
  external auditor can re-verify a published pack's certificates
  without downloading the full pack. Reserved.
- **Streaming queries for large result sets.** The pack reader
  currently materializes a blob in full before returning it.
  Streaming consumption is reserved for post-V1.0.

The line between V1.0 and post-V1.0 is drawn so that V1.0 is
sufficient for self-hosting and stdlib distribution and post-V1.0
adds the surface required for multi-tenant team and ecosystem
deployment.
