#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preamble.py — SessionStart-хук. Агент получает не голую задачу, а телеметрию
хранилища: ветка, перепись страниц по ярусам доверия, состояние fail-closed
конфигурации, карантины, последние операции, активные learnings.

stdout этого скрипта Claude Code кладёт в контекст сессии. Должен отрабатывать
быстро (<1 c) и переживать любое состояние волта. Только stdlib.
"""
import json, os, pathlib, re, shutil, signal, subprocess, sys
try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):
    pass

ROOT = pathlib.Path(os.environ.get("VAULT", ".")).resolve()

def sh(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5, cwd=ROOT)
        # tools (e.g. timelayer-verifier) print usage/help to stderr; capability
        # probes must see both streams, matching notary.py's detection.
        return (r.stdout + r.stderr).strip()
    except Exception:
        return ""

out = ["=== BRAIN PREAMBLE — телеметрия волта ==="]

# --- git ---------------------------------------------------------------
branch = sh("git rev-parse --abbrev-ref HEAD") or "не git-репозиторий"
dirty = sh("git status --porcelain") if branch != "не git-репозиторий" else ""
n_dirty = len(dirty.splitlines()) if dirty else 0
out.append(f"git: ветка {branch}, незакоммичено файлов: {n_dirty}")

# --- перепись wiki по ярусам доверия ------------------------------------
tiers = {"trusted": 0, "trusted-mechanical": 0, "unverified": 0, "без-статуса": 0}
wiki = ROOT / "wiki"
rx = re.compile(r"^status:\s*([\w-]+)", re.M)
if wiki.exists():
    for p in wiki.rglob("*.md"):
        if p.name in ("index.md", "log.md", "learnings.md", "learnings-quarantine.md") \
           or "_templates" in p.parts:
            continue
        m = rx.search(p.read_text(encoding="utf-8", errors="replace")[:2000])
        tiers[m.group(1) if m and m.group(1) in tiers else "без-статуса"] += 1
out.append(f"wiki: trusted {tiers['trusted']} · trusted-mechanical {tiers['trusted-mechanical']}"
           f" · unverified {tiers['unverified']}"
           + (f" · без статуса {tiers['без-статуса']} (!)" if tiers["без-статуса"] else ""))

# --- карантин страниц ----------------------------------------------------
uq = ROOT / "unverified"
if uq.exists():
    files = list(uq.rglob("*.md"))
    if files:
        out.append(f"unverified/ (карантин страниц): {len(files)} шт. — "
                   + ", ".join(f.name for f in files[:5]) + ("…" if len(files) > 5 else ""))

# --- карантин источников (guard) ----------------------------------------
gd = ROOT / "receipts" / "guard"
if gd.exists():
    unacked = []
    for vp in gd.glob("*.guard.json"):
        try:
            v = json.loads(vp.read_text(encoding="utf-8"))
            if v.get("verdict") == "SUSPECT" and not v.get("ack"):
                unacked.append(pathlib.Path(v.get("path", vp.stem)).name)
        except Exception:
            pass
    if unacked:
        out.append(f"⚠ guard: SUSPECT-источники без ack человека: {', '.join(unacked[:5])}"
                   " — читать их нельзя, пока человек не подтвердит (ingest_guard.py ack).")

# --- fail-closed конфигурация: чего не хватает до полного trusted --------
judge = bool(os.environ.get("TL_JUDGE_CMD"))
l4 = bool(os.environ.get("TL_INJECTION_CMD"))
ver = os.environ.get("TL_VERIFIER") or shutil.which("timelayer-verifier")
expect = False
if ver:
    expect = "--expect" in sh(f'"{ver}" verify --help') or "--expect" in sh(f'"{ver}" --help')
cfg = []
cfg.append("судья " + ("настроен" if judge else "НЕ настроен (TL_JUDGE_CMD) → потолок trusted-mechanical"))
cfg.append("verifier " + ("с --expect" if expect else
           ("есть, но без --expect (README: нужен v2.0.0+)" if ver else "не найден (TL_VERIFIER/PATH)"))
           + ("" if expect else " → потолок trusted-mechanical"))
cfg.append("L4-классификатор инъекций " + ("вкл" if l4 else "не настроен (TL_INJECTION_CMD), работают L1–L3"))
out.append("конфиг: " + " · ".join(cfg))

# --- последние операции ---------------------------------------------------
log = wiki / "log.md"
if log.exists():
    lines = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines()
             if l.startswith("## [")]
    if lines:
        out.append("последние операции: " + " | ".join(l[3:70] for l in lines[-3:]))

# --- learnings: активные и карантин ---------------------------------------
def count_entries(p):
    if not p.exists():
        return 0, []
    heads, fenced = [], False
    for l in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if l.startswith("```"):
            fenced = not fenced
        elif not fenced and l.startswith("### "):
            heads.append(l[4:])
    return len(heads), heads

n_act, _ = count_entries(wiki / "learnings.md")
n_q, qheads = count_entries(wiki / "learnings-quarantine.md")
line = f"learnings: активных {n_act} · в карантине {n_q}"
if qheads:
    line += " (" + "; ".join(h[:40] for h in qheads[:3]) + ")"
out.append(line)
out.append("Правила: CLAUDE.md — конституция; raw/ читать только через ingest_guard.py read; "
           "trusted ставит только notary.py; вердикт судьи — рекомендация, решает человек.")
out.append("=== конец преамбулы ===")

print("\n".join(out))
sys.exit(0)
