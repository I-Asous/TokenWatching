"""
Measures CLAUDE_TOKEN_RATIO in agents/tokens.py: how many Claude tokens (from Anthropic's count_tokens
endpoint) a prompt takes per o200k_base token. The Optimizer's tool loop uses this ratio to estimate
Claude counts locally instead of calling count_tokens on every draft.

Calls count_tokens once per sample (free, but needs ANTHROPIC_API_KEY). Re-run it when
CLAUDE_COUNT_MODEL changes, or with real prompts once there are some.

Usage: python3 scripts/calibrate_claude_tokens.py [prompt files...]
Each file is one prompt. With no files, the Optimizer's worked examples and a few extra samples are used.
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
load_dotenv(REPO / ".env")

from agents import tokens  # noqa: E402
from agents.optimizer import OPTIMIZER_EXAMPLES  # noqa: E402

EXTRA_SAMPLES = [
    "Write a Python function that checks a user's password. Never log the password. Must follow our GDPR policy.",
    "Summarize this article and cite your sources: https://example.com/study",
    "1. Pull the latest data.\n2. Remove duplicates.\n3. If the file is empty, stop. Otherwise email the report.",
    "You are a SQL assistant. Please write queries for our `orders` table. Always use parameterized queries "
    "to prevent SQL injection. Never return more than 100 rows.",
    "Fix this:\n```python\ndef add(a, b): return a - b\n```\nIt returns -1 for add(1, 2) instead of 3.",
    "Hey, I'm working on a presentation for my team about our Q3 results and I was hoping you could help me "
    "put together an outline. We grew revenue by 12% but churn went up a little, so I want to be honest about "
    "that while keeping the tone positive. It should be around 10 slides and aimed at non-technical people.",
]


def main():
    samples = [Path(path).read_text(encoding="utf-8") for path in sys.argv[1:]]
    samples = samples or [prompt for prompt, _ in OPTIMIZER_EXAMPLES] + EXTRA_SAMPLES

    totalLocal = totalClaude = 0
    for sample in samples:
        local = tokens.localTokenCount(sample)
        claude = tokens.countClaudeTokens(sample)
        totalLocal += local
        totalClaude += claude
        print(f"{claude / local:5.2f}  o200k {local:4}  claude {claude:4}  {sample[:60]!r}")
    print(f"\nCLAUDE_TOKEN_RATIO = {totalClaude / totalLocal:.2f}  ({len(samples)} samples, {tokens.CLAUDE_COUNT_MODEL})")


if __name__ == "__main__":
    main()
