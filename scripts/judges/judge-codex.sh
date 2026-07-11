#!/bin/zsh
# Судья смысловых утверждений для notary.py (TL_JUDGE_CMD).
# Семейство моделей: OpenAI (codex CLI) — НЕ Claude, декорреляция с автором вики (§П5).
# Контракт: промпт на stdin -> печатает ТОЛЬКО JSON {"cls":...,"span":...} в stdout.
# --output-last-message (-o) обязателен: голый stdout codex содержит эхо промпта с {скобками},
# что ломает жадный regex-парсер notary.py.
# Проверено в бою 2026-07-11 (три волта, ~190 утверждений). Скорость ~6 сек/голос.
set -u
PROMPT=$(cat)
OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT
codex exec --skip-git-repo-check -s read-only -c model_reasoning_effort='"low"' -o "$OUT" - <<< "$PROMPT" >/dev/null 2>&1
cat "$OUT"
