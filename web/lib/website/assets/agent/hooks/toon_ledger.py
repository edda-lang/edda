import sys, os, json, tempfile


def ledger_path(sid):
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in sid)
    return os.path.join(tempfile.gettempdir(), "edda_toon_ledger", safe + ".txt")


def main():
    data = json.loads(sys.stdin.read())
    fp = (data.get("tool_input") or {}).get("file_path")
    if not fp or os.path.basename(fp).lower() != "index.toon":
        return
    sid = data.get("session_id") or "default"
    d = os.path.normcase(os.path.abspath(os.path.dirname(fp)))
    ledger = ledger_path(sid)
    os.makedirs(os.path.dirname(ledger), exist_ok=True)
    existing = set()
    if os.path.exists(ledger):
        with open(ledger, "r", encoding="utf-8") as f:
            existing = set(l.strip() for l in f if l.strip())
    if d not in existing:
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(d + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
