# A second brain on receipts

**English** · [Русский](README.ru.md)

**A knowledge base your hand doesn't keep — and that cannot quietly lie.**

Andrej Karpathy's [LLM Knowledge Base](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
pattern (`raw/` → `wiki/`, the Ingest/Query/Lint cycle) plus a **notarial correctness layer**
on [TimeLayer](https://timelayer-os.com) receipts: every claim in the wiki is anchored to a
source fragment, and the status "verified" is not a checkbox — it's a **receipt over the hash
of the current text**. Edit the text and the status falls off by itself.

> **The honest model.** A receipt proves that *a check ran over exactly these words, who is
> accountable for it, and that the text was not changed afterwards*. It does **not** prove the
> content is true. A notarized error is still an error — only now it's visible who checked what.
> Correctness comes from the checker (mechanics / model / human), not from the receipt itself.

---

## What's inside

| File | What it is |
|---|---|
| `brain-notary-guide.md` | The full guide: why, how it works, how to build it from scratch |
| `CLAUDE.md` | Constitution for the maintainer agent (drop it in the root of your vault) |
| `notary.py` | The CLI layer: notarizing sources, grounding checks, the trusted gate |
| `wiki/_templates/page.md` | Wiki-page template with source-anchoring discipline |
| `example/` | A working example: a source + a page that passes verification |

## How it works in three words

1. **Ingest** — you put a source in `raw/`, the agent writes pages in `wiki/`, every claim
   carries a pointer to a specific source fragment and the hash of its version.
2. **Verify** — `notary.py` checks claims against the source (numbers and quotes mechanically,
   meaning via a judge model), and for those that pass it takes a **receipt** from the network,
   bound to the hash of `text + sources + verdict`. Only then does the page become `trusted`.
3. **Audit** — any edit changes the hash; `audit` instantly strips `trusted`.
   "Verified" is a computed property, not a flag taken on faith.

> **The notary is a witness, not a guard.** A receipt proves *what* was notarized and *when* — it
> makes any later change **detectable** (tamper-evident), not **impossible** (tamper-proof). Anyone
> holding a vault write key can still rewrite a page and re-notarize it; what protects the base is
> key custody, not the receipt. Two tiers reflect how strong the tie is: `trusted` means the
> verifier **cryptographically bound** the receipt to the current content; `trusted-mechanical`
> means it's valid and the hash matches, but the installed verifier can't bind to the content yet,
> so the tie rests on a plaintext field a key-holder could forge. Re-certify with a
> binding-capable verifier to reach full `trusted`.

---

## Quick start

Works on **Linux, macOS and Windows**. You only need Python 3.8+ and one library.

**1. Dependencies**
```bash
pip install -r requirements.txt        # this is just pyyaml; everything else is the standard library
```

**2. Buy receipts and issue a token.** Receipts are the "fuel" of verification: each
notarization spends one. Create an account and buy a pack at **https://timelayer-os.com**,
then issue an `api_token` in the cabinet at https://cabinet.timelayer-os.com.

**3. Download the offline verifier** for your OS (Linux / macOS / Windows). Use **v1.4.0 or
later** — it adds the `--expect` content binding the notary uses to grant the full `trusted`
tier (older verifiers still work but cap pages at `trusted-mechanical`):
**https://github.com/TimeLayer-OS/timelayer-verifier/releases/tag/v1.4.0**
(latest: https://github.com/TimeLayer-OS/timelayer-verifier/releases/latest).

**4. Set the environment**

Linux / macOS:
```bash
export TIMELAYER_TOKEN=<your token>
export TL_VERIFIER=/path/to/timelayer-verifier
```
Windows (PowerShell):
```powershell
$env:TIMELAYER_TOKEN = "<your token>"
$env:TL_VERIFIER = "C:\path\to\timelayer-verifier.exe"
```

**5. Scaffold a vault and run the example** (identical on every OS):
```bash
python notary.py init my-vault            # creates the vault structure with no shell commands
python notary.py ingest-source example/raw/articles/2026-06-29-sample.md   # notarize the source
python notary.py verify example/wiki/sample-page.md      # → PASS → trusted
python notary.py audit  example/wiki/sample-page.md      # → trusted holds
#  edit a number in the page — run audit again → trusted is stripped
```
> For the example, set the vault root: `VAULT=example` (Linux/macOS) or
> `$env:VAULT="example"` (Windows), or run from inside the `example` folder.

### Commands

```
python notary.py init [dir]                # scaffold the vault structure (cross-platform)
python notary.py hash <raw-file>           # sha256 of a source (for pointers in wiki)
python notary.py ingest-source <raw-file>  # hash + source receipt
python notary.py verify <wiki-page>        # grounding + receipt + trusted gate
python notary.py verify-all                # same across all wiki/ pages
python notary.py audit  <wiki-page>        # strip trusted if changed after notarization
python notary.py audit-all
```

---

## The judge (for semantic claims)

Numbers and quotes are checked mechanically and work out of the box. Semantic claims are
checked by a **judge model** — set it with a command:

```bash
export TL_JUDGE_CMD='python my_judge.py'   # reads the prompt from stdin → prints {"cls":...,"span":...}
```

Use a **different model family** for the judge than the one that wrote the wiki (error
decorrelation). If `TL_JUDGE_CMD` is not set, semantic claims are marked unverified
(fail-closed): the page won't get `trusted` until you wire up a judge or confirm it by hand.
Better "not notarized" than "notarized for nothing."

---

## Environment variables

| Variable | Purpose |
|---|---|
| `TIMELAYER_TOKEN` | api_token from the cabinet (required to notarize) |
| `VAULT` | the vault root (defaults to the current folder) |
| `TL_VERIFIER` | path to the `timelayer-verifier` binary (defaults to `PATH`) |
| `TL_JUDGE_CMD` | the judge-model command (optional) |

---

## License

[Apache-2.0](LICENSE).
