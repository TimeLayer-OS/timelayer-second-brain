# Second Brain on Receipts — the complete guide

**Obsidian + Claude Code + the TimeLayer notarial layer**

A knowledge base that compounds instead of being rediscovered; a wiki that isn't written by your own hand; and a mechanism that makes correctness checking **mandatory, unforgeable, attributable, and self-invalidating on any edit**.

> This document brings together three things: the **LLM Knowledge Base methodology of Andrej Karpathy** (the `raw/wiki` pattern, the Ingest/Query/Lint cycle — [gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)), the wiring from the "Second Brain on Claude + Obsidian" guide (plugin, MCP, scheduling), and the TimeLayer notarial correctness layer. Who Karpathy is: co-founded OpenAI, led Tesla's Autopilot AI, PhD from Stanford, a well-known AI educator. The pattern is his; the notarial overlay closes the spot he himself flags as weak (see §0 and §18).

---

## 0. First — an honest model. Without it the mechanism will lie to you

Everything rests on a single distinction. Confuse it, and you'll build a system that looks reliable and quietly lies.

**Notarization does not check truth and cannot.** A receipt proves that *something happened over these exact bytes at such-and-such a moment and was not changed afterward*. About *whether the content is correct* it says nothing. A notarized hallucination is still a hallucination — just now with a stamp.

That's why we notarize not "the text" but **a judgment about the text**: the binding of the note's bytes, a specific source, and a verification verdict. The receipt turns from "here is text" into "**here is proof that a check ran over exactly these words, and here is who is accountable for it**." This is the ceiling of crypto — and it's enough, if you pick the right thing to notarize *and* the right checker.

| Layer | Question | What provides it |
|---|---|---|
| **Access** | Can the agent change the file at all | **Keys** (read-only, narrow scope). Not prompts. |
| **Integrity and process** | If it changed it — is there an unforgeable, attributable trail; did the check run | **Receipts** from TimeLayer |
| **Correctness** | Is what's written correct | **The checker** (the mechanical path / a model / a human). Neither keys nor receipts give you this |

The "immutable" you need in a wiki is not "the bytes can't be changed" but **tamper-evident**: an edit is detected instantly and strips the "verified" status. Immutability of *trust*, not of bytes. Only a key can physically forbid a write. Keep this table in front of you for the rest of the guide.

---

## PART I. WHY THIS, AND WHAT SHAPE IT TAKES (Karpathy's methodology)

### 1. Why ordinary knowledge bases don't work

Most people work with documents through an LLM like this: load the files, the model fetches relevant chunks for each query, generates an answer. This is **RAG** — and it has four congenital holes:

- **No accumulation** — every question starts from scratch.
- **No synthesis** — the model doesn't connect information across sources.
- **No updating** — new data doesn't correct old conclusions.
- **No structure** — knowledge is smeared across chunks with no cross-references.

The picture per Karpathy: you gather 50 articles, ask a question — the model found 3 relevant chunks out of 50. Tomorrow a similar question — a different 3. You never have the full picture; knowledge doesn't accumulate, it gets reinvented.

### 2. The idea: a persistent, compounding wiki

Instead of searching over raw documents, the LLM **incrementally builds and maintains a wiki** — a structured collection of cross-linked markdown files. The links are already in place, contradictions already flagged, the synthesis already reflects everything read. The wiki grows richer with every source and every question.

Why the LLM and not you: the boring part of a wiki isn't the reading or the thinking, it's the **bookkeeping** (links, updates, consistency). People abandon wikis because the maintenance cost grows faster than the value. An LLM doesn't tire and updates 15 files in a single pass.

**Division of roles:**

| You (the human) | The LLM (the agent) |
|---|---|
| Curate sources | Summarization and indexing |
| Set direction | Cross-linking |
| Ask questions | Updating on new data |
| Think about meaning | Bookkeeping and consistency |

Where this fits: research, an internal company wiki (from Slack/meetings/calls), personal development, reading books, competitive analysis.

### 3. Architecture: four layers + the schema

Karpathy keeps three layers; the notarial layer adds a fourth (`receipts/`) and a quarantine (`unverified/`).

| Layer | Purpose | Writes | Reads | Rule |
|---|---|---|---|---|
| `raw/` | Raw sources | You | LLM | **Never modify** |
| `wiki/` | LLM's wiki | LLM | You | The LLM owns it entirely |
| `outputs/` | Reports, answers | LLM | You | Can be fed back into wiki |
| `receipts/` | Receipts (provenance + verdicts) | script | script/you | Append-only |
| `unverified/` | Quarantine for the unverified | script | you | Temporary |
| `CLAUDE.md` | The schema (config) | You + LLM | LLM | Evolves |

**Folder structure:**

```
my-knowledge-base/
├── raw/                 <- Immutable sources. The LLM reads, NEVER edits
│   ├── articles/        <- articles, blog posts
│   ├── papers/          <- research
│   ├── notes/           <- personal notes
│   ├── telegram/        <- Telegram posts
│   └── images/          <- diagrams, screenshots
├── wiki/                <- The LLM's wiki. You — don't touch by hand
│   ├── index.md         <- catalog of all pages (the LLM reads it first)
│   ├── log.md           <- append-only operations log (the seed of an audit trail)
│   └── _templates/      <- page templates
├── outputs/             <- reports, analysis
├── receipts/            <- .tlcert/.tlbundle: receipts for sources and verdicts
│   ├── raw/
│   └── wiki/
├── unverified/          <- notes without a valid verification receipt
└── CLAUDE.md            <- the schema for the LLM
```

Key files: **`wiki/index.md`** — a catalog by domain; the LLM reads it first to find relevant pages. **`wiki/log.md`** — an append-only operations log (`## [YYYY-MM-DD] operation | description`); this is exactly where we'll put receipt ids, and the log itself can be notarized. **`CLAUDE.md`** — the schema: without it the LLM is just a chatbot; with it, a disciplined wiki maintainer.

---

## PART II. BUILDING THE BASE (the wiring)

### 4. Install Claude Code

Download the Claude desktop app from `claude.com/download`, open the **Code** tab — the version that reads and writes files on your computer. You need a paid plan (Claude Pro ~$20/mo; it won't run on free). The only mandatory line item in the base part. The pattern isn't tied to Claude — Cursor, Codex, any agent with file access will do too.

### 5. Create the structure

Download Obsidian from `obsidian.md`, create a vault. In the vault's terminal:

```bash
mkdir -p raw/articles raw/papers raw/notes raw/telegram raw/images
mkdir -p wiki/_templates outputs receipts/raw receipts/wiki unverified
```

Or just tell Claude Code: "Create the LLM Knowledge Base structure following Karpathy's pattern, plus the `receipts/` and `unverified/` folders."

### 6. Open the door to the vault (the Local REST API plugin)

In Obsidian: **Settings → Community plugins → enable → Browse → install Local REST API**. Enable it, open the settings, copy the **API key**. The plugin brings up a local server at `127.0.0.1:27124`.

**Don't close Obsidian** — the door works only while the app is open.

> This is "that plugin." TimeLayer is not a plugin — it connects separately (§13).

### 7. Connect Claude via MCP

On the Code tab, substituting your key (drop the word `Bearer` from the plugin, keep the string after it):

```bash
claude mcp add-json obsidian-vault '{
  "type": "stdio",
  "command": "uvx",
  "args": ["mcp-obsidian"],
  "env": {
    "OBSIDIAN_API_KEY": "PASTE-YOUR-KEY",
    "OBSIDIAN_HOST": "127.0.0.1",
    "OBSIDIAN_PORT": "27124"
  }
}'
```

`mcp-obsidian` is a proven bridge with thousands of stars on GitHub. Test it: "list all files in my vault."

### 8. CLAUDE.md — the brain of the system

The single most important file. It contains six blocks:

1. **Architecture** — a description of the four layers (section 3).
2. **Frontmatter schema** — the metadata of each wiki page. Karpathy's base schema, extended with the notarial layer's fields:

```yaml
---
type: entity | concept | project | person | summary
domain: ai | infra | content | personal
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: ["[[raw/articles/file]]@a1b2c3"]   # source + VERSION HASH (our addition)
status: trusted | unverified                 # the verification gate (ours)
receipt_ref: receipts/wiki/<id>              # reference to the verdict receipt (ours)
bound_hash: <sha256>                          # for self-invalidation (ours)
tags: []
---
```

3. **Naming conventions** — kebab-case for the wiki, a date prefix (`2026-04-06-name.md`) for articles.
4. **Operations** — Ingest / Query / Lint (Part III), including notarization and anchoring.
5. **Domains of interest** — your topics.
6. **Profile** — who you are. Don't type it in by hand; let Claude interview you:

> Interview me ONE question at a time to build a profile: who I am and what I do, goals for the year, how to communicate with me, strengths/weaknesses, current projects. Wait for each answer. At the end, write it all into `CLAUDE.md` under headings.

Wiki page template (in `wiki/_templates/`):

```markdown
# Title
## Summary
1–2 paragraphs.
## Key Details
Structured information — every factual claim anchored to a source (§10).
## Related
- [[wiki/related-page]] — why related
## Sources
- [[raw/articles/source-file]]@<hash>
```

CLAUDE.md evolves: start simple ("super simple and flat," per Karpathy) and expand.

### 9. Teach Claude the Obsidian dialect

Claude writes bare markdown — it doesn't know `[[wikilinks]]`, callout blocks, Bases, or Canvas until you show it. Steph Ango (CEO of Obsidian) published official Agent Skills at `kepano/obsidian-skills`. Put the repository's contents into `.claude` at the root of the vault. The skills follow the open Agent Skills spec — they work in other agents too.

---

## PART III. THE WORKING CYCLE: INGEST / QUERY / LINT

Karpathy's canonical cycle is three operations. The notarial layer is built directly into them: **source notarization lives in Ingest, the checker lives in Lint.** No separate "pipeline" — one cycle.

### 10. Ingest — with anchoring and source notarization

You dropped a file into `raw/`. Say: "Process the new file in `raw/articles/2026-04-06-name.md`." What happens:

1. **Source notarization** *(ours)* — the script computes the file's hash, sends it to TimeLayer, puts the receipt into `receipts/raw/`. The source now has a provable "version."
2. The LLM reads the source in full.
3. It discusses the key takeaways with you (one source at a time — the wiki comes out better that way).
4. It creates/updates pages in `wiki/` — **every factual claim carries a pointer to a specific source fragment with a version hash** *(our reinforcement of anchoring discipline)*:

```markdown
Growth slowed in Q2. ^[[raw/q2-report.md#L40-L48|src:q2-report@a1b2c3]]
```

5. It updates `wiki/index.md` and `wiki/log.md` (into the log — the receipt id).
6. It places `[[links]]` between related pages.

A single source can touch 5–15 pages. **You don't write the wiki by hand** — that's the "not by hand" from your spec, and anchoring to sources is the "anchored."

**Ways to load into `raw/`:**

| Method | How | Difficulty |
|---|---|---|
| Obsidian Web Clipper | browser button → `.md` into `raw/articles/` | easy |
| Copy-paste | create a `.md` manually | easy |
| Claude Code | "save this article into `raw/`" | easy |
| Telegram Sync | forward to a bot → `raw/telegram/` | medium |
| yt-dlp | YouTube transcripts via CLI | medium |
| X/Twitter archive | request the archive → unpack | medium |

```bash
# YouTube transcripts
yt-dlp --write-auto-sub --sub-lang ru --skip-download -o "raw/notes/%(title)s" URL
# Summary of an article by URL
summarize https://example.com/article > raw/articles/2026-04-06-article.md
```
Web Clipper: install the extension, in settings point it at the vault and the `raw/articles/` folder; images — the "Download attachments" hotkey (`Ctrl+Shift+D`) downloads them into `raw/images/`.

### 11. Query — with compounding into outputs/

Once the wiki has 10+ pages, ask:

- "The three main trends in AI agents based on everything in `wiki/`?"
- "Compare article X and Y. Where do they diverge?"
- "A 500-word briefing on topic [X], from the base's materials only."

The LLM reads `wiki/index.md`, finds relevant pages, synthesizes an answer with citations. **Compounding:** save valuable answers into `outputs/`, or feed them back into `wiki/` as a new page — each question makes the next answer better. Important: an answer fed back into the wiki then passes through Lint, like any page — otherwise an error in the answer becomes the foundation for the next one (see §18).

### 12. Lint → the grounding checker

In Karpathy's setup, Lint runs once a month to look for contradictions, orphans, claims without a source, missing links, gaps — "code review for the knowledge base." **We turn Lint into a full correctness check with receipts.** Karpathy's classic checks ride along with it.

Lint now does three things:
1. **Classic lint** (Karpathy): contradictions between pages, orphan pages, concepts without their own page, broken/missing links, stale claims.
2. **Grounding check** *(ours)*: for each claim — does it follow from the cited source. Full steps in §15.
3. **Notarization and the gates** *(ours)*: the verdict is notarized, the `trusted` status is granted/revoked. §14, steps 4–5.

Why this matters: classic Lint catches *contradictions and broken links*, but it does NOT catch a confidently-wrong claim that is internally consistent (semantic drift). Grounding catches exactly that. And git gives you rollback, but neither tamper-evidence, nor authorship, nor the **mandatory** nature of the check. The notarial layer closes precisely this gap.

### Viewing in Obsidian

**Graph View** (`Ctrl/Cmd+G`): hubs (pages with many incoming links — key concepts), orphans (no links — add links or delete), topic clusters. Color by `status` — and you'll see where the `unverified` quarantine is.

**Dataview** (a plugin, queries over frontmatter) — doubling as a trust panel:
```dataview
TABLE type, domain, status, updated
FROM "wiki"
WHERE type != null
SORT status ASC, updated DESC
```
**Search:** up to ~100 pages, `index.md` + Obsidian's standard search is enough. Beyond that — `qmd` (local BM25 + vector search with re-ranking, has a CLI and an MCP server).

---

## PART IV. THE NOTARIAL CORRECTNESS LAYER

### 13. Set up TimeLayer and install the verifier

TimeLayer is a notarial network: you send a fingerprint (a hash), get back a small (~1.5 KB) receipt, and verify it offline with open-source code. **The content never leaves — only the hash.** There's a ready-made "Tamper-evident Agent Log" product for AI-agent actions.

1. Register in the cabinet (`cabinet.timelayer-os.com`). At the start, 50 free receipts.
2. Get an **API token** (keep it narrow and separate — "keys, not prompts").
3. Download `timelayer-verifier` from GitHub (repository `TimeLayer-OS/timelayer-verifier`). It verifies a receipt offline, with one command.
4. The exact API parameters and the receipt format are in the docs at `timelayer-os.com/docs/`; confirm the details there or with support (§19).

### 14. The five steps of notarization (two of them live inside Ingest and Lint)

**"Verified" is not a flag you take on faith, but a computed property:** it's true only when there's a genuine receipt notarizing the hash of exactly the *current* content of the note together with its sources and the verdict. It can't be forged (the receipt is signed by a quorum of independent operators). It can't survive an edit (an edit changes the hash — the receipt no longer matches).

```
[1] source notarization   → in Ingest (§10.1): a content-receipt for each source
[2] writing with anchoring → in Ingest (§10.4): every claim with a pointer + version hash
[3] grounding pass         → in Lint (§15): an independent checker, a verdict per claim
[4] verdict receipt        → in Lint: the BINDING is notarized (bytes + source versions + verdict)
[5] two gates              → in Lint: promotion to trusted  and  the self-invalidation audit
```

**Step 4.** Only on `PASS`: `H = hash(note_bytes ++ sources_with_versions ++ verdict)` → into TimeLayer → `cert`/`bundle` into `receipts/wiki/`, and into the frontmatter — `receipt_ref` and `bound_hash`. This is a verification-receipt: it binds the *verdict* to *these bytes*.

**Step 5 — two gates.**
- **Gate A (promotion):** a note is `trusted` ⇔ (a) the verification-receipt passes `timelayer-verifier`, AND (b) the notarized hash equals the one freshly computed from the *current* content + sources + verdict. If not — it goes off to `unverified/`. The status is **computed**, not recorded, so forging `status: trusted` is pointless — check (b) will fail.
- **Gate B (self-invalidation):** an audit pass over every `trusted` note recomputes the hash and compares. **Any edit → the fingerprint changes → the receipt no longer matches → the status falls off.** You can't glue an old PASS onto new text. This is "immutable" in the honest sense: not "can't be changed," but "change it and it's instantly visible, trust is revoked by itself." The same trick catches tampering in `raw/` (the version hash will diverge → grounding fails → cascade).

**(Optional) a human signature** on top of machine grounding for critical notes — non-repudiation that a model cannot give.

### 15. The grounding checker — the full steps

The heart of the system. Input: a `wiki/` note with pointers. Output: a structured verdict, which gets notarized at step 4. The cross-cutting principle: **what can be checked mechanically is checked mechanically, because code doesn't hallucinate; the model is only for genuinely semantic claims, and only when hardened.**

**S1. Decomposition into atomic claims.** A note has many claims. Break each sentence into atomic ones, each with its own pointer. "Revenue +12% in Q2 driven by enterprise" = (1) +12% in Q2; (2) the driver is enterprise; grounded separately. Rule: every sentence containing a fact must map to at least one atomic claim; lint complains about sentences with no mapping and claims with no pointer.

**S2. Evidence extraction + version check.** For each claim, pull the fragment from `raw/` by the pointer **and check the version hash**. Diverged → a corruption signal (the cascade from step 5), stop. The reference doesn't resolve → automatic `INSUFFICIENT`.

**S3. Routing by type (the key decision).**

| Claim type | Check |
|---|---|
| Numbers, dates, quantities, percentages, units | **Mechanically**: extract the number from the source and from the claim, compare programmatically (with tolerance). Don't ask the model. |
| Quotes, verbatim wordings, attributions | **Mechanically**: a normalized substring match. |
| Existence/structure (a link, a version hash) | **Mechanically**. |
| Logical/semantic entailment ("X caused Y," generalizations) | **An NLI model**, hardened (S4–S5). |

Rule: if it can be checked mechanically, it *must* be checked mechanically. The model is a fallback only for what mechanics can't handle.

**S4. Three outcomes, not two.** SUPPORTED / **CONTRADICTED** (the fragment contradicts — a hard fail) / **INSUFFICIENT** (the source is silent). The split is critical: "contradicts" means "the note lies against the source," "insufficient" means "there's no support, you need another source." Different fixes.

**S5. Hardening the judge (error decorrelation).** The judge model is **the weakest link in the system**; the whole point of mechanics-first is to lean on it less often. Where there's no avoiding it:
1. **A different model from the one that wrote** (mandatory). Better — a different family: identical models give a *correlated* error, and the receipt will honestly notarize it.
2. **Self-consistency:** k samples (3–5), unanimity or a hard threshold; disagreement → **to a human, not an auto-PASS**.
3. **An adversarial framing:** ask the judge to look for a reason why it is NOT supported (a steelman of refusal), rather than "is everything OK" — this cuts the sycophantic PASS.
4. **Forced citation:** the judge must quote the exact supporting fragment. Didn't quote it — can't assign SUPPORTED. This grounds the judge itself.
5. **(stronger) An ensemble:** two different families must agree.

**S6. The verdict schema** (a machine-parseable object; notarized in full at step 4):

```json
{
  "claim": "revenue +12% in Q2",
  "source_ref": "raw/q2-report.md#L40-L48",
  "source_version": "a1b2c3",
  "source_hash_ok": true,
  "method": "mechanical",
  "classification": "SUPPORTED",
  "evidence_span": "...growth was 12% over Q1...",
  "agreement": "3/3"
}
```
Note rollup: **PASS** ⇔ every claim SUPPORTED AND all `source_hash_ok`. Any CONTRADICTED → **FAIL**. Any INSUFFICIENT → **NEEDS_SOURCE**. "Verified" can't be forged: change the verdict — the hash changes — the receipt won't match.

**S7. Escalations.** NEEDS_SOURCE → to Claude for a better source; if it can't find one → a human. CONTRADICTED → a loud flag, quarantine, a line in the morning digest. Judge disagreement → a human. Flagged `critical` → **a human signature is mandatory regardless of the machine PASS**.

**S8. The checker's own failures (honestly).** Correlated errors → mechanics-first + cross-family. Sycophantic PASS → adversarial framing + forced citation. Decomposition dropped a claim → the sentence-mapping rule + lint. **Source truthfulness is out of scope:** grounding checks "matches the source," not "the source is truthful." See §18.

### 16. How to wire it by hand (script skeleton)

There's no ready-made "TimeLayer for Obsidian" plugin — the service is bolted on with a thin script (Python fits well; the starter `coleam00/second-brain-starter` is already markdown+Python). Below is a *skeleton*: the exact API fields and verifier arguments come from `timelayer-os.com/docs/`.

```python
import hashlib, json, subprocess, httpx, pathlib

TL = "https://api.timelayer-os.com/v1/notarize"
TOKEN = "..."  # narrow TimeLayer token, from the environment, not in the code

def sha256_hex(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def canon(o) -> bytes: return json.dumps(o, sort_keys=True, ensure_ascii=False).encode()

def notarize(hex_digest: str) -> dict:
    r = httpx.post(TL, headers={"Authorization": f"Bearer {TOKEN}"},
                   json={"action_hex": hex_digest})       # send only the hash
    r.raise_for_status()
    return r.json()  # {cert_hex, bundle_hex, notarized_at} — confirm against the docs

# Step 1 (in Ingest): source notarization
def ingest_source(path: pathlib.Path):
    d = sha256_hex(path.read_bytes())
    save_receipt(f"receipts/raw/{path.stem}", notarize(d), d)

# §15 (in Lint): the grounding checker
def verify_note(note_path: pathlib.Path) -> dict:
    claims = decompose(note_path.read_text())   # S1
    out = []
    for c in claims:
        frag, src_ok = fetch_fragment(c)        # S2
        if not src_ok:
            out.append({**c, "source_hash_ok": False,
                        "classification": "INSUFFICIENT", "method": "mechanical"}); continue
        if c["kind"] in ("number","date","quote","structure"):
            res, m = check_mechanically(c, frag), "mechanical"     # S3
        else:
            res, m = check_with_judge(c, frag), "model"            # S4–S5
        out.append({**c, "source_hash_ok": True, "method": m, **res})
    return rollup(out)                            # S6

def check_with_judge(c, frag) -> dict:           # a different model ≠ the writer; adversarial;
    votes = [judge_once(c["text"], frag) for _ in range(5)]   # forced citation; k samples
    classes = {v["cls"] for v in votes}
    if classes == {"SUPPORTED"} and all(v["span"] in frag for v in votes):
        return {"classification":"SUPPORTED","evidence_span":votes[0]["span"],"agreement":"5/5"}
    if "CONTRADICTED" in classes: return {"classification":"CONTRADICTED","agreement":"split"}
    return {"classification":"INSUFFICIENT","agreement":"split"}   # → escalation (S7)

# Step 4 (in Lint): the verdict receipt (only on PASS)
def certify_note(note_path, sources, verdict):
    H = sha256_hex(note_path.read_bytes() + canon(sources) + canon(verdict))
    r = notarize(H)
    save_receipt(f"receipts/wiki/{note_path.stem}", r, H)
    set_frontmatter(note_path, receipt_ref=r["id"], bound_hash=H, status="trusted")

# Gate B (in Lint): the self-invalidation audit
def is_trusted(note_path, sources, verdict) -> bool:
    fm = read_frontmatter(note_path)
    if not fm.get("receipt_ref"): return False
    cert, bundle = load_receipt(fm["receipt_ref"])
    if subprocess.run(["timelayer-verifier","verify",cert,bundle]).returncode != 0:  # (a)
        return False
    H = sha256_hex(note_path.read_bytes() + canon(sources) + canon(verdict))
    return H == fm["bound_hash"]                                                      # (b)
```

`decompose`, `fetch_fragment`, `check_mechanically`, `judge_once`, `rollup` — modules for your pointer format and model pool.

### 17. Scheduling and the iron rule

Once the cycle settles — put it on a schedule. The **Schedule** tab, a task at 7 a.m.: run **Ingest** over what's new in `raw/` (with source notarization), then **Lint** (classic + grounding + the gates), and write a three-line digest: what was added, what's `trusted`, what fell into `unverified/`.

**The rule that does not get broken: access is governed by keys, not prompts.** "Don't delete this" is a wish. A read-only key with narrow scope is a setting. TimeLayer is a **witness, not a guard**: it'll prove what the agent did, but it won't stop it. In a strict variant (the agent's only path to disk is through a proxy that requires a receipt) it can guard too, but only *accountability*, and only if you build that bottleneck yourself. Live data — as in the base guide (`claude mcp add google-workspace uvx workspace-mcp --tools calendar`), also on a read-only key.

---

## PART V. REALITY

### 18. The honest ceiling (without it the whole construct lies)

- **The correctness guarantee is exactly as good as the checker in the gate.** Notarization makes its verdict mandatory and unforgeable — but not correct. It hallucinates SUPPORTED — the receipt will honestly record a false PASS. You haven't killed the trust problem, you've **moved** it from the writer to the checker. The win comes only if the checker is more reliable: mechanics where you can (S3); an independent family and hardening where you can't (S5); a human for what's important (S7). Two identical models will give a correlated error, and the receipt will notarize it.
- **Grounding checks "matches the source," not "the source is truthful."** Falsehood in `raw/` will honestly slip into `trusted`. Garbage in — notarized garbage out.
- **Tamper-evident ≠ tamper-proof.** Receipts detect an edit, they don't forbid it. Only a key forbids it.
- **TimeLayer is a young network, without a formal audit** (by their own account, an external security review is only planned). Its strength: receipts are verified offline with open-source code — there's no lock-in, old receipts stay verifiable even if the service disappears (new ones won't be). Build so you can leave.
- **Karpathy himself notes this ceiling.** In his FAQ, to "what if the LLM gets it wrong?" the answer is "Lint + git rollback." Lint catches contradictions, git gives rollback, but neither gives tamper-evidence, nor authorship, nor the mandatory nature of the check. Our layer is an upgrade of exactly this spot.

What the mechanism **actually** gives: it turns "trust me, it's correct here" into "here is proof that it was checked against this source, bound to these exact words, and here is who is accountable," and it **automatically revokes trust from any note that was silently changed**. It guards the *process and the chain of accountability*. Truth is produced by the checker — notarization merely keeps you from lying that the check happened.

### 19. Best practices and TimeLayer contacts

**Do:** load sources one at a time and take part in the discussion; feed valuable answers back into `wiki`/`outputs`; run Lint at least once a month (and with a schedule — daily); place `[[wikilinks]]` everywhere; keep `CLAUDE.md` current; keep the wiki in git (version history for free); notarize **only the changed** files; checker ≠ writer, mechanics ahead of the model, the critical to a human; keys narrow and read-only.

**Don't:** don't edit the `wiki` by hand (that's the LLM's job — tell it); don't modify `raw/`; don't over-engineer (flat files + a good schema > a tricked-out stack, the "Notion trap"); don't hoard `raw/` without processing (the value is in the wiki); don't trust `trusted` as "true" — it's "checked by a named checker," see §18; don't put tokens/keys in the code.

**TimeLayer contacts:** email `timelayer.os@gmail.com`, Telegram `@TIMELAYEROS`, docs `timelayer-os.com/docs/`, the verifier and operators' public keys — GitHub `TimeLayer-OS`. What to ask support: (1) the response format of `/v1/notarize` and how the receipt is bound to the hash — is the digest in the `bundle`, can you verify against a known hash (needed for Gates A/B); (2) support for arbitrary **memo/metadata** in the receipt; (3) whether you can send SHA-256 directly (inside a commitment over BLAKE3); (4) the limits for your volume; (5) ready-made **gateway / fail-closed** examples for the strict variant; (6) their status on security/audit. What you build yourself: the anchoring discipline, the checker (§15), the gates, the schedule, the keys — TimeLayer gives you notarization and the verifier, you assemble the semantic part on your side.

### 20. FAQ

**Not Claude Code, but a different tool?** Yes — Cursor, Codex, any agent with file access. The pattern isn't tied to one.

**Will the wiki get too big for the context?** At ~100 pages (~400,000 words) Karpathy says the LLM copes via `index.md` without RAG. Beyond that — `qmd` for search.

**How is this different from Notion/Obsidian with plugins?** People abandon wikis because the bookkeeping (links, updates, consistency) takes more time than the value. The LLM does it for free.

**Do I need Obsidian?** No, any editor will do. Obsidian is handy for the graph and Dataview, but it's optional — "the AI doesn't care what app you open the files in."

**For a team?** Yes: the wiki is a git repo, you can do PRs/branches, the LLM updates from Slack/meetings. And here, by the way, notarization is especially apt: receipts give a third party a verifiable trail of who contributed what.

**And if the LLM gets it wrong?** Karpathy's base answer is Lint + git rollback. Our layer adds to that a grounding check (catches the semantic drift Lint misses), tamper-evidence and authorship, and makes the check **mandatory**, not "once a month if the mood strikes."

**Notarize every file every day?** No — only the changed ones. Otherwise the free 50 receipts, and even €19/5k, will fly away. When you notarize the delta, the spend is small.

### 21. What you'll need (checklist)

**Software:** Claude (the Code tab, paid plan ~$20/mo) · Obsidian + the Local REST API plugin · `uvx`/`mcp-obsidian` · a TimeLayer account + token + `timelayer-verifier` · Python (the starter `coleam00/second-brain-starter`) · a model pool for the judge (**a different family** than the writer) · the `kepano/obsidian-skills` skills · optional: Web Clipper, yt-dlp, qmd, Dataview.

**Structure:** `raw/{articles,papers,notes,telegram,images} wiki/{index.md,log.md,_templates} outputs receipts/{raw,wiki} unverified CLAUDE.md` (+ `raw/` read-only at the OS/key level).

**Money:** Claude Pro — the only mandatory subscription. TimeLayer — a free start (50 receipts), then from €19/mo for 5,000 (≈166/day, enough for the delta). Everything else free.

**Discipline (more important than software):** the LLM writes the wiki, not you · every claim with a source and a version · checker ≠ writer · mechanics ahead of the model · the critical to a human · access by keys, not prompts · notarize only what changed.

**Skip the manual build of the base:** ready-made repositories for Karpathy's pattern — `AgriciDaniel/claude-obsidian` (15 skills, PARA/Zettelkasten presets), `eugeniughelbur/obsidian-second-brain` (43 commands, Claude/Codex/Gemini), `coleam00/second-brain-starter` (interview → plan → rollout). Clone one, bolt the notarial layer (Part IV) on top.

### 22. Quick start

1. Install Obsidian + Claude Code.
2. Create the folders (§5) or ask Claude Code.
3. Set up `CLAUDE.md` (§8) — schema + interview.
4. Put `kepano/obsidian-skills` into `.claude/` (§9).
5. Open the door: the Local REST API plugin + MCP (§6–7).
6. Set up TimeLayer, install the verifier, write the thin notarization/checking script (§13, §16).
7. **Ingest:** drop an article into `raw/`, run processing (§10).
8. **Query:** ask a question, the valuable answer — into `outputs/` (§11).
9. **Lint:** run the check — grounding, receipts, the gates (§12, §15).
10. Put the cycle on 7 a.m. (§17). Repeat — each pass makes the base richer and more provable.

---

## What you end up with

Work at it for a week — it's a notes app. A month — a reference system. Half a year — a knowledge engine that **compounds instead of being rediscovered**: every new note links up with everything already there. On top of this, the notarial layer gives you **provable discipline**: a wiki where every claim is anchored to a source, the "verified" status can't be drawn on, and any silent edit gives itself away and revokes trust.

But soberly: you get **guardianship of the process and of accountability**, not a guarantee of truth. The mechanism forces the check to happen, makes it unforgeable and attributable, and automatically invalidates everything that was changed. Correctness itself is produced by the checker — the choice of *who* and *what* stands in the Lint gate is the principal engineering decision in the whole build.

The same subscription. A fundamentally different machine — and now it also won't let you lie that the check happened.

*Methodology: Andrej Karpathy, LLM Knowledge Base ([gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)). Wiring: the "Second Brain on Claude + Obsidian" guide. Notarization: TimeLayer.*
