> **This repository follows the Receipts + Brain method.** It is universal — it applies to any agentic or multi-agent project, not only a brain built on this template. The owner supplies the repo, the brain-vault, and keys at the start of a session. See also the Russian edition: [`AGENTS.ru.md`](AGENTS.ru.md).

# The agent working method: Receipts + Brain

This is a guide to a **way of working**, not to any one project. Any agent that takes on a
repair, an audit, or any multi-step task works by this logic. The owner supplies the repository
link, the brain-vault link, and keys/access at the start of the session. Your job is not to
"look done" — it is to close every item with proof.

The method delivers: **work in one pass**, nothing breaks, the agent doesn't get lost, and any
result can be re-checked after the fact — from commits, tests, sha, and the log.

---

## Why it works (a practical observation)

Two simple rules cure the two chronic failures of agents — claiming "done" without proof, and
losing context between steps. In practice the effect is:

- **One pass instead of many.** A well-framed task runs as **one audit → one repair**, with no
  "redo it" loops. The agent doesn't circle back, because every step is closed with proof, not
  a promise.
- **Feed the spec through the brain — much faster, far cheaper.** Load the specification and
  plan into the brain (external state) first, then work from it, and the task gets done **several
  times faster and with markedly fewer tokens**: the agent doesn't re-read everything or hold
  context in one bloated window — it picks up the current state and continues from where it left off.
- **Higher quality.** Verifying against code and receipts, not words, removes silent errors and
  regressions before they pile up.

In short: **think with the brain (external state), close with a receipt (proof), verify against
the code (not against words).**

---

## 1. Two pillars

**RECEIPT** — no item counts as done without proof. Proof is not "I fixed it" — it is a
checkable fact: a commit hash, a test result (red → green), command output, an external check.
No receipt → the item is open.

**BRAIN** (external state vault) — plans, an action log, and decisions live not in one pass's
memory but in durable storage (a repository-vault). State survives between sessions, so you don't
hold everything in your head and nothing gets confused.

---

## 2. Ticket discipline

Each unit of work = a TICKET. A ticket has a status and a mandatory receipt on close.

Statuses: **open** (hole described, untouched) · **in progress** · **closed** (done, with a
receipt — closing without one is forbidden) · **deferred** (with an explicit reason: maintenance
window / condition / dependency).

A ticket body always contains:
1. **Root** — what exactly is wrong, with an exact address (`file:line`, not "somewhere in the module").
2. **Action** — what specifically to do.
3. **Acceptance criterion** — how you'll know the hole is closed (which test/check proves it).
4. **Receipt** — filled in at close (the proof).

Example of a closed ticket:
```
## A2 — [HIGH] Client with no timeout freezes the loop
open → closed
Root: src/info_client.rs:23 — Client::new() with no timeout.
Action: builder with timeout(8s)/connect_timeout(5s).
Acceptance: test with a mock server silent >8s → timeout error, no hang.
Receipt:
- Edited info_client.rs:23. Test client_times_out red→green. 153 passed; 0 failed.
- Commit <hash>. Deployed; binary sha changed from <old> to <new>.
```

---

## 3. What counts as a receipt (by kind of work)

| Kind of work | Valid receipt |
|---|---|
| Code change | commit hash + test red→green + `N passed; 0 failed` |
| Deploy | binary sha256 **before and after** + confirmation it's live on every required host |
| Infra/config | command output BEFORE and AFTER (e.g. `iptables -L -n`, external connect → refused) |
| Checking someone's work | confirmation from code/binary (grep the change, compare sha), **not** from their report |
| "False alarm" | proof of why the finding is wrong (walk the logic/math), then revert |
| Deferred | reason + resume condition + where the catch-up plan is recorded |

Rule: a receipt must be **reproducible by someone else**. If it can't be re-checked, it isn't a receipt.

---

## 4. Working with GitHub (code = source of truth)

1. The owner gives the repo link and access. You work in it, not from retellings.
2. Each change = a separate commit with a clear message: **what** was fixed and **why**. The
   commit hash is part of the receipt.
3. Before writing "done" you run the tests and paste their result into the receipt.
4. On a release build, record the artifact's sha256. On deploy, verify the **same** sha is live
   on every host.
5. **Verify from code, not from a report.** Open the file, grep the change, compare the deployed
   binary's sha. A report can lie or lag — code and binary don't. An unchanged binary sha = the
   layer wasn't touched, whatever the report says.

---

## 5. Working with the BRAIN (state vault)

1. The owner gives the brain-vault link and access. It's separate durable storage for plans and
   the log (not the project's code).
2. What we keep in the brain:
   - **Plans** — repair/audit plan files with tickets (see §2). Each round gets its own plan;
     old ones aren't overwritten, they're referenced.
   - **Log (append-only)** — a feed: what was done, when, with what receipt. Append only.
3. **Session start: read the brain first** — the current plan and the latest log entries, to
   continue from where you left off rather than start over. (This is where the speed and token
   savings come from.)
4. End of an action: write the receipt into both the plan ticket and the log. An action with no
   brain entry is a lost action.
5. Link entries liberally (plan ↔ log ↔ findings) so state stays connected, not scattered.

---

## 6. The one-pass cycle

```
1. Read the brain: current plan + log (where you stopped).
2. Take the next open ticket by priority (critical → high → medium → low).
3. Find the root in the code (file:line), not from memory.
4. Make the change. Write a test for the original failure (red → green).
5. Build / run tests. Get the proof.
6. Close the ticket with a receipt. Write it into the log.
7. If it's a deploy — verify the sha on every host.
8. Move to the next ticket. Skip nothing silently:
   a skip/limit = its own entry, never silence.
```

---

## 7. Prioritizing findings

By descending money/security risk:
1. **CRITICAL** — active money loss / key exposure / data loss.
2. **HIGH** — a latent hole that fires on failure (network drop, restart, overflow).
3. **MEDIUM** — "present but not working" logic (dead gates, silent degradations).
4. **LOW** — polish, resilience to bad input, hygiene.

Critical closes first, polish last.

---

## 8. Iron rules (never break)

- **No receipt, no "done".** Words don't close a ticket.
- **Verify from code and binary, not from a report.** A report is a hypothesis; code is fact.
- **A test for the original failure is mandatory** for a non-trivial change (red → green).
- **Money/security: fail-closed by default.** In doubt, stop and ask — don't "roughly fix".
- **Don't break the neighbours.** A regression is also an open ticket; catch it with a check.
- **Silence is forbidden.** Any skip, limit, or deferral is an explicit brain entry.
- **Nothing irreversible without confirmation** (deploy to a live account, deletion, leader
  restart) — first prove it's safe, then do it, in a window.

---

## 9. What the method gives you

- Work in one pass: no circling back to redo.
- Nothing breaks: every change is backed by a test, regressions are caught by a check.
- The agent doesn't get lost: state lives in the brain, not in one context's head.
- Fewer tokens, more speed: spec and plan live in the brain instead of being re-read each time.
- Every result is re-checkable: from commits, tests, sha, and the log — later and by others.

Applies to any agentic / multi-agent system, not only to this project.
