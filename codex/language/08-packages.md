# Package management: Mímir, runes, manifest, lockfile, CLI

> Distribution moves bytes between caches; package management is the
> surface a human (or an LLM author working alongside one) reaches for
> when they want to *add a dependency*. The shape of that surface
> decides what kinds of supply-chain failures are mechanically
> impossible versus left to publisher honor. Edda's bet is that the
> failures most other ecosystems treat as honor-bound — SemVer
> truthfulness, transitive trust, capability escalation through
> updates — can be reduced to hash comparisons the consumer runs
> locally. The publisher gets no trust they did not earn through a
> signature; the registry gets no trust the lockfile does not pin.

This chapter specifies the package-management surface: the brand name
of the system, the wire format of a published package, the three
independent hashes that key SemVer enforcement, the manifest fields
that pin trust, the lockfile that records resolved state, and the CLI
verbs that drive the workflow. The [distribution](07-distribution.md)
chapter describes the cache hierarchy and content-addressing
primitives this layer rests on; the [verification](03-verification.md)
chapter describes the contract-hash machinery that the publish workflow
inherits; the [tooling](06-tooling.md) chapter describes the broader
`edda` CLI surface this chapter extends.

---

## 1. Why package management is part of the spec

Most ecosystems treat their package manager as a separate product —
designed, versioned, and governed apart from the language. The cost
of that separation is paid by every consumer: SemVer is a publisher
promise rather than a mechanical property; transitive trust requires
auditing tooling outside the compiler; capability escalation in an
update is invisible until something exfiltrates. Edda chooses the
opposite trade. The package manager's surface is part of the language
spec because the language's thesis — every piece of context the LLM
author could plausibly need, defending against the floor of model
behavior — does not survive the moment a dependency lands.

Three properties follow from binding package management to the spec:

1. **SemVer is mechanical, not honored.** The publisher's claimed
   version is checked against three independent hashes computed by
   the consumer. A patch-claimed update whose `surface_hash` changed
   is rejected at `edda update` time; a minor-claimed update whose
   `effect_hash` grew is rejected on the same call. The publisher
   cannot lie about compatibility because the consumer is not asked
   to take their word.

2. **Trust narrows at first install and never widens.** The first
   `edda add` pins the publisher's Ed25519 fingerprint into the
   manifest. Every subsequent update from that name must verify
   against the same key. A maintainer handoff that changes the
   signing key is a manual decision recorded in the manifest, not a
   silent rotation the consumer is asked to accept.

3. **The consumer's effect ceiling caps the dependency's authority.**
   The manifest's `max_effects` is the union of effect-row entries
   any reachable public function in the dependency is permitted to
   carry. An update that grows the effect surface beyond this ceiling
   is rejected with diagnostic class `capability_escalation`, not
   admitted with a warning.

These three properties are what the rune exists to deliver. The
container format, the hashes, the manifest fields, and the CLI verbs
are all in service of mechanical verification at consume time.

---

## 2. Naming and roles

Four names cover the surface, each with a single responsibility.

**Mímir** is the registry — the system and brand by which runes are
discovered, fetched, and verified. The name is Norse: Mímir is Óðinn's
oracle, the source of trustworthy knowledge. The reference registry
domain is `mimir.edda.dev`; the lockfile records the registry that
served each artifact in its `source` field, so a deployment that
mirrors Mímir behind a corporate proxy or replaces it with a vendored
filesystem path differs from the reference deployment only by that
field's value. There is no separate `mimir` binary; the registry is
served, the client surface is the `edda` CLI.

**rune** is the unit of distribution. The archive extension is
`.rune`; a single archive corresponds to a single
published version of a single package. The container format is
specified in §3 of this chapter; the hashes that identify it are
specified in §4; the manifest fields a consumer writes to depend on
it are specified in §6.

**`edda`** is the unified tool surface. Following the Cargo lineage
(`cargo add`, `cargo update`, `cargo publish`) rather than the npm
lineage (`npm`, separate from `node`), every package operation is an
`edda` subcommand: `edda add`, `edda update`, `edda audit`,
`edda publish`, `edda contract-diff`, `edda why`. The full list is
specified in §8. The choice of one binary is intentional — every
operation that touches the cache hierarchy, the manifest, or the
lockfile already requires the compiler's resolver and the daemon's
persistent index, so a separate binary would either duplicate them
or fall out of sync.

**Reference registry domain.** `mimir.edda.dev` is the locked
reference; the lockfile's `source` field treats it as a hint, never
as authority. A consumer whose lockfile pins a specific `rune_hash`
will refuse to serve different bytes regardless of which registry
returns them. Registry brand and registry domain are decoupled by
construction: a corporate mirror at `mimir.example.com` serves the
same hashes and is functionally indistinguishable.

### 2.1 The stdlib / rune boundary

Two distribution tiers carry Edda code, and the line between them is
drawn by a single mechanical test rather than left to accretion.

**`std.*` is ambient.** Every Edda program transitively imports the
standard library without an `edda add`; it ships with the toolchain,
versions with the language, and carries the V1.0 stability guarantee.
Because that guarantee is only as honorable as the surface is small,
`std.*` is held to what the language itself cannot do without.

**runes are explicit.** Everything else is distributed through Mímir,
pinned in `package.lock.toml`, added with `edda add`, and free to
evolve on its own SemVer cadence under the three-hash enforcement this
chapter specifies. Security-sensitive code (the cryptographic suite)
and domain-bound code (calendar tables, wire-format parsers, payload
codecs) belongs here precisely because it wants an evolution cadence
independent of the language's.

**The criterion.** A package is `std.*` if and only if it satisfies at
least one of:

1. **The compiler reaches for it by name.** `derive` targets
   (`std.core.compare`, `…hash`, `…fmt`, `std.core.copy`,
   `std.serde.core`, `std.testing.properties`); the `?`-propagation
   carriers (`std.core.outcome`, `std.core.option`); the f-string
   formatter backbone; `std.task` (every `scope(exec)` spawn result);
   the allocator primitives (`std.mem.alloc`); and the BLAKE3 the
   compiler uses to content-address specs and runes.
2. **It is on the stable-callee whitelist.** A `stable` function may
   call only other stable functions and a curated stdlib subset (the
   `math`, `bytes`, `string`, `fmt` families per
   [03-verification.md](03-verification.md) Rule 2). A `stable`
   function cannot call into a rune, so the whitelisted subset must
   stay ambient.
3. **It is a capability operation surface.** The package one imports to
   *exercise* one of the 18 locked capabilities: `std.os.{fs, process,
   env, time}`, `std.io.{stream, cursor}`, `std.net.{socket, udp}`,
   `std.mem.alloc`. The capability *types* are nominal and minted by
   the runtime; the operations that consume them ship with the
   language.
4. **It is an irreducible container.** The data structures essentially
   every program needs: `Vec`, `String`, slices, sort, `HashMap` /
   `HashSet`, ranges.

Everything else is a rune. The V1.0 reading is **pragmatic-core**:
near-universal utilities that the criterion does not strictly compel —
`deque`/`heap`/`bitset`, `ipc.channel`, the low-level `mem` family,
`encoding.{hex, base64, varint}`, `text.{ascii, search, lines}`,
`core.{cmp, reduce, assert}`, `os.path`, `io.cursor` — stay ambient
because the mandatory-`edda add` they would otherwise impose on nearly
every program is not worth the marginally smaller surface.

**Compiler-dependency carve-out.** A package the compiler itself
imports stays in `std.*` even when the criterion would otherwise
emigrate it, because the compiler cannot take a Mímir dependency on a
package whose own distribution it is responsible for content-addressing
— that is circular. The load-bearing case is **BLAKE3**: the rest of
the cryptographic suite emigrates to the `crypto` rune, but the BLAKE3
used for spec and rune content-addressing stays ambient.
`std.core.semver` is the same shape — it stays only if the resolver
imports it; otherwise it emigrates.

**Disposition.** Applying the criterion across the 113 packages in
`std/lib/` at V1.0 (a package is any directory carrying its own
`package.toml`; `crypto`'s namespace nests three to four levels deep
by algorithm — e.g. `crypto.aead.aes.gcm`, `crypto.sig.ed25519` — so a
shallow two-level directory scan undercounts it): 68 stay, 45 emigrate.

Stays in `std.*`:

| Subsystem | Packages |
|---|---|
| `core` | compare, hash, fmt, copy, option, outcome, iter, range, parse, overflow, cmp, reduce, assert |
| `collections` | vec, slice, sort, hashmap, hashset, array, deque, heap, bitset |
| `text` | string, str, itoa, atoi, utf8, ascii, search, lines |
| `mem` | alloc, raw, atomic, bits, byteorder, cmp, fill, rt, suballoc |
| `os` | fs, process, env, time, path, debug, pages, raw |
| `io` | stream, cursor, stdio |
| `net` | socket, udp, dns |
| `math` | scalar, constants, integer, float |
| `encoding` | hex, base64, varint |
| `archive` | tar |
| `compress` | zstd |
| `bytes` | bytes |
| `serde` | core |
| `ipc` | channel |
| `task` | task |
| `testing` | properties |
| `crypto` | hash.blake3 (content-addressing carve-out only) |

`mem.rt` and `mem.suballoc` are the heap-region/sub-allocator runtime
`mem.alloc` and `Box(T)` are built on; `os.pages` and `os.raw` are the
mmap/syscall substrate the capability operation surfaces (`os.fs`,
`os.process`) are built on — all four stay under the same
compiler-dependency carve-out as `mem.alloc` itself. `archive.tar` and
`compress.zstd` are the `.rune` container substrate — the compiler
packs and unpacks the tar.zst archive format (§3.1) through them — so
both stay under the same carve-out as the content-addressing BLAKE3.
`os.debug` is the
operation surface for the `Debugger` capability (criterion 3), exactly
as `os.fs`/`os.process` are for `Filesystem`/`Subprocess`. `io.stdio`
is the operation surface backing `Stdin`/`Stdout`/`Stderr` (criterion
3). `net.dns` performs resolution (a `Network` capability operation),
unlike the address-parsing-only `net.{cidr,ip,mac}` trio that
emigrates below. `math.float` is the floating-point transcendental
counterpart to `math.scalar`/`math.integer` — as near-universal as
either (criterion 4).

Emigrates to a rune:

| rune | From `std.*` | Holds |
|---|---|---|
| `crypto` | `crypto.*` (minus `hash.blake3`) | aead (aes.gcm, chacha20.poly1305), ecdh, field (gfp.p256, gfp.p384), hash (sha256, sha512), kdf (hkdf), mac (hmac.sha256, hmac.sha384), pke (rsa.oaep), random (CSPRNG), sig (ecdsa, ed25519, ed448, rsa, secp256k1), subtle, x509 (cert, chain) — 20 leaf packages |
| `encoding` | `encoding.{asn1,base32,pem,percent,url,utf16}` | the codecs the compiler does not reach for |
| `netaddr` | `net.{cidr,ip,mac}` | CIDR / IP / MAC address parsing (the `Network` capability and `net.{socket,udp,dns}` stay) |
| `chrono` | `time.{calendar,iso8601}` | calendar math (the `Clock` capability and `os.time` stay) |
| `numerics` | `math.{bigint,complex,random}` | arbitrary precision, complex, non-crypto PRNG |
| `color` | `graphics.color` | color-space conversions |
| `checksum` | `core.checksum` | CRC / Adler |
| `semver` | `core.semver` | SemVer parse/compare (unless the resolver imports it — then it stays per the carve-out) |
| text utilities | `text.{csv,glob,htmlescape,shell,escape,repeat,wrap,lex}` | grouped at migration: standalone `csv` / `glob` / `lex`, an `escaping` umbrella (htmlescape, shell, escape), a `textwrap` umbrella (wrap, repeat) |

**Naming and grouping.** First-party runes use bare, descriptive names
— `crypto`, `encoding`, `netaddr`, `chrono` — matching the convention
already shipping in the `runes/` subtree (`json`, `regex`, `tls`, `toml`,
`yaml`, `uri`, `cookies`, `hermod`, `pgsql`); the registry brand is not
a package-name prefix. A cohesive multi-package family ships as one
umbrella rune that versions and publishes together — `crypto.aead` and
`crypto.sig` come from one `crypto` archive under one publisher key —
while a genuinely single-purpose package stays standalone. Because
`std` is a reserved root namespace (see [06-tooling.md](06-tooling.md)),
emigration changes a package's import path — `std.crypto.aead` becomes
`crypto.aead` and now requires an `edda add crypto` — which is the
intended signal that the dependency is no longer ambient. The migration
itself (moving each family into the `runes/` subtree, wiring
`package.lock.toml`) is downstream of this lock and out of scope for
the codex.

---

## 3. The `.rune` archive format

### 3.1 Container choice: tar.zst with pinned flags

A `.rune` file is a single `tar.zst` archive. The `tar` ordering is
fixed (sorted lex by entry path), entry mtimes are zeroed, ownership
fields are zeroed, and the zstd compression is invoked with the
pinned flags `--long=27 -19`. Two machines that compress the same
canonical tar bytes with the same zstd version under these flags
produce byte-identical archive output.

The container choice supersedes the custom `EPK1` design sketched in
earlier drafts of this corpus and recorded in
[07-distribution.md §5](07-distribution.md). The reversal is
deliberate. A custom binary container buys faster random access at
the cost of every consumer needing format-aware tooling; tar.zst
buys ubiquitous tooling (every Unix has tar; zstd is stable across
platforms), debuggability (extract to a directory and read the files
directly), and reproducibility (the canonicalization story is the
same one that already covers `manifest.toon` and `index.toon`).
Random access is recovered by the in-archive `index.toon`, which
records each entry's offset; readers that want O(log n) lookup
binary-search it the same way the earlier design binary-searched the
custom index section.

The flags `--long=27 -19` are part of the format. `--long=27`
enables long-range mode with a 128 MiB window, which is what makes
the compression deterministic across zstd versions for the file
sizes Edda produces; `-19` is the level. Changing either flag
invalidates the `rune_hash` of every archive built before the change,
so the flags are versioned as carefully as the magic bytes in the
earlier custom design.

### 3.2 Layout

The archive's internal layout is fixed. A reader that extracts the
tarball expects exactly these entries:

```
manifest.toml          canonical subset of package.toml
surface/               one .toon per public module
  <module>.toon        per stable item: signature, effect row,
                       refinements; sorted lex by item name
mir/                   MIR per module (post type-check)
  <module>.mir
objects/               compiled artifacts per target triple
  <triple>/<name>.o
index.toon             compiler-emitted structmap for the archive
hashes.toon            rune_hash, surface_hash, effect_hash,
                       per-file BLAKE3s
signature.bin          ed25519(publisher_priv_key, hashes.toon)
publisher.key          ed25519 pubkey + fingerprint line
```

Five categories of content are deliberately excluded: source `.ea`
files, tests, benches, examples, and rendered HTML docs. The
exclusions are size-driven for tests/benches/examples and trust-driven
for source — a rune's surface is its `surface/*.toon` plus its `mir/`,
not its source files. A consumer who wants source ships a sibling
`<name>-<version>.rune.src` archive (format reserved; V1.0 does not
emit it).

The `surface/` directory is the heart of the consumer-visible surface.
Each `.toon` file corresponds to one public module; within each file,
items are sorted lex by name, and each item records its signature,
effect row, and refinement clauses. These checked facts are carried
verbatim into the LLM synthesis surface at every call site that
references the item; there is no doc-comment text to carry, because
Edda source admits no comments and the structure map is derived
entirely from the typed AST.

`mir/` carries the typed MIR for each module post type-check. The
MIR has been verified — refinement obligations discharged, effect
rows resolved, contract hashes recorded. A consumer linking against
the rune does not re-typecheck or re-verify the MIR; the surface
contract is what the consumer commits to, and the MIR is the
implementation that satisfies it.

`objects/<triple>/` carries pre-compiled native object files keyed by
target triple. A rune that supports `x86-64-windows-msvc`,
`aarch64-darwin`, and `x86-64-linux-gnu` ships three
subdirectories under `objects/`. Targets not represented in the
archive force the consumer to re-lower from `mir/`; for stdlib and
common dependencies, every supported target is shipped.

`index.toon` is the compiler-emitted structmap for the archive's
content, sized as a directory-tree index in the same shape as the
per-directory `index.toon` files described in
[06-tooling.md](06-tooling.md). A reader that wants to know what
public items the rune offers, with their signatures and effect rows,
reads `index.toon` first; the per-module `surface/*.toon` files are
the authoritative form, and `index.toon` is the navigation layer.

`hashes.toon`, `signature.bin`, and `publisher.key` together form the
trust chain; §4 and §9 specify them in detail.

### 3.3 Trust chain

The trust chain for a consumer verifying a rune is exactly four
steps. (a) Read `publisher.key`; its fingerprint is checked against
the manifest's pinned `publisher.key_fingerprint`. (b) Read
`signature.bin` and `hashes.toon`; verify the signature against
`hashes.toon`'s canonical bytes using the publisher's pubkey. (c)
Recompute every per-file BLAKE3 in `hashes.toon` and compare against
the recorded values. (d) Recompute `rune_hash` over the archive bytes
and compare against the lockfile's pinned value. A mismatch at any
step rejects the archive; there is no fallback path. The signature
buys trust in `hashes.toon`; the per-file hashes buy trust in each
file; the `rune_hash` buys trust in the archive bytes; the lockfile
buys trust in the version pin.

> **Implementation status (V1.0 in progress).** Steps (b)–(d) are wired
> in the bootstrap: `edda publish` signs `hashes.toon` with the
> publisher key, `edda add` verifies that signature, recomputes every
> per-file BLAKE3 on unpack, and recomputes `rune_hash` / `surface_hash`
> and compares against the registry index. Step (a) — checking the
> archive's `publisher.key` fingerprint against the manifest's pinned
> `publisher.key_fingerprint` — is **not yet enforced**: the fingerprint
> computation exists and `edda add` records the fingerprint into the
> manifest, but no verb — `edda add`, `edda update`, or `edda audit` —
> yet compares an arriving key against the recorded pin. The
> pin-on-first-install story (§6.5) is the locked design; its
> enforcement is pending.

---

## 4. The three independent hashes

The rune carries three BLAKE3 hashes that each answer a different
question about what the consumer is about to take a dependency on.
Their independence is load-bearing: a legitimate patch release
changes only one of the three; a release that claims to be a patch
but changes a different one is mechanically dishonest.

| Hash | Input | Question |
|---|---|---|
| `rune_hash` | the canonical `.tar.zst` bytes | Bit-identical artifact? |
| `surface_hash` | concat of `surface/*.toon` in lex order | API unchanged? |
| `effect_hash` | sorted union of effect-row entries reachable from public items | Effect surface grew? |

### 4.1 `rune_hash` — artifact identity

`rune_hash` is BLAKE3 over the bytes of the `.tar.zst` archive. It
answers the most basic question: did the bytes change at all? The
lockfile's pin is on `rune_hash`; a consumer that fetches an archive
from any source — Mímir, a corporate mirror, a vendored filesystem
path, a teammate's cache — recomputes `rune_hash` and rejects the
bytes if they do not match. This is the foundation that lets the
`source` field be a hint rather than authority: every byte is
verified locally before it touches the build.

### 4.2 `surface_hash` — API identity

`surface_hash` is BLAKE3 over the concatenation of every
`surface/*.toon` file in lex order. The input scope is **stable items
only** — `stable function`, `stable type`, and other items carrying
the stability marker described in
[03-verification.md](03-verification.md). `unstable` items appear in
`surface/` files (so consumers can opt into them with
`accept_unstable: true`) but do not participate in `surface_hash`
input. The rationale: stability is the language's contract promise,
and `surface_hash` is the consumer's tool for enforcing it. Unstable
drift is a separate concern, governed by `accept_unstable` and
visible in `edda contract-diff` output but not in SemVer enforcement.

`surface_hash` changes mechanically detect every API change: a
parameter type changed, a refinement tightened, a stable item added,
a stable item removed. A publisher claiming a patch release whose
`surface_hash` changed will be rejected by every consumer running
`edda update`; the publisher must either revert the change or bump the
minor or major version.

### 4.3 `effect_hash` — capability surface identity

`effect_hash` is BLAKE3 over the sorted, canonically-encoded union of
every effect-row entry reachable through any public function in the
surface. An effect-row entry is one of: a capability name (e.g.
`Filesystem`, `Allocator`), a typed pure effect (`err: T`, `panic`,
`yield: T`, `cancellation`, `divergence`, `nondet`), or a graded
effect (`alloc(bytes <= N)`, `io(calls <= N)`, `time(ops <= N)`).
The union is computed by walking every public function's effect row
and every transitively-reachable internal function's effect row,
collecting each entry once. The canonical encoding is one entry per
line, sorted lex, no duplicates, UTF-8 LF.

`effect_hash` changing means the dependency's capability ceiling
grew. A function that previously raised only `err: alloc.AllocError`
now also raises `err: stream.IoError`; a function that was pure now
takes an `Allocator`; a function that lacked a graded bound now
declares one. Each of these is a real change in what authority the
consumer is delegating, and each is what `max_effects` (described in
§6) was put in place to mechanically reject.

> **Implementation status (V1.0 in progress).** The bootstrap currently
> computes `effect_hash` over the effect-row entries declared directly
> on the **public stable items** in `surface/`, collected, sorted, and
> deduplicated as specified. The **transitive-callee walk** — folding in
> every transitively-reachable internal function's effect row — is not
> yet wired: the per-item surface schema does not yet record the
> callee links the walk needs. Until it lands,
> `effect_hash` reflects the declared public effect surface but not yet
> effects an internal helper reaches that the public row does not
> already name; the canonical encoding (one entry per line, sorted lex,
> deduplicated, UTF-8 LF) matches the spec.

### 4.4 Why independence matters

The three hashes are computed from disjoint, well-defined inputs.
This is the property that makes mechanical SemVer enforcement
possible. A legitimate patch release — a bug fix that does not
change any signature, does not introduce any new effect-row entry,
does not break any consumer — has the same `surface_hash` and the
same `effect_hash` as the previous release; only `rune_hash` changes,
because the patched implementation produces different bytes. A
minor release adds a stable item; `surface_hash` changes, `effect_hash`
may change. A major release breaks an existing signature or removes
a capability ceiling; `surface_hash` definitely changes, and the
consumer's pinned `max_effects` may force the update to fail entirely
until the consumer raises the ceiling.

The publisher's claimed version is checked against the hash diff at
`edda update` time. The diff classifications are mechanical:

- `rune_hash` differs, `surface_hash` and `effect_hash` unchanged →
  patch admissible.
- `surface_hash` differs by addition only, `effect_hash` differs by
  addition only or unchanged → minor admissible.
- `surface_hash` differs by removal or signature change, OR
  `effect_hash` differs by removal of a previously declared graded
  bound (a relaxation that lets the dep do more work without the
  consumer noticing) → major required.

Publisher SemVer dishonesty — claiming a minor when major is required
— is mechanically detected and rejected.

---

## 5. Canonical encoding for hash inputs

Every byte sequence that feeds into a BLAKE3 computation in this
chapter is canonically encoded. The rules are uniform across
`surface/*.toon`, `hashes.toon`, `manifest.toml`, the lockfile, and
the effect-entry serialization for `effect_hash`:

- **UTF-8, no BOM.**
- **LF line endings.** CRLF is rejected; the canonicalizer normalizes
  on write.
- **Sorted map keys, lex order.** Every TOML/TOON table's keys are
  emitted in lexicographic order. Insertion-order encoding is not
  admitted in hash inputs.
- **No trailing whitespace.** Each line ends with the LF immediately
  after its last non-whitespace byte.
- **Single trailing newline.** The file ends with exactly one LF.
- **Floats are not admitted in hash inputs.** V1.0 refinements do not
  use floats (NLA is reserved for post-V1.0), so float fields never
  appear in any hash-input file. A future surface that admits float
  refinements will need its own canonicalization rules; until then,
  floats are excluded.
- **Integers in decimal, no underscores.** `1024`, not `1_024`. The
  underscore-as-separator surface that `package.toml` admits at the
  human-facing layer is normalized away by the canonicalizer.

Canonical encoding is the precondition for hashing. The canonicalizer
runs at rune build time over every file that feeds a hash; the
resulting bytes are what gets hashed. A consumer that wants to
verify a hash independently runs the same canonicalizer and the same
BLAKE3 against the same input bytes and gets the same result on
every platform.

---

## 6. Manifest additions to `package.toml`

Dependencies are declared as `[[dependencies]]` entries — an array of
tables, one per dependency (the manifest block inventory lives in
[06-tooling.md](06-tooling.md) §9.3). Each entry carries three
required base fields — `name`, `version`, and `source` (`registry`
for the Mímir flow, or `git+<url>` / `path+<rel-path>`) — and gains
four locked Mímir fields plus a nested `publisher` sub-table:

```toml
[[dependencies]]
name            = "regex"
version         = "^1.2"
source          = "registry"
surface_hash    = "blake3:204bd8aa…"
max_effects     = ["err: alloc.AllocError"]
accept_unstable = false

[dependencies.publisher]
key_fingerprint = "ed25519:f4c3…"
```

### 6.1 `version`

The version constraint follows the SemVer caret/tilde discipline.
`^1.2` admits any `1.x` where `x >= 2`; `~1.2.3` admits any `1.2.y`
where `y >= 3`; an exact pin like `=1.2.3` admits only that version.
Resolution chooses the highest admitted version whose `surface_hash`
matches the manifest's pinned value and whose effect ceiling fits
inside `max_effects`.

### 6.2 `surface_hash`

The pinned BLAKE3 of the dependency's public surface at first
install. Subsequent updates that change `surface_hash` are rejected
unless the consumer explicitly raises the pin — typically by running
`edda update --accept-surface-change <name>`, which records the new
hash in the manifest. The pin is per-name, not per-version; a minor
version bump that legitimately adds new stable items will fail until
the pin is raised, surfacing the API growth to the consumer as a
manual decision.

> **Implementation status (V1.0 in progress).** The current bootstrap
> `edda update --accept-surface-change <name>` waives the rejection
> and records the accepted hashes in the lockfile; rewriting the
> manifest pin itself is pending, so the raised pin does not yet
> appear as a `package.toml` diff.

### 6.3 `max_effects`

A list of effect-row entries declaring the ceiling of capability and
effect surface the consumer is willing to delegate to this
dependency. The ceiling is a **superset constraint**: the union of
every effect-row entry reachable through any public function the
consumer calls must be a subset of `max_effects`. An update whose
`effect_hash` change would push the union past the ceiling is
rejected with diagnostic class `capability_escalation`.

The list's entries use the same path-qualified leaf-form notation
used in effect rows everywhere else: `err: alloc.AllocError`,
`err: stream.IoError`, `cancellation`, `divergence`, `nondet`,
capability names like `Filesystem` or `Allocator`. Graded effects
are admitted with their bound: `alloc(bytes <= 4096)` declares that
the dependency may allocate up to 4 KiB per call; an update that
raises the bound, or introduces a new graded entry, requires manual
revision of the ceiling.

> **Implementation status (V1.0 in progress).** The locked semantics
> are the subset/superset check described above. What the current
> bootstrap `edda update` path ships is narrower: when a dependency's
> `max_effects` is non-empty, it compares the `effect_hash` it
> recomputes from the fetched candidate against the candidate's own
> registry-index entry and raises `capability_escalation` on a
> mismatch. That is an integrity check on the index claim, not the
> escalation check against the pinned hash — a candidate whose index
> truthfully reports its grown effect surface passes it. Both the
> escalation-vs-pin comparison and the precise set-difference superset
> check are pending on the live `update` path; the set-difference
> check is exercised in tests only.

An empty `max_effects = []` is a valid declaration: it requires the
dependency to be fully pure. This is the strongest ceiling and is
the right setting for pure-data dependencies (numeric formatters,
canonical-form serializers). Most dependencies will need at least
`err: alloc.AllocError` because allocation is the most common
fallible effect; carrying that one entry is not a security concern
because the consumer's own `Allocator` parameter is what authorizes
the allocation site.

### 6.4 `accept_unstable`

A boolean defaulting to `false`. When `false`, the consumer's code is
forbidden from referencing any `unstable function` or `unstable type`
in the dependency's surface; attempts produce a diagnostic at the
import site. When `true`, the consumer opts into the unstable surface
and accepts that `surface_hash` does not enforce against unstable
drift. The opt-in is per-dependency and per-consumer, not transitive:
a dependency that itself sets `accept_unstable = true` on its
sub-dependencies does not relax the consumer's own setting.

> **Implementation status (V1.0 in progress).** The import-site gate —
> rejecting references to `unstable` items when `accept_unstable` is
> `false` — is the locked design and is not yet wired. What the flag
> currently controls is version resolution: `edda add` and
> `edda update` exclude pre-release versions of the dependency unless
> `accept_unstable = true`.

### 6.5 `[dependencies.publisher]`

The pinned publisher key. `key_fingerprint` is the publisher's
Ed25519 pubkey fingerprint, set on first `edda add` of this
dependency. Subsequent updates that arrive signed by a different key
are rejected at the signature-verification step; the consumer must
explicitly accept the rotation via
`edda update --accept-publisher-rotation <name>`, which updates the
fingerprint in the manifest. Maintainer handoffs are visible as
manifest diffs in version control, not silent.

> **Implementation status (V1.0 in progress).** Rotation rejection is
> the locked design. The current bootstrap accepts
> `--accept-publisher-rotation` on the command line but does not yet
> act on it, because no verb yet compares an arriving key's
> fingerprint against the pinned `key_fingerprint` (§3.3) — a rotated
> key is not yet rejected, so the flag has nothing to waive.

---

## 7. Lockfile

The lockfile `package.lock.toml` is generated, not hand-edited. It
records the resolved state of every dependency — direct and
transitive — with enough information that the consumer can reproduce
the exact build offline given access to the per-tier cache. The
file is committed to version control alongside `package.toml`. Two
entry tables carry that state: `[[rune]]` pins each resolved
dependency, and `[[contract_baseline]]` records the package's own
stable-contract baseline.

```toml
[[rune]]
name           = "regex"
version        = "1.4.2"
source         = "mimir.edda.dev"
rune_hash      = "blake3:7a3f9c1e…"
surface_hash   = "blake3:204bd8aa…"
effect_hash    = "blake3:91ffe2…"
publisher_key  = "ed25519:9b…"
publisher_sig  = "ed25519:c0ffee…"
deps           = []   # flat transitive list

[[contract_baseline]]
qualified_name     = "regex.compile"
contract_hash      = "36b526…"
version_introduced = "1.4.0"

[lockfile_meta]
lockfile_hash = "blake3:f0011a…"
```

Each `[[contract_baseline]]` entry pins one stable item's contract
hash — the BLAKE3 over its canonical signature described in
[03-verification.md](03-verification.md) — together with the package
version at which that contract was first recorded. The compiler
upserts these entries at build time; the baseline is what makes a
breaking change to a `stable` item detectable across versions. A
lockfile may carry baseline entries and no `[[rune]]` entries at all:
a package with only local dependencies still records its own
stable-contract baseline.

### 7.1 The flat `deps` field

Each `[[rune]]` entry records its flat transitive dependency list in
`deps`. The flatness is intentional: a transitive trust collapse —
"my dep's dep was compromised" — is impossible to express coherently
when transitive trust is a graph traversal. By flattening, every
transitive rune appears as its own `[[rune]]` entry pinned to its own
hashes, and the consumer's lockfile lists every byte it will fetch.
The graph structure is recoverable from each entry's `deps` field if
needed; the lockfile primary view is the flat set.

### 7.2 `lockfile_hash` trailer

The `[lockfile_meta]` block at the bottom records the BLAKE3 of every
preceding entry's canonical encoding — `[[rune]]` and
`[[contract_baseline]]` alike. A consumer who edits
the lockfile by hand — to bump a version, swap a hash, or relax a
publisher pin — invalidates `lockfile_hash`. The next `edda build` or
`edda update` rejects the lockfile with diagnostic class
`lockfile_tampered`. The trailer is not cryptographic security
against a hostile editor (a hostile editor can recompute the trailer
trivially); it is a guard against accidental edits, merge conflicts
resolved by hand, and tooling that does not understand the lockfile
schema. The legitimate way to change the lockfile is to run an
`edda` verb that regenerates it.

### 7.3 Compiler version in `manifest.toml`

The `manifest.toml` inside a rune records the compiler version that
built it. The field is `compiler = "edda 1.0"` — major.minor, no
patch. A rune built by a compiler at a different major.minor is
rejected by the consumer's compiler at link time: `rune_hash` is a
function of `(source × compiler)`, so the same source under a
different compiler produces a different archive and would silently
mismatch the lockfile pin if compiler version were not in the
verification chain. Patch-level compiler versions are required to
produce byte-identical runes against the same source by the
self-hosting test suite (see [verification](03-verification.md)), so
the patch level is not part of the rejection criterion.

> **Implementation status (landed).** `edda publish` injects `compiler
> = "edda <major.minor>"` into the rune `manifest.toml` from the
> compiler's own version, and the `edda add` verify chain reads it back
> and fails closed on a major.minor mismatch (or a missing pin). Patch
> level is not checked.

---

## 8. CLI surface

Six package verbs extend the existing `edda` CLI described in
[06-tooling.md](06-tooling.md), plus the `edda key` publisher-keypair
verb that supports the publish flow. Each verb is named to make the
verb→effect relationship unambiguous; none is overloaded with
unrelated functionality.

```
edda add <name>[@<ver>]    resolve, fetch, verify, pin
edda update [<name>]       SemVer bump within ranges; surface/
                           effect diff must pass max_effects
edda audit                 verify every lockfile entry against
                           cached bytes
edda publish               sign + upload .rune to Mímir
edda contract-diff <a> <b> human-readable surface/effect diff
edda why <name>            transitive provenance
edda key generate          create a publisher Ed25519 keypair
```

### 8.1 `edda add <name>[@<ver>]`

Resolves the dependency, fetches the rune from Mímir (or the
configured registry), verifies the trust chain end-to-end (§3.3),
and pins the resolved version into `package.toml` with empty
`max_effects` and `accept_unstable = false` defaults. The
`surface_hash` and `publisher.key_fingerprint` are written from the
verified archive. On success, the lockfile is regenerated and
committed-ready. On any verification failure (signature mismatch,
file hash mismatch, archive hash mismatch), the verb aborts without
modifying `package.toml` or the lockfile.

### 8.2 `edda update [<name>]`

Bumps each pinned dependency (or just `<name>`) to the highest
admissible version within its caret/tilde range. Each candidate is
fetched and verified; the surface/effect diff against the currently
pinned version is computed; the diff is checked against
`max_effects` and against the SemVer-class rules from §4.4. A
candidate that violates `max_effects` raises diagnostic class
`capability_escalation`; a candidate whose surface change requires a
major-version bump that exceeds the manifest's caret range is
silently skipped. The verb prints a summary of accepted and rejected
candidates and updates the lockfile only on full success.

### 8.3 `edda audit`

Re-verifies every lockfile entry against its cached bytes. The
project cache (and team/global if configured) is searched for each
`rune_hash`; the found archive is re-verified end-to-end. The verb
is the consumer's local check that the lockfile is in a consistent
state — useful after merging a branch, before shipping a release, or
on cron in CI. `edda audit` does not touch the network; if a
lockfile entry has no cached archive locally, the verb reports it as
unverified rather than fetching it.

> **Implementation status (V1.0 in progress).** The current bootstrap
> `edda audit` searches the project cache only and re-checks each
> found archive's `rune_hash` against the lockfile pin. The rest of
> the end-to-end re-verification (signature, per-file hashes) and the
> team/global cache tiers are pending. The no-network contract holds
> today: missing entries are reported as unverified, never fetched.

### 8.4 `edda publish`

Signs and uploads a rune to Mímir (or the configured registry).
The publish verb is the publisher-side counterpart to `edda add`. It
builds the archive, runs the canonicalization step, computes the
three hashes, writes `hashes.toon`, signs it with the publisher's
private key (sourced from the local keyring or a configured signing
endpoint), bundles `signature.bin` and `publisher.key` into the
archive, and uploads the result. Pre-upload, the verb runs the
self-verification chain — exactly what a consumer would run on
download — and aborts if any step fails. Upload requires
authentication against the registry's account model, which is a
registry-implementation concern outside this spec.

> **Implementation status (V1.0 in progress).** The build, hash,
> sign, and pre-upload self-verification steps are wired in the
> bootstrap; the verb currently writes the finished archive locally
> and reports the registry upload as pending. The upload step lands
> with the registry's HTTPS wire surface.

`edda publish` is distinct from `structmap --publish`. The latter
(see [07-distribution.md §10](07-distribution.md)) is the dev-tree to
public-tree sanitization workflow for source distribution; the
former is the registry publish for binary rune distribution. Both
names are kept because both flows are real, and the leading verb
disambiguates them.

### 8.5 `edda contract-diff <a> <b>`

Produces a human-readable diff between two rune versions or between
a rune and its successor candidate. The diff covers added, removed,
and changed stable items in `surface/`; added and removed
effect-row entries; changed refinement clauses; changed graded
bounds. Output is grouped by SemVer impact: patch-class changes,
minor-class changes, major-class changes. The verb is what a
publisher consults before deciding the version bump for a release;
it is what a consumer consults to understand what `edda update`
would accept or reject. [03-verification.md](03-verification.md) §8
describes a finer-grained, per-function contract-hash delta query
under the same verb name and an `inspect.contract_diff` MCP
counterpart — that surface is still-roadmapped target design with no
implementation; this rune-level diff is what
`edda contract-diff` actually does today.

### 8.6 `edda why <name>`

Prints the transitive provenance of a dependency: who in the project
imports it directly, which dependencies transitively pull it in, and
what capabilities and effects it brings into the consumer's effect
ceiling. The verb is the consumer's tool for understanding why a
particular rune is in the lockfile. For an unexpectedly heavy
dependency or one whose effect ceiling is broader than expected,
`edda why` traces the chain to the direct consumer that pulled it.

---

## 9. Security thesis

Mímir's structural mitigations against the supply-chain attack
surface that has dominated other package ecosystems are listed
below as a side-by-side comparison. Each row pairs a class of attack
that has cost the wider ecosystem real money and effort with the
Edda mechanism that makes the attack mechanically detectable or
impossible.

| Attack class | npm-style outcome | Edda's structural mitigation |
|---|---|---|
| `postinstall` script execution | Arbitrary code at install time | No install-time code execution. `.rune` is data + MIR + objects; only the compiler ever touches its contents. |
| Maintainer pushes a malicious update | Silent capability creep until exfiltration | `surface_hash` and `effect_hash` are mechanical. New capability use produces a diff `edda update` rejects under `max_effects`. |
| Compromised registry serves bad bytes | Consumer trusts whatever bytes arrive | Lockfile `rune_hash` is authoritative. The registry is a hint; the bytes are verified before they touch the build. |
| Typosquatting / dependency confusion | Similarly-named package installs silently | Publisher key pinned per dep after first `add`. A different key (different publisher) is rejected without manual acceptance. |
| Transitive trust collapse | One compromised transitive dep cascades | Lockfile `deps` is flat. Every transitive rune pins its own hashes, publisher, and signature; transitive trust is per-leaf. |
| Resource exhaustion at install | Malicious package runs the CPU dry | Resolution is parsing and type-checking; no execution, no ambient `Allocator`. The compiler has bounded effect rows everywhere. |
| SemVer dishonesty | Patch claim hides breaking change | `surface_hash` change with same major version is mechanically detected. The publisher's claimed version is checked against the hash diff. |
| Capability escalation in update | New `Filesystem` use ships under a patch | `max_effects` is a ceiling. An update that would push the union past the ceiling raises `capability_escalation` and is rejected. |
| Lockfile tampering | Hand-edits go unnoticed | `lockfile_hash` trailer rejects mismatched lockfiles at the next build. |
| Compiler-version drift | Same source produces different bytes | `manifest.toml` records `compiler = "edda <major.minor>"`. Patch-level reproducibility is enforced by the self-hosting test suite. |

The locked diagnostic class for ceiling violations is
`capability_escalation`. The locked diagnostic class for lockfile
edits that invalidate the trailer is `lockfile_tampered`. Both are
listed in the diagnostic-class enum maintained in
[03-verification.md](03-verification.md); adding either is a minor
language-version bump, removing or renumbering either is breaking.

The security thesis is not that Edda is unbreakable. A consumer who
runs `edda update --accept-surface-change --accept-publisher-rotation`
on every dependency every morning has opted out of every mitigation
this chapter offers. The thesis is that the *default* state — first
install pins everything, subsequent operations verify against pins,
edits to pins are visible in version control — makes the common
classes of supply-chain failure mechanically detectable. Mechanical
detection is the property that scales; honor-based trust does not.

---

## 10. Reserved for post-V1.0

The V1.0 surface ships the chapter above. Several adjacent
capabilities are sketched but deferred to post-V1.0; they are listed
here so that V1.0 reads as a deliberate subset.

- **Registry server implementation.** The reference Mímir registry
  lives in a separate repository and is implemented after the
  client-side surface stabilizes. V1.0's `edda publish` targets the
  registry's wire surface; the registry's storage model, account
  system, mirror federation, and revocation flow are reserved.
- **Source runes.** A sibling `<name>-<version>.rune.src` carrying
  `.ea` source files for consumers that want to read or audit the
  implementation. The container format reuses the tar.zst rules; the
  build-side emission is reserved.
- **Advisory feed.** A registry-served stream of known-bad hashes
  and recommended upgrade paths, consumed by `edda audit --advisories`.
  The feed format and trust model are reserved; V1.0 ships `audit`
  without the advisory hookup.
- **Mirror federation beyond `source` field.** V1.0's lockfile
  records a single `source` per entry, extensible to `file://` and
  `git+ssh://` schemes. Multi-source fallback (try the corporate
  mirror, fall back to upstream) is reserved.
- **Yank / unpublish workflow.** Versions remain available once
  published in V1.0. The yank mechanism, including its interaction
  with lockfiles that pin yanked versions, is reserved.
- **Cross-registry signing.** A single publisher key per dependency
  in V1.0. Cross-signing — multiple keys vouching for the same
  archive — is reserved.

The line between V1.0 and post-V1.0 for this chapter is drawn so that
V1.0 covers what a closed group of authors and consumers need to ship
verified runes against a single registry. Post-V1.0 covers the
surface required for ecosystem-scale operation: many publishers, many
registries, advisory coordination, key rotation at scale.
