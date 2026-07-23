---
name: edda-authoring
description: Special operations for Edda — verification tooling (edda build/check semantics, contract-diff), property-based testing, the comptime built-in table, capability typestate machines, structured concurrency and std.task, Subprocess/ChildSpec and per-target availability, full stability rules, the attribute family, and distribution (package.toml, .rune, content addressing). Load when a task touches tooling, verification workflows, or language features beyond everyday syntax.
---

# Edda authoring — special operations

Everyday Edda syntax lives in the language reference, `AGENTS.md`
(https://edda-lang.org/AGENTS.md), which your harness already loads. This skill
is the tier above it — for operations beyond ordinary syntax.

1. **Read the authoring guide** — https://edda-lang.org/guide.md — the
   special-operations reference. Every feature carries a status tag
   (**[shipped]** / **[partial]** / **[design]**); trust the tags and do not
   write code that depends on a **[design]** feature.
2. **Read the worked examples before inventing a form.** They are a buildable
   package under `docs/authoring/examples/` in the source repo
   (https://github.com/edda-lang/edda/tree/main/docs/authoring/examples); every
   `src/*.ea` file compiles with the current toolchain. Open the one matching
   your task — `config`, `consume`, `dispatch`, `option`, or `tree`.

If the guide and the compiler ever disagree, the compiler is right: `edda build`
is the source of truth.
