#!/usr/bin/env python3
"""
notary.py — нотариальный слой корректности для LLM Knowledge Base.

Зависимости:  pip install pyyaml          # всё остальное — стандартная библиотека
Окружение:    TIMELAYER_TOKEN  — твой API-токен TimeLayer (узкий, отдельный)
              VAULT            — корень волта (по умолчанию текущая папка)
              TL_VERIFIER      — путь к бинарю timelayer-verifier (по умолчанию из PATH)
              TL_JUDGE_CMD     — судья смысла: команда stdin=промпт → stdout=JSON
                                 (референсные обёртки: scripts/judges/)
              TL_JUDGE_K       — голосов судьи на утверждение (по умолчанию 5)

Команды:
  python notary.py init [dir]               # развернуть структуру волта (кросс-платформенно)
  python notary.py hash <raw-file>          # sha256 источника (для указателей в wiki)
  python notary.py ingest-source <raw-file> # хеш + квитанция источника  (ступень 1)
  python notary.py verify <wiki-note.md>     # grounding + квитанция + ворота A  (ступени 3–5)
  python notary.py verify-all                # то же по всем страницам wiki/
                     [--mechanical-only]     # явное согласие на прогон без судьи
  python notary.py audit <wiki-note.md>      # ворота B: снять trusted, если изменено
  python notary.py audit-all

╔══════════════════════════════════════════════════════════════════════════╗
║  РАБОТАЕТ ИЗ КОРОБКИ. Контракт TimeLayer подтверждён на живом API:          ║
║    • POST /v1/notarize  body {"action_hex": "<sha256 hex>"}                 ║
║      -> {"cert_hex": "...", "bundle_hex": "..."}   (notarized_at НЕ шлётся) ║
║    • .tlcert/.tlbundle — СЫРЫЕ БАЙТЫ (bytes.fromhex), не hex-текст.         ║
║      timelayer-verifier verify cert.tlcert bundle.tlbundle -> "VALID FINAL".║
║                                                                            ║
║  ОПЦИОНАЛЬНО подключить:                                                    ║
║   1. Судья смысловых утверждений — задай TL_JUDGE_CMD (команда: stdin=промпт║
║      -> stdout=JSON). Бери ДРУГОЕ семейство моделей, чем писало вики        ║
║      (декорреляция, §П5). Без судьи смысловые утверждения = INSUFFICIENT    ║
║      (fail-closed); числа/цитаты проверяются механически и без него.        ║
║   2. (опц.) decompose() — дефолт разбивает по предложениям с указателем;    ║
║      для атомарности подключи LLM-декомпозицию.                             ║
╚══════════════════════════════════════════════════════════════════════════╝

Честный потолок (§18): нотариат гарантирует, что проверка случилась, что она
неподделываема и привязана к этим байтам — но НЕ что содержимое истинно.
Гарантия корректности ровно настолько хороша, насколько хорош judge_once и
механические проверки. Мусор в raw/ пройдёт как заверенный мусор.
"""

from __future__ import annotations   # PEP 604 (`dict | None`) в аннотациях — иначе Python 3.9
                                      # падает криптичным TypeError без намёка на причину

import os, re, sys, json, time, shutil, hashlib, subprocess, argparse, pathlib
import urllib.request, urllib.error

if sys.version_info < (3, 10):
    print(f"notary.py: Python {sys.version_info.major}.{sys.version_info.minor} — "
          "поддерживается ограниченно, рекомендован 3.10+ (тесты гоняются на нём).",
          file=sys.stderr)

import yaml

VAULT       = pathlib.Path(os.environ.get("VAULT", ".")).resolve()
WIKI        = VAULT / "wiki"
RECEIPTS    = VAULT / "receipts"
UNVERIFIED  = VAULT / "unverified"
API_NOTARIZE = "https://api.timelayer-os.com/v1/notarize"
VERIFIER    = os.environ.get("TL_VERIFIER", "timelayer-verifier")
SKIP        = {"index.md", "log.md", "status.md", "learnings.md", "learnings-quarantine.md"}  # служебные/живые страницы wiki, не знаниевые

PAGE_TEMPLATE = """---
type: concept
domain: <домен>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: []
status: unverified
tags: []
---

# Название страницы

## Summary

1–2 абзаца обзора. Фактические утверждения привязывай к источникам.

## Key Details

Каждое фактическое утверждение — с указателем на конкретный фрагмент источника:

- Утверждение с числом или фактом. ^[[raw/articles/<файл>.md#L10-L18|src:<имя>@<полный_sha256>]]

Числа, даты и цитаты пиши дословно — их проверяет механическая сверка.

## Related

- [[wiki/related-page]] — почему связано

## Sources

- [[raw/articles/<файл>.md]]@<полный_sha256>
"""

JUDGE_PROMPT = """Ты — придирчивый проверяющий фактов. Тебе дан ФРАГМЕНТ-ИСТОЧНИК и УТВЕРЖДЕНИЕ.
Твоя задача — активно искать причину, по которой утверждение НЕ следует из фрагмента.
Не будь любезным: если поддержки нет, скажи прямо.

Верни СТРОГО JSON без пояснений:
{"cls": "SUPPORTED" | "CONTRADICTED" | "INSUFFICIENT", "span": "<дословная цитата из фрагмента, доказывающая SUPPORTED, иначе пустая строка>"}

Правила:
- SUPPORTED только если можешь привести дословный фрагмент, прямо подтверждающий утверждение. Нет цитаты — не SUPPORTED.
- CONTRADICTED — если фрагмент прямо противоречит утверждению.
- INSUFFICIENT — если фрагмент просто молчит об этом.

ФРАГМЕНТ:
{fragment}

УТВЕРЖДЕНИЕ:
{claim}"""

# ─────────────────────────── базовые помощники ───────────────────────────

def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def now_utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def canon(o) -> bytes:
    return json.dumps(o, sort_keys=True, ensure_ascii=False).encode("utf-8")

def split_frontmatter(text: str):
    """Возвращает (frontmatter_dict, body_str). Хеш считаем по body, не по всему файлу,
       чтобы запись receipt_ref/status в frontmatter не ломала само-инвалидацию."""
    if text.startswith("---"):
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
        if m:
            fm = yaml.safe_load(m.group(1)) or {}
            return fm, m.group(2)
    return {}, text

def write_frontmatter(path: pathlib.Path, updates: dict):
    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    fm.update(updates)
    dumped = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    path.write_text(f"---\n{dumped}\n---\n{body}", encoding="utf-8")

def body_of(path: pathlib.Path) -> str:
    _, body = split_frontmatter(path.read_text(encoding="utf-8"))
    return body.strip()

# ─────────────────────────── клиент TimeLayer ───────────────────────────

def notarize(action_hex: str) -> dict:
    token = os.environ.get("TIMELAYER_TOKEN")
    if not token:
        sys.exit("Нет TIMELAYER_TOKEN в окружении.")
    req = urllib.request.Request(
        API_NOTARIZE,
        data=json.dumps({"action_hex": action_hex}).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        sys.exit(f"API /v1/notarize -> {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")
    except urllib.error.URLError as e:
        sys.exit(f"API /v1/notarize недоступен: {e.reason}")
    # Подтверждено на живом API: ответ = {"cert_hex": "...", "bundle_hex": "..."}.
    # notarized_at API НЕ возвращает (авторитетное время — внутри сертификата).
    return json.loads(body)

def save_receipt(kind: str, stem: str, receipt: dict, bound_hash: str, extra: dict | None = None):
    d = RECEIPTS / kind
    d.mkdir(parents=True, exist_ok=True)
    # Подтверждено на живом API: /v1/notarize отдаёт cert_hex/bundle_hex (hex-строки),
    # а timelayer-verifier ждёт СЫРЫЕ БАЙТЫ в .tlcert/.tlbundle — поэтому декодируем hex.
    (d / f"{stem}.tlcert").write_bytes(bytes.fromhex(receipt.get("cert_hex", "") or ""))
    (d / f"{stem}.tlbundle").write_bytes(bytes.fromhex(receipt.get("bundle_hex", "") or ""))
    # API не возвращает notarized_at (авторитетное время лежит внутри сертификата);
    # тут пишем клиентскую метку «когда заверили» только как удобный человекочитаемый след.
    sidecar = {"bound_hash": bound_hash,
               "notarized_at": receipt.get("notarized_at") or now_utc_iso(),
               **(extra or {})}
    (d / f"{stem}.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2),
                                    encoding="utf-8")

_EXPECT_FLAG = None   # кэш: поддерживает ли установленный verifier привязку к ожидаемому хешу

def _verifier_supports_expect() -> bool:
    """Один раз спрашиваем у verifier его help и ищем флаг привязки (--expect/--expected-digest)."""
    global _EXPECT_FLAG
    if _EXPECT_FLAG is not None:
        return _EXPECT_FLAG
    try:
        h = subprocess.run([VERIFIER, "verify", "--help"],
                           capture_output=True, text=True)
        help_txt = (h.stdout or "") + (h.stderr or "")
    except FileNotFoundError:
        sys.exit(f"Не найден verifier '{VERIFIER}'. Скачай timelayer-verifier и задай TL_VERIFIER.")
    _EXPECT_FLAG = "--expect" if "--expect" in help_txt else ""
    return bool(_EXPECT_FLAG)

def verify_receipt_offline(kind: str, stem: str, expected_hex: str | None = None) -> bool:
    """Проверяет квитанцию офлайн. Если задан expected_hex И verifier умеет --expect —
       квитанция обязана криптографически привязываться именно к этому хешу (fail-closed).
       Если verifier ещё не умеет привязку, expected_hex проверяется на верхнем уровне
       (is_trusted) сверкой bound_hash — это ловит правки тела/источников, но НЕ злонамеренную
       подмену квитанции при наличии ключа записи (граница угрозы — правило №5 в CLAUDE.md:
       доступом управляют ключи). См. ISSUE п.1."""
    d = RECEIPTS / kind
    cert, bundle = d / f"{stem}.tlcert", d / f"{stem}.tlbundle"
    if not cert.exists():
        return False
    args = [VERIFIER, "verify", str(cert), str(bundle)]
    if expected_hex and _verifier_supports_expect():
        args += ["--expect", expected_hex]   # привязка к ожидаемому action_hex (fail-closed)
    try:
        rc = subprocess.run(args, capture_output=True).returncode
        return rc == 0
    except FileNotFoundError:
        sys.exit(f"Не найден verifier '{VERIFIER}'. Скачай timelayer-verifier и задай TL_VERIFIER.")

# ─────────────────── разбор указателей и источников ───────────────────

ANCHOR = re.compile(r"\[\[(raw/[^\|\]]+)\|src:[^@\]]+@([0-9a-fA-F]+)\]\]")

def extract_sources(body: str) -> list[dict]:
    """Детерминированно: все источники с версиями, отсортированы."""
    seen = {(ref, ver) for ref, ver in ANCHOR.findall(body)}
    return sorted(({"ref": ref, "version": ver} for ref, ver in seen),
                  key=lambda s: (s["ref"], s["version"]))

def _within(p: pathlib.Path, root: pathlib.Path) -> bool:
    """True, только если p физически лежит ВНУТРИ root (после резолва симлинков/..)."""
    try:
        rp = p.resolve()
    except Exception:
        return False
    return str(rp).startswith(str(root.resolve()) + os.sep)

def fetch_fragment(ref: str, version: str):
    """Достаёт фрагмент из raw/ по ref (с опц. #Lx-Ly) и сверяет хеш версии источника."""
    m = re.match(r"(.+?)(?:#L(\d+)-L(\d+))?$", ref)
    rel, l1, l2 = m.group(1), m.group(2), m.group(3)
    path = VAULT / rel
    # П4-фикс: якорь обязан указывать ПОД raw/ — иначе `raw/../../secret` уводил чтение
    # за пределы волта (фрагмент мог осесть в evidence_span). Ограничиваем поддеревом raw/.
    if not _within(path, VAULT / "raw") or not path.exists():
        return "", False
    raw_bytes = path.read_bytes()
    src_ok = (sha256_hex(raw_bytes) == version)   # точное сравнение полного sha256
    text = raw_bytes.decode("utf-8", errors="replace")
    if l1 and l2:
        lines = text.splitlines()
        text = "\n".join(lines[int(l1) - 1:int(l2)])
    return text, src_ok

# ─────────────────────── П1: декомпозиция ───────────────────────

def classify_kind(claim_text: str) -> str:
    if re.search(r"[«\"“].+?[»\"”]", claim_text):
        return "quote"
    if re.search(r"\d", claim_text):
        return "number"
    return "semantic"

def decompose(body: str) -> list[dict]:
    """ДЕФОЛТ: одно утверждение на каждый указатель в строке. Текст утверждения —
       строка без указателей. Для более атомарного разбиения подключи LLM."""
    claims = []
    for line in body.splitlines():
        anchors = ANCHOR.findall(line)
        if not anchors:
            continue
        text = ANCHOR.sub("", line).replace("^", "").strip(" -•\t")
        for ref, ver in anchors:
            claims.append({"text": text, "source_ref": ref, "source_version": ver,
                           "kind": classify_kind(text)})
    return claims

# ─────────────── П3: механические проверки (без модели) ───────────────

NUM = re.compile(r"-?\d+(?:[.,]\d+)?")

def _nums(s: str) -> set[float]:
    out = set()
    for tok in NUM.findall(s.replace("\u00a0", " ").replace(" ", "")):
        try:
            out.add(float(tok.replace(",", ".")))
        except ValueError:
            pass
    return out

def check_number(claim, frag) -> dict:
    want, have = _nums(claim["text"]), _nums(frag)
    ok = all(any(abs(w - h) <= 1e-9 or (h and abs(w - h) / abs(h) < 1e-4) for h in have)
             for w in want) if want else False
    return {"classification": "SUPPORTED" if ok else "INSUFFICIENT",
            "evidence_span": frag[:160]}

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()

def check_quote(claim, frag) -> dict:
    quoted = re.findall(r"[«\"“](.+?)[»\"”]", claim["text"])
    ok = all(_norm(q) in _norm(frag) for q in quoted) if quoted else False
    return {"classification": "SUPPORTED" if ok else "CONTRADICTED",
            "evidence_span": (quoted[0] if quoted else "")[:160]}

def check_structure(claim, frag) -> dict:
    return {"classification": "SUPPORTED" if frag.strip() else "INSUFFICIENT",
            "evidence_span": ""}

# ─────────── П4–П5: судья для смысловых утверждений ───────────

def _build_judge_prompt(claim_text: str, fragment: str) -> str:
    # NB: НЕ str.format — в JUDGE_PROMPT есть литеральные {…} (пример JSON), .format об них падает.
    return JUDGE_PROMPT.replace("{fragment}", fragment).replace("{claim}", claim_text)

def judge_once(claim_text: str, fragment: str) -> dict:
    """Судья для смысловых утверждений. Возвращает {"cls": ..., "span": ...}.

    По умолчанию вызывает внешнюю команду из TL_JUDGE_CMD: команда читает промпт со stdin
    и печатает JSON в stdout. Возьми ДРУГОЕ семейство моделей, чем писало вики (декорреляция,
    §П5) — например свой скрипт поверх стороннего провайдера.
        export TL_JUDGE_CMD='python my_judge.py'   # читает stdin → печатает {"cls":...,"span":...}

    Если TL_JUDGE_CMD не задан — судьи нет: смысловое утверждение считаем INSUFFICIENT
    (fail-closed). Тогда страница не получит trusted, пока ты не подключишь судью или не
    подтвердишь её вручную. Механические утверждения (числа/цитаты) работают и без судьи."""
    cmd = os.environ.get("TL_JUDGE_CMD")
    if not cmd:
        return {"cls": "INSUFFICIENT", "span": ""}
    prompt = _build_judge_prompt(claim_text, fragment)
    try:
        out = subprocess.run(cmd, shell=True, input=prompt,
                             capture_output=True, text=True, timeout=120).stdout
        m = re.search(r"\{.*\}", out, re.DOTALL)
        v = json.loads(m.group(0)) if m else {}
    except Exception:
        # _err: сбой судьи (таймаут/падение/мусор вместо JSON), а не смысловой вердикт.
        # Такой голос НЕ кэшируется — иначе временный сбой сети застынет как INSUFFICIENT.
        return {"cls": "INSUFFICIENT", "span": "", "_err": True}
    cls = v.get("cls")
    if cls not in ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT"):
        return {"cls": "INSUFFICIENT", "span": "", "_err": True}
    return {"cls": cls, "span": v.get("span", "") or ""}

# ─────────── кэш вердиктов судьи (receipts/judge/) ───────────
# Ключ = sha256(судья + утверждение + фрагмент): смена текста утверждения, версии источника
# или команды судьи меняет ключ и вызывает честный пересуд. Неизменная пара не пересуживается —
# повторный verify-all стоит секунды вместо часов. Один файл на вердикт: параллельные verify
# не конфликтуют (write-once по ключу, в духе append-only receipts/).

def _judge_cache_path(claim_text: str, fragment: str) -> pathlib.Path:
    ident = os.environ.get("TL_JUDGE_CMD", "")
    key = sha256_hex("\x00".join((ident, claim_text, fragment)).encode("utf-8"))
    return RECEIPTS / "judge" / f"{key}.json"

def check_with_judge(claim, frag, k: int | None = None) -> dict:
    """П5: k сэмплов, единогласие + принудительная цитата-в-фрагменте; иначе эскалация.
    Вердикт по неизменной паре (утверждение, фрагмент) берётся из кэша receipts/judge/.
    k настраивается через TL_JUDGE_K (голоса — самая дорогая часть verify)."""
    if k is None:
        try:
            k = max(1, int(os.environ.get("TL_JUDGE_K", "5") or "5"))
        except ValueError:
            k = 5
    cpath = _judge_cache_path(claim["text"], frag)
    if cpath.exists():
        try:
            c = json.loads(cpath.read_text(encoding="utf-8"))
            return {"classification": c["classification"],
                    "evidence_span": c.get("evidence_span", ""),
                    "agreement": c.get("agreement", "") + "+cache"}
        except Exception:
            pass                                     # битый кэш-файл — пересуживаем
    votes = [judge_once(claim["text"], frag) for _ in range(k)]
    classes = {v.get("cls") for v in votes}
    if classes == {"SUPPORTED"} and all(_norm(v.get("span", "")) in _norm(frag) and v.get("span")
                                        for v in votes):
        result = {"classification": "SUPPORTED", "evidence_span": votes[0]["span"][:160],
                  "agreement": f"{k}/{k}"}
    elif "CONTRADICTED" in classes:
        result = {"classification": "CONTRADICTED", "evidence_span": "", "agreement": "split"}
    else:
        result = {"classification": "INSUFFICIENT", "evidence_span": "", "agreement": "split"}
    if not any(v.get("_err") for v in votes):        # сбойные голоса не замораживаем в кэш
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps({**result, "ts": now_utc_iso(),
                                     "claim_sha256": sha256_hex(claim["text"].encode("utf-8")),
                                     "judge": os.environ.get("TL_JUDGE_CMD", "")},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    return result

# ─────────────── оркестрация проверки одной страницы ───────────────

# Чем меньше число — тем строже вердикт (выигрывает худший из применённых проверок).
_VERDICT_ORDER = {"CONTRADICTED": 0, "INSUFFICIENT": 1, "SUPPORTED": 2}

def route(claim, frag) -> dict:
    """П2-фикс: гоним ВСЕ применимые проверки и берём строжайший вердикт.
       Раньше число/цитата уводили утверждение в один механический чек и его СМЫСЛ
       судья не видел («Спрос упал на 30%», где в источнике 30 — но про рост): цифра
       совпадала → SUPPORTED, хотя смысл противоречит. Теперь если задан судья (TL_JUDGE_CMD),
       он голосует по ЛЮБОМУ утверждению вдобавок к механике, и противоречие смысла валит чек."""
    checks = []  # (method, result)
    if re.search(r"\d", claim["text"]):
        checks.append(("mechanical", check_number(claim, frag)))
    if re.search(r"[«\"“].+?[»\"”]", claim["text"]):
        checks.append(("mechanical", check_quote(claim, frag)))
    if os.environ.get("TL_JUDGE_CMD"):                 # семантика — для любого утверждения
        checks.append(("model", check_with_judge(claim, frag)))
    if not checks:                                     # ни цифр/цитат, ни судьи
        checks.append(("model", {"classification": "INSUFFICIENT", "evidence_span": ""}))
    method, worst = min(checks, key=lambda c: _VERDICT_ORDER.get(c[1]["classification"], 1))
    return {"classification": worst["classification"],
            "evidence_span": worst.get("evidence_span", ""),
            "method": "+".join(sorted({m for m, _ in checks}))}

# ─────────────── П3-фикс: фактические предложения без указателя ───────────────

# Заголовки/служебные секции и блоки, где якорь не требуется (связи, теги, шаблоны кода).
_SKIP_LINE = re.compile(r"^\s*(#{1,6}\s|[-*]\s*\[\[|>\s|\||```|:?-{3,}|<|\d+\.\s*\[\[)")
_SECTION_SKIP = re.compile(r"^\s*#{1,6}\s*(related|sources|see also|links|"
                           r"связанн|источник|см\.?\s*также|ссылк|теги|tags)", re.I)
# Фактическим считаем предложение с цифрой, кавычками-цитатой или утвердительной длиной.
_HAS_FACT = re.compile(r"\d|[«\"“].+?[»\"”]")

def find_unanchored(body: str) -> list[str]:
    """Возвращает фактические предложения тела, у которых НЕТ указателя на источник.
       Дисциплина привязки (CLAUDE.md): без источника утверждение писать нельзя — должно
       стоять [нужен источник]. Раньше такие строки молча игнорировались и страница могла
       стать trusted с непривязанной (возможно ложной) фактурой между нормальными ссылками."""
    out, in_skip = [], False
    for line in body.splitlines():
        if _SECTION_SKIP.match(line):
            in_skip = True; continue
        if line.strip().startswith("#"):
            in_skip = bool(_SECTION_SKIP.match(line))
        if in_skip:
            continue
        if not line.strip() or _SKIP_LINE.match(line):
            continue
        if ANCHOR.search(line):                        # уже привязано — ок
            continue
        if "[нужен источник]" in line or "[need source]" in line:
            continue                                    # честно помечено — это разрешено
        if _HAS_FACT.search(line) or len(line.strip()) > 80:
            out.append(line.strip()[:120])
    return out

def rollup(results: list[dict]) -> str:
    if not results:                                                  return "NO_CLAIMS"
    if any(r["classification"] == "CONTRADICTED" for r in results):  return "FAIL"
    if any(not r["source_hash_ok"] for r in results):               return "FAIL"  # порча источника / STALE_HASH
    if any(r["classification"] == "INSUFFICIENT" for r in results):  return "NEEDS_SOURCE"
    return "PASS"

def verify_note(path: pathlib.Path) -> dict:
    body = body_of(path)
    results = []
    for c in decompose(body):                                        # П1
        frag, src_ok = fetch_fragment(c["source_ref"], c["source_version"])  # П2
        if not src_ok:
            # STALE_HASH: битый УКАЗАТЕЛЬ (хеш версии разошёлся с файлом raw/), а не смысловая
            # ошибка. Раньше падало как INSUFFICIENT и выглядело как «источник не подтверждает
            # мысль» — чинили текст вместо хеша. Отдельный класс сразу говорит, что чинить.
            results.append({**c, "source_hash_ok": False, "method": "mechanical",
                            "classification": "STALE_HASH", "evidence_span": ""})
            continue
        results.append({**c, "source_hash_ok": True, **route(c, frag)})  # П3–П5
    status = rollup(results)                                          # П6
    unanchored = find_unanchored(body)                               # П3-фикс
    if unanchored and status in ("PASS", "NO_CLAIMS"):
        status = "NEEDS_SOURCE"                                       # есть непривязанная фактура
    return {"note": path.name, "status": status, "n_claims": len(results),
            "claims": results, "unanchored": unanchored}

# ─────────────── ступень 4 + ворота A/B ───────────────

def _fully_judged(verdict: dict) -> bool:
    """True, если КАЖДОЕ утверждение страницы получило голос судьи (в method есть 'model').
       Без TL_JUDGE_CMD судья молчит → смысл утверждений не проверен: механическое совпадение
       числа/цитаты НЕ доказывает, что утверждение следует из источника по СМЫСЛУ
       («спрос упал на 30%», где в источнике 30 — но про рост). ISSUE п.2 (остаток): такую
       страницу нельзя считать полным 'trusted' — только слабый тир."""
    claims = verdict.get("claims", [])
    return bool(claims) and all("model" in (c.get("method", "") or "") for c in claims)

def _trust_tier(bound: bool, judged: bool) -> str:
    """Полный 'trusted' = криптопривязка к содержимому (verifier --expect) И каждое утверждение
       проверено судьёй по смыслу. Любая из двух слабостей → честный слабый тир
       'trusted-mechanical' (валидно и консистентно, но не доказано до конца)."""
    return "trusted" if (bound and judged) else "trusted-mechanical"

def _tier_reason(bound: bool, judged: bool) -> str:
    if bound and judged:
        return "trusted: криптопривязка квитанции к H + смысл проверен судьёй"
    miss = []
    if not bound:
        miss.append("verifier без --expect (нет криптопривязки к содержимому, ISSUE п.1)")
    if not judged:
        miss.append("без судьи: смысл утверждений не проверен, только механика (ISSUE п.2)")
    return "trusted-mechanical: " + "; ".join(miss)

def certify_note(path: pathlib.Path, verdict: dict) -> str:
    body = body_of(path)
    sources = extract_sources(body)
    H = sha256_hex(body.encode("utf-8") + canon(sources) + canon(verdict))  # бинд по body
    receipt = notarize(H)
    # Полный 'trusted' честен ТОЛЬКО при двух условиях сразу:
    #  (1) verifier криптографически привязывает квитанцию к H (флаг --expect) — иначе связь с
    #      содержимым держится на открытом bound_hash, подделываемом держателем ключа записи (п.1);
    #  (2) смысл каждого утверждения проверен судьёй — иначе чисто механическое совпадение
    #      числа/цитаты не доказывает следование из источника по смыслу (п.2).
    # Нет любого из условий → честный слабый тир 'trusted-mechanical'.
    bound = _verifier_supports_expect()
    judged = _fully_judged(verdict)
    status = _trust_tier(bound, judged)
    save_receipt("wiki", path.stem, receipt, H,
                 extra={"sources": sources, "verdict": verdict,
                        "binding": "bound" if bound else "mechanical",
                        "fully_judged": judged})
    write_frontmatter(path, {"status": status,
                             "receipt_ref": f"receipts/wiki/{path.stem}",
                             "bound_hash": H,
                             "verify_note": _tier_reason(bound, judged)})
    return status

def quarantine(path: pathlib.Path, reason: str):
    write_frontmatter(path, {"status": "unverified", "verify_note": reason})
    UNVERIFIED.mkdir(exist_ok=True)
    shutil.move(str(path), str(UNVERIFIED / path.name))

def is_trusted(path: pathlib.Path) -> str:
    """Ворота B. Возвращает УРОВЕНЬ доверия (строку, не bool):
         "bound"      — квитанция криптографически привязана к H (verifier с --expect): подделка
                        невозможна без перенотаризации (а это уже граница ключей, правило №5);
         "mechanical" — квитанция валидна И bound_hash == H, НО привязки к H нет: связь с
                        содержимым держится на открытом bound_hash и подделывается тем, у кого есть
                        ключ записи в волт. Ловит случайные/наивные правки, не злонамеренную подмену;
         ""           — не trusted: правка после заверения, либо привязка к H не сошлась.
       Это лишь крипто-целостность квитанции. Итоговый тир страницы ('trusted' vs
       'trusted-mechanical') считают certify_note/_audit_one: к 'bound' добавляется
       требование судьи по смыслу (_fully_judged, ISSUE п.2). С verifier'ом v1.4.0+
       (--expect) уровень здесь — 'bound'; 'mechanical' остаётся для старых verifier'ов."""
    fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    ref = fm.get("receipt_ref")
    if not ref:
        return ""
    sidecar = json.loads((RECEIPTS / "wiki" / f"{path.stem}.json").read_text(encoding="utf-8"))
    body = body_of(path)
    sources = extract_sources(body)
    H = sha256_hex(body.encode("utf-8") + canon(sources) + canon(sidecar["verdict"]))  # (б)
    # (а) подлинность + (при поддержке --expect) криптопривязка именно к H, fail-closed:
    if not verify_receipt_offline("wiki", path.stem, expected_hex=H):
        return ""
    # (б) сверка bound_hash ловит правки тела/источников/вердикта после заверения:
    if not (H == fm.get("bound_hash") == sidecar["bound_hash"]):
        return ""
    return "bound" if _verifier_supports_expect() else "mechanical"

# ─────────────────────────── команды CLI ───────────────────────────

def wiki_pages():
    return [p for p in WIKI.glob("*.md") if p.name not in SKIP]

def cmd_init(args):
    """Разворачивает структуру волта кросс-платформенно (без shell-команд)."""
    root = pathlib.Path(args.dir).resolve()
    dirs = ["raw/articles", "raw/papers", "raw/notes", "raw/images",
            "wiki/_templates", "outputs", "receipts/raw", "receipts/wiki", "unverified"]
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)
    files = {
        "wiki/_templates/page.md": PAGE_TEMPLATE,
        "wiki/index.md": "# Index\n\nКаталог страниц вики по доменам. Агент читает его первым.\n",
        "wiki/log.md": "# Log\n\nappend-only лог операций: ## [YYYY-MM-DD] операция | описание | receipt:<id>\n",
    }
    for rel, content in files.items():
        p = root / rel
        if not p.exists():
            p.write_text(content, encoding="utf-8")
    print(f"Волт развёрнут: {root}")
    print("Дальше: положи CLAUDE.md из репозитория в корень волта, задай TIMELAYER_TOKEN и TL_VERIFIER.")

def cmd_hash(args):
    print(sha256_hex(pathlib.Path(args.path).read_bytes()))

def cmd_ingest_source(args):
    p = pathlib.Path(args.path)
    digest = sha256_hex(p.read_bytes())
    receipt = notarize(digest)
    save_receipt("raw", p.stem, receipt, digest)
    print(f"{p}  →  sha256={digest}  (квитанция в receipts/raw/{p.stem})")
    print("Используй этот sha256 в указателях wiki: ...|src:NAME@" + digest + "]]")

def _verify_one(path: pathlib.Path):
    verdict = verify_note(path)
    if verdict["status"] == "PASS":
        tier = certify_note(path, verdict)
        note = "" if tier == "trusted" else \
            f"  [{_tier_reason(_verifier_supports_expect(), _fully_judged(verdict)).split(': ', 1)[1]}]"
        print(f"PASS     {path.name}  → {tier} ({verdict['n_claims']} утв.){note}")
    else:
        bad = [f"{r['classification']}: {r['text'][:60]}"
               for r in verdict["claims"]
               if r["classification"] != "SUPPORTED" or not r["source_hash_ok"]]
        for u in verdict.get("unanchored", []):
            bad.append(f"НЕТ ИСТОЧНИКА: {u[:60]}")     # П3-фикс: показать непривязанную фактуру
        reason = verdict["status"] + "; " + " | ".join(bad[:5])
        if any(r["classification"] == "STALE_HASH" for r in verdict["claims"]):
            reason += " | STALE_HASH: чини УКАЗАТЕЛЬ (хеш/строки), не текст; свежий хеш: notary.py hash raw/<файл>"
        # Мягкий карантин: в unverified/ уезжает только FAIL (противоречие источнику или
        # порча его версии) — активная ложь изолируется. NEEDS_SOURCE/NO_CLAIMS — неполнота,
        # не ложь: страница остаётся на месте со статусом unverified и verify_note, ссылки
        # index.md не бьются.
        if verdict["status"] == "FAIL":
            quarantine(path, reason)
            print(f"{verdict['status']:8} {path.name}  → unverified/  ({'; '.join(bad[:3])})")
        else:
            write_frontmatter(path, {"status": "unverified", "verify_note": reason})
            print(f"{verdict['status']:8} {path.name}  → остаётся в wiki/, unverified  ({'; '.join(bad[:3])})")

def cmd_verify(args):
    _verify_one(pathlib.Path(args.note))

def _judge_smoke_ok() -> bool:
    """Один тестовый голос перед массовым прогоном: судья должен вернуть парсибельный вердикт.
       Ловит мёртвого судью (квота провайдера, слетевший логин, сломанная обёртка) ДО того,
       как 20 страниц молча упадут INSUFFICIENT и прогон уйдёт в мусор."""
    v = judge_once("Дважды два — четыре.", "Проверка: дважды два — четыре.")
    return not v.get("_err")

def cmd_verify_all(args):
    # Тихая ловушка №1: судья не настроен → вся проза падает INSUFFICIENT (fail-closed —
    # правильно), но выглядит как «база сломана», а не как забытая переменная окружения.
    # Требуем либо судью, либо явное согласие на потолок trusted-mechanical.
    if not os.environ.get("TL_JUDGE_CMD") and not getattr(args, "mechanical_only", False):
        sys.exit("verify-all: судья не настроен (TL_JUDGE_CMD пуст) — все смысловые утверждения\n"
                 "упадут INSUFFICIENT, потолок страниц: trusted-mechanical.\n"
                 "Либо настрой судью (референсные обёртки: scripts/judges/),\n"
                 "либо согласись явно:  notary.py verify-all --mechanical-only")
    # Тихая ловушка №2: судья настроен, но мёртв (квота, логин, сеть) — сбойные голоса
    # неотличимы от честного INSUFFICIENT. Один смоук-голос до прогона.
    if os.environ.get("TL_JUDGE_CMD") and not _judge_smoke_ok():
        sys.exit("verify-all: TL_JUDGE_CMD задан, но судья не отвечает валидным JSON\n"
                 "(квота провайдера? слетел логин? сломана обёртка?). Прогон дал бы сплошной\n"
                 "INSUFFICIENT впустую. Проверь руками:  echo тест | $TL_JUDGE_CMD")
    for p in wiki_pages():
        try:
            _verify_one(p)
        except PermissionError as e:
            # Одна read-only страница не должна ронять проверку остальных.
            print(f"ПРОПУСК  {p.name}  (нет прав на запись: {getattr(e, 'filename', None) or e}) — продолжаю")

def _audit_one(path: pathlib.Path):
    if not (RECEIPTS / "wiki" / f"{path.stem}.json").exists():
        print(f"—        {path.name}  (нет квитанции, пропуск)"); return
    level = is_trusted(path)          # "bound" | "mechanical" | "" — крипто-целостность квитанции
    if not level:
        write_frontmatter(path, {"status": "unverified",
                                 "verify_note": "изменено после заверения — trusted снят"})
        print(f"СНЯТ     {path.name}  → trusted снят (изменено после заверения)")
        return
    # целостность держится — теперь страничный тир с учётом семантики (тот же закон, что в certify):
    sidecar = json.loads((RECEIPTS / "wiki" / f"{path.stem}.json").read_text(encoding="utf-8"))
    bound = (level == "bound")
    judged = _fully_judged(sidecar.get("verdict", {}))
    status = _trust_tier(bound, judged)
    write_frontmatter(path, {"status": status, "verify_note": _tier_reason(bound, judged)})
    if status == "trusted":
        print(f"OK       {path.name}  (trusted держится, криптопривязка к H + судья)")
    else:
        print(f"OK*      {path.name}  ({_tier_reason(bound, judged)})")

def cmd_audit(args):
    _audit_one(pathlib.Path(args.note))

def cmd_audit_all(args):
    for p in wiki_pages():
        try:
            _audit_one(p)
        except PermissionError as e:
            print(f"ПРОПУСК  {p.name}  (нет прав на запись: {getattr(e, 'filename', None) or e}) — продолжаю")

def main():
    ap = argparse.ArgumentParser(description="Нотариальный слой корректности для LLM KB")
    sub = ap.add_subparsers(required=True)
    sp = sub.add_parser("init"); sp.add_argument("dir", nargs="?", default="."); sp.set_defaults(f=cmd_init)
    sp = sub.add_parser("hash");          sp.add_argument("path"); sp.set_defaults(f=cmd_hash)
    sp = sub.add_parser("ingest-source"); sp.add_argument("path"); sp.set_defaults(f=cmd_ingest_source)
    sp = sub.add_parser("verify");        sp.add_argument("note"); sp.set_defaults(f=cmd_verify)
    sp = sub.add_parser("verify-all")
    sp.add_argument("--mechanical-only", action="store_true",
                    help="явное согласие на прогон без судьи (потолок: trusted-mechanical)")
    sp.set_defaults(f=cmd_verify_all)
    sp = sub.add_parser("audit");         sp.add_argument("note"); sp.set_defaults(f=cmd_audit)
    sub.add_parser("audit-all").set_defaults(f=cmd_audit_all)
    args = ap.parse_args()
    args.f(args)

if __name__ == "__main__":
    main()
