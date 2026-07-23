import sys, os, json, tempfile


def _env_list(name, default):
    return tuple(x.strip() for x in os.environ.get(name, default).split(",") if x.strip())


SUBTREES = _env_list("EDDA_TOON_SUBTREES", "compiler,std,runes")
ROOT_MARKERS = _env_list("EDDA_TOON_ROOT_MARKER", "CLAUDE.md,.git,AGENTS.md,package.toml")


def _protocol():
    for a in sys.argv[1:]:
        if a.startswith("--protocol="):
            return a.split("=", 1)[1].strip().lower()
    return os.environ.get("EDDA_TOON_PROTOCOL", "claude").strip().lower()


PROTOCOL = _protocol()

READ_THRESHOLD = int(os.environ.get("EDDA_TOON_READ_THRESHOLD", "400"))
READ_WINDOW = int(os.environ.get("EDDA_TOON_READ_WINDOW", "400"))
READ_GATE = os.environ.get("EDDA_TOON_READ_GATE", "1") != "0"


def count_lines(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def ledger_path(sid):
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in sid)
    return os.path.join(tempfile.gettempdir(), "edda_toon_ledger", safe + ".txt")


def load_ledger(sid):
    p = ledger_path(sid)
    if not os.path.exists(p):
        return set()
    with open(p, "r", encoding="utf-8") as f:
        return set(l.strip() for l in f if l.strip())


def find_repo_root(d):
    for marker in ROOT_MARKERS:
        cur = d
        while True:
            if os.path.exists(os.path.join(cur, marker)):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    return None


def subtree_root(target_dir, repo_root):
    if not repo_root:
        return None
    rel = os.path.relpath(target_dir, repo_root)
    if rel == "." or rel.startswith(".."):
        return None
    first = rel.split(os.sep)[0]
    if first in SUBTREES:
        return os.path.join(repo_root, first)
    return None


def deny(reason):
    if PROTOCOL == "claude":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))
        sys.exit(0)
    sys.stderr.write(reason + "\n")
    sys.exit(2)


def ancestor_chain(target_dir, root):
    if not root:
        return [target_dir]
    rel = os.path.relpath(target_dir, root)
    parts = [] if rel == "." else rel.split(os.sep)
    chain, cur = [root], root
    for p in parts:
        cur = os.path.join(cur, p)
        chain.append(cur)
    return chain


def main():
    data = json.loads(sys.stdin.read())
    ti = data.get("tool_input") or data.get("toolInput") or data.get("input") or {}
    fp = ti.get("file_path") or ti.get("path") or ti.get("filePath") or data.get("file_path")
    if not fp or not fp.lower().endswith(".ea"):
        return
    sid = data.get("session_id") or data.get("sessionId") or "default"
    target_dir = os.path.abspath(os.path.dirname(fp))
    repo_root = find_repo_root(target_dir)
    anchor = subtree_root(target_dir, repo_root) or repo_root
    root = repo_root or anchor
    ledger = load_ledger(sid)

    missing = []
    for d in ancestor_chain(target_dir, anchor):
        toon = os.path.join(d, "index.toon")
        if os.path.exists(toon) and os.path.normcase(os.path.abspath(d)) not in ledger:
            missing.append(toon)

    if missing:
        listed = "\n".join(
            "  - " + (os.path.relpath(m, root) if root else m) for m in missing
        )
        deny(
            "Edda reading discipline (see AGENTS.md): read these compiler-emitted index.toon "
            "structure maps in path order BEFORE opening "
            + os.path.basename(fp) + ":\n" + listed
            + "\nThey carry the signatures, refinements, stability, and call graph for this "
            "area and are always in sync with source. Read them top-down (subtree root "
            "first), then retry."
        )

    if READ_GATE and (data.get("tool_name") or data.get("toolName") or "") == "Read" and os.path.exists(fp):
        nlines = count_lines(fp)
        if nlines > READ_THRESHOLD:
            offset, limit = ti.get("offset"), ti.get("limit")
            bounded = (
                isinstance(offset, int)
                and isinstance(limit, int)
                and limit <= READ_WINDOW
            )
            if not bounded:
                deny(
                    "Edda focused-read gate (see AGENTS.md): "
                    + os.path.basename(fp) + " is " + str(nlines) + " lines (> "
                    + str(READ_THRESHOLD) + "); read a bounded span, not the whole file. "
                    "The index.toon you just read lists every item's [line,end] span "
                    "(with its signature, effect row, and calls): Read with offset=<line> "
                    "limit=<end - line + 1>. The [line,end] span already INCLUDES any "
                    "attribute lines above the function, so no upward slack is needed. The "
                    "file preamble (module/import/spec/derive) is lines 1..<smallest item "
                    "line>. For a genuine whole-file pass, page through in <= "
                    + str(READ_WINDOW) + "-line windows. Pass both offset and limit "
                    "(limit <= " + str(READ_WINDOW) + ")."
                )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
