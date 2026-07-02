#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
careful.py — PreToolUse-хук. Механическое исполнение «железных правил» CLAUDE.md.

До сих пор правила №1–№3 (raw/ неприкосновенен, trusted ставит только notary.py,
receipts/ не трогать) жили только в промпте. Этот хук делает их свойством
инструмента, а не памяти модели. Работает даже под --dangerously-skip-permissions.

Протокол Claude Code: JSON на stdin; exit 0 = пропустить, exit 2 = заблокировать
(stderr уходит модели как объяснение). Никакого JSON на stdout при exit 2.

Белый список — в духе /careful: rm -rf по мусорным папкам проходит молча.
"""
import json, re, sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # не смогли разобрать — не блокируем вслепую

tool = data.get("tool_name", "")
ti = data.get("tool_input", {}) or {}

def block(msg: str):
    sys.stderr.write("BLOCKED by careful.py: " + msg + "\n")
    sys.exit(2)

# ---------- файловые инструменты: Edit / Write / Read -----------------------
if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
    p = str(ti.get("file_path", ""))
    if re.search(r"(^|/)receipts/", p):
        block("правило №3: receipts/ — машинный провенанс, пишет только notary.py.")
    if re.search(r"(^|/)raw/", p):
        block("правило №1: raw/ неприкосновенен. Источники только читаются (через ingest_guard.py read).")
    if re.search(r"(^|/)wiki/log\.md$", p) and tool != "Write":
        pass  # append через Edit допустим; переписывание истории ловим на Bash-уровне
    # запрет руками выставлять доверие в frontmatter
    new_text = str(ti.get("new_string", "")) + str(ti.get("content", ""))
    if re.search(r"status:\s*trusted", new_text):
        block("правило №2: status: trusted / trusted-mechanical выставляет только notary.py (verify). "
              "Пиши status: unverified и запускай проверку.")
    if re.search(r"(receipt_ref|bound_hash)\s*:", new_text):
        block("правило №3: поля receipt_ref / bound_hash пишет только скрипт.")
    sys.exit(0)

if tool == "Read":
    p = str(ti.get("file_path", ""))
    if re.search(r"(^|/)raw/", p):
        block("дисциплина чтения (L1): источники из raw/ читаются только через "
              "`python3 scripts/ingest_guard.py read <path>` — с датамаркировкой и подсветкой скрытого. "
              "Прямое чтение недоверенного текста запрещено.")
    sys.exit(0)

# ---------- Bash -------------------------------------------------------------
if tool != "Bash":
    sys.exit(0)

cmd = str(ti.get("command", ""))

# Белый список: молча пропускаем мусорные rm -rf (в духе оригинального /careful)
WHITELIST_RM = re.compile(
    r"rm\s+(-[a-zA-Z]*\s+)*("
    r"(\./)?(outputs|unverified|node_modules|dist|build|__pycache__|\.pytest_cache)(/[^\s;|&]*)?"
    r"|/tmp/[^\s;|&]+"
    r")\s*($|[;|&])"
)
if WHITELIST_RM.search(cmd) and not re.search(r"(^|[\s/])(raw|receipts|wiki)(/|\s|$)", cmd):
    sys.exit(0)

RULES = [
    # (паттерн, сообщение)
    (r"rm\s+(-[a-zA-Z]*\s+)*[^\s]*(^|/)?(raw|receipts)(/|\s|$)",
     "правило №1/№3: удаление в raw/ или receipts/ запрещено."),
    (r"(>|>>|\btee\b)\s*[^\s]*(^|/)(raw|receipts)/",
     "правило №1/№3: запись в raw/ или receipts/ запрещена."),
    (r"\b(mv|cp)\b[^\n;|&]*\s[^\s]*(^|/)(raw|receipts)/[^\s]*\s*($|[;|&])",
     "правило №1/№3: перемещение/затирание файлов в raw/ или receipts/ запрещено."),
    (r"\bsed\b[^\n]*-i[^\n]*(raw|receipts)/",
     "правило №1/№3: правка на месте в raw/ или receipts/ запрещена."),
    (r"\bchmod\b[^\n]*(raw|receipts)/",
     "правило №5: права на raw/ и receipts/ — граница по ключам, не обходить."),
    (r"(sed|perl|awk|echo|printf)[^\n]*status:\s*trusted",
     "правило №2: подделка status: trusted через shell запрещена — только notary.py verify."),
    (r"(sed|perl|awk)[^\n]*-i[^\n]*wiki/log\.md",
     "wiki/log.md — append-only. Историю операций не переписываем."),
    (r"rm\s+(-[a-zA-Z]*\s+)*(/|\$HOME|~)\s*($|[;|&])",
     "rm -rf по корню/дому. Нет."),
    (r"git\s+push\s+[^\n]*--force",
     "force-push по волту запрещён: история — часть доказуемости."),
    (r"git\s+clean\s+-[a-zA-Z]*x",
     "git clean -x может снести receipts/ и unverified/. Запрещено."),
    (r"\bDROP\s+TABLE\b|\bTRUNCATE\b",
     "деструктивный SQL в волте. Нет."),
    (r"curl[^\n]*\|\s*(ba)?sh|wget[^\n]*\|\s*(ba)?sh",
     "pipe-to-shell из сети в нотариальном хранилище запрещён."),
]

for pat, msg in RULES:
    if re.search(pat, cmd, re.IGNORECASE):
        block(msg + "  Команда: " + cmd[:120])

# Чтение raw/ в обход датамаркировки (cat/head/tail/less)
if re.search(r"\b(cat|head|tail|less|more)\b[^\n;|&]*(^|[\s'\"])raw/", cmd) \
   and "ingest_guard" not in cmd:
    block("дисциплина чтения (L1): raw/ читаем только через ingest_guard.py read — "
          "иначе недоверенный текст попадает в контекст без маркировки.")

sys.exit(0)
