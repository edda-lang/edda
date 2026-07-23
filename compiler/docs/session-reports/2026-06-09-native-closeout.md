# Session report — native issue-queue closeout (2026-06-09)

Agent-authored report on a session spent working the Tier 1/2/3 `component:native`
issues that are fully isolated to this repository. Includes a self-assessment of
effectiveness working *in Edda*, since this repo is the Edda self-hosting compiler.

## What was done

**Implemented + closed (2):**
- **#283** — `@target_requires` wired end-to-end as *absent + call-site* gating.
  New check pass `types.check.pass.avail.gate`: collects `@target_requires(T)`
  items unavailable on the build triple, skips their own bodies, emits a
  call-site diagnostic. Replaced the prior decl-site semantics (which
  contradicted "the function does not exist on unsupported targets" and broke
  composition with `comptime if target.supports(T)`).
- **#307** — nested or-patterns with binders now lower. Generalized #221's
  arm-level `emit_or_alternatives` into a `bind_or_pattern` decision sub-tree at
  any projected sub-scrutinee, converging on a local join block.

**Verified already-complete + closed (3):** the issues were stale — the work had
landed (mostly alongside the CodeView spine) but the trackers were never updated.
- **#260** line tables (MIR origin → LIR `op.origin` → `record_line` side-table → CodeView).
- **#261** CodeView functions + line subsections.
- **#285** frame-slot locals (`S_LOCAL` + `S_DEFRANGE_FRAMEPOINTER_REL`).

**Assessed + deferred, with precise implementation plans posted (open):**
#205 (comptime lowering), #309 (capability-typestate), #287 (aggregate `.debug$T`),
#288, #263, #262, #207, #322, #286, #214, #247, #200, #201, plus the debugger
epic #264/#265/#266/#267/#268. Epic status sweeps on #259 and #190.

The deferrals fall into three honest buckets:
1. **Cross-component** (not native-isolated): #309 (stdlib ordered-protocol surface
   / redundant with the linear pass), #266 (a new `Debugger` capability needs a
   stdlib nominal type + an extension to the *locked 17-capability set*).
2. **New cross-phase / cross-member infrastructure**, large and blind: #205
   (node-keyed comptime store + cteval→compile→mir threading), #207/#322 (a
   resolve+types+hir closure-conversion frontend pass), #214 (raw-alloc extern
   recognition through resolve/lower), #286 (object-emit format dispatch).
3. **Correctly held until stage-C makes them safe**: #287-aggregate / #288 / #263 /
   #262 (byte-exact debug records I won't guess), #247 (premature perf-opt of
   passes that don't run yet, with real blind-miscompile risk).

## The dominant constraint: check-only verification

The single most important factor in every routing decision was **not the Edda
language** but a toolchain fact: the bootstrap compiler type-checks our native
`.ea` passes but never *executes* them. A native semantic/codegen pass can be
written and made `edda check`-clean, but its runtime behaviour is unobservable
until "stage C" (a native self-build), which is itself gated elsewhere.

This is why the session splits so cleanly into "implemented" vs "deferred." Where
a change is *correct by construction* — mirroring an existing, accepted pass, or
verifying an existing implementation against its done-when — I shipped or closed
it. Where a change is a large blind addition (new codegen bytes, optimizer
rewrites, cross-phase threading) whose correctness `edda check` cannot confirm, I
judged that shipping it unverified risks a silent miscompile worse than leaving a
well-documented, ready-to-implement plan. That judgment, applied honestly, is what
produced ~13 deferrals — not a lack of language facility.

## Effectiveness working in Edda: 8/10

**What made me effective (Edda-specific assets):**
- **The derived `index.toon` structure map is the best navigation aid I have used
  in any codebase.** Signatures + effect rows + `calls` + refinements per directory
  let me locate exact sites — the `validate.ea` `@target_requires` machinery, the
  `capability.supports` table, the `modes.ea` walker, the `record_line` producer,
  the `cv_type_for` primitive mapper — almost always *before* opening source. For
  an agent, "the leaf is canonical, the map is checked fact" pays off enormously:
  it collapses search and resists the stale-comment poisoning that plagues prose
  navigation.
- **Mirrorability.** Edda's regularity (every walker threads the same
  `(file, …, diags, allocator)` shape; effect rows are explicit and copyable; spec
  mangling is deterministic) meant I could clone `modes.ea` into a correct ~480-line
  capability walker, and `emit_or_alternatives` into `bind_or_pattern`, essentially
  first-try. Explicit effect rows in particular make "what can this function do" a
  read, not an investigation.
- **The verification gates caught my mistakes** — `termination_unproven` on a
  recursive pure helper, the structure-budget ceiling on a too-large new file.
  These are real correctness/maintainability signals, not noise.

**What cost me (the −2), and how much is Edda vs. the harness:**
- **Reactive gates + a ~90s no-cache check cycle.** The structure-budget gate
  (Gate A 6000-token per-node ceiling) and `filename_encodes_hierarchy` only fire
  *after* you write the file, and each retry is a full ~90s rebuild with zero
  inter-run caching. #283 cost two extra cycles purely on file placement
  (`target_gate.ea` underscore → must be a directory; the file blew the per-node
  budget → relocate to `check/pass/avail/gate.ea`). This is the main efficiency
  tax, and it is squarely an Edda/toolchain property: the discipline is good, but
  it is *discovered late*, so the skill is to anticipate the gate before writing.
  I improved within the session (#307 landed clean first try by placing it inside
  the existing dense file rather than adding a new node).
- **Termination obligations on pure recursion.** A recursive pure helper with no
  `decreases`/`divergence` is rejected; the sibling walkers admitted `divergence`
  and I didn't carry it. Correct of the language; a first-pass miss on my part.
- **Mode/`take` discipline** required care (borrow vs `take`, mode keywords barred
  in struct literals), but caused no actual errors this session — the prior memory
  notes on these paid off.

**Net.** Edda was a net *accelerant* for the work I could verify: the structure
map and the language's regularity made navigation and mirror-implementation fast
and reliable. The ceiling on this session's throughput was not Edda's
expressiveness or my fluency in it — it was the inability to execute native passes
to validate deep changes, which correctly converted roughly two-thirds of the
queue from "implement" into "assess and document." I'd rate my Edda effectiveness
8/10: high navigational and implementation competence, a small recurring tax on
anticipating the reactive structure/termination gates, and a hard external ceiling
(check-only) that bounded how much new codegen I was willing to ship blind.
