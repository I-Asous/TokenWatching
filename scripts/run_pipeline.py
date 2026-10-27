"""
Runs your own prompt through the agent pipeline (Auditor -> Optimizer -> lock check -> Validator)
and prints the result. Makes real Claude API calls.

The prompt can come from an argument, a file, or typed in (finish with Ctrl-D on a new line).

Usage: python3 scripts/run_pipeline.py ["prompt"] [--file prompt.txt] [--target chatgpt|claude]

# type or paste it (multi-line is fine), then press Ctrl-D on a new line
python3 scripts/run_pipeline.py

# pass it as an argument
python3 scripts/run_pipeline.py "Please could you kindly write me a poem about cats"

# read it from a file
python3 scripts/run_pipeline.py --file my_prompt.txt
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from agents.orchestrator import runPipeline  # noqa: E402
from agents.tokens import DEFAULT_TARGET, TARGETS  # noqa: E402


def readPrompt(args) -> str:
    if args.prompt:
        return args.prompt
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        print("Type or paste your prompt, then press Ctrl-D on a new line:\n")
    return sys.stdin.read()


def main():
    parser = argparse.ArgumentParser(description="Run a prompt through the Token Watching pipeline.")
    parser.add_argument("prompt", nargs="?", help="the prompt to optimize (omit to type it in)")
    parser.add_argument("--file", help="read the prompt from this file")
    parser.add_argument("--target", choices=TARGETS, default=DEFAULT_TARGET,
                        help=f"LLM whose tokenizer is used for counts (default: {DEFAULT_TARGET})")
    args = parser.parse_args()

    prompt = readPrompt(args).strip()
    if not prompt:
        sys.exit("No prompt given.")

    print("\nRunning pipeline...\n")
    result = runPipeline(prompt, args.target)

    print("Original:", result.originalPrompt)
    print()
    print("Final:", result.finalPrompt)
    print()
    print("Optimized:", result.wasOptimized)
    print("Audit severity:", result.auditResult.severity)
    print("Audit issues:", result.auditResult.issues)
    print()
    summary = {
        "attempts": [
            {
                "attempt": i,
                "score": attempt.qualityScore,
                "passed": attempt.passed,
                "reason": attempt.reasoning,
            }
            for i, attempt in enumerate(result.attempts, start=1)
        ],
        "vagueness": result.vagueness.level,
        "clarifyingQuestions": result.vagueness.questions,
    }
    if result.wasOptimized:
        summary["changes"] = result.changes
        summary["tokensSaved"] = result.tokensSaved
        summary["percentSaved"] = result.percentSaved
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
