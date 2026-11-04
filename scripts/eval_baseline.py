"""
Runs every prompt in an eval set through the agent pipeline and records how it did: what came out (optimized,
unchanged, accepted by the filler-only check, clarifying questions), tokens saved, whether anything the prompt needed was dropped,
Validator results, Optimizer turns, LLM calls, API tokens and latency. Makes real Claude API calls.

Run it before changing the agents to get a baseline, then again after, and compare the two summaries.
LLM output varies between runs, so use --repeat to average over a few runs before trusting a difference.

Usage:
python3 scripts/eval_baseline.py [--label baseline] [--repeat 1] [--only id-or-category ...] [--target chatgpt|claude]
python3 scripts/eval_baseline.py --compare evals/results/baseline.summary.json evals/results/phase1.summary.json
python3 scripts/eval_baseline.py --summarize phase1 [--saved-price-model claude-opus-5-5]

Costs come from config/prices.yaml: what the pipeline's own API calls cost, what the tokens it saved are worth
on one send, the net of the two, and how many sends each saved prompt needs to pay the pipeline back.
--summarize recomputes a run's summary from its saved records, with no API calls.

Each run writes evals/results/<label>.jsonl (one record per prompt per repeat) and <label>.summary.json.
"""
import argparse
import json
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
#agents/hooks imports schema from the backend, same as tests/conftest.py
sys.path.insert(0, str(REPO / "backend"))
load_dotenv(REPO / ".env")

from agents import optimizer, tokens, validator  # noqa: E402
from agents.hooks.orchestrator import OrchestrationHooks  # noqa: E402
from agents.optimizer import findRewriteProblems  # noqa: E402
from agents.orchestrator import fillerOnlyValidation, runPipeline  # noqa: E402
from agents.tokens import DEFAULT_TARGET, TARGETS  # noqa: E402

DEFAULT_CASES = REPO / "evals" / "prompts.jsonl"
RESULTS_DIR = REPO / "evals" / "results"
PRICES_FILE = REPO / "config" / "prices.yaml"
#The usage fields an API call is billed for, as the recorder stores them
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
#The modules whose Anthropic client makes the pipeline's LLM calls, by the agent name they're recorded under.
#The Auditor no longer makes its own LLM call (11/4/2026: folded into the Optimizer's own first look, see
#orchestrator.MIN_TOKENS_TO_LET_OPTIMIZER_LOOK), so it's no longer one of these
LLM_AGENTS = {"optimizer": optimizer, "validator": validator}
OUTCOMES = ("optimized", "fillerOnly", "unchanged", "ask", "error", "crash")
#What each "expect" in the eval set accepts as a match
EXPECTED_OUTCOMES = {
    "optimize": {"optimized", "fillerOnly"},
    "unchanged": {"unchanged"},
    "ask": {"ask"},
}


"""
* @brief Loads the prices the eval's costs are computed with, from config/prices.yaml.
* @post
* 1. Returns (prices, savedTokenPrice). prices maps each model to its USD price per token for every
*    USAGE_KEYS field: cache reads are the input price less cache_read_discount, cache writes the input
*    price times cache_write_multiplier (the agents use the 5-minute cache).
* 2. savedTokenPrice is the input price per token of savedModel, or of the file's saved_token_model:
*    what one token cut from a person's prompt is worth on a single send.
* 3. An unknown savedModel raises a KeyError naming it.
"""
def loadPricing(savedModel: str | None = None, path: Path = PRICES_FILE) -> tuple[dict[str, dict[str, float]], float]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    modifiers = config["modifiers"]
    prices = {}
    for model, price in config["models"].items():
        inputPrice = price["input"] / 1_000_000
        prices[model] = {
            "input_tokens": inputPrice,
            "output_tokens": price["output"] / 1_000_000,
            "cache_read_input_tokens": inputPrice * (1 - modifiers["cache_read_discount"]),
            "cache_creation_input_tokens": inputPrice * modifiers["cache_write_multiplier"],
        }
    savedModel = savedModel or config["saved_token_model"]
    if savedModel not in prices:
        raise KeyError(f"No price for {savedModel} in {path.name}")
    return prices, prices[savedModel]["input_tokens"]


def loadCases(path: Path) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for case in cases:
        case.setdefault("mustKeep", [])
        case.setdefault("category", "other")
        case.setdefault("expect", None)
    return cases


"""
* @brief Records every LLM call the agents make while a prompt runs.
* @post
* 1. Each agent module's client.messages.create is wrapped once; the real call still runs.
* 2. Each call adds the agent, model, latency, stop reason and token usage (cache reads and writes
*    included) to calls, or the error type if it raised (the error is re-raised unchanged).
* 3. With target "claude", count_tokens calls are recorded too, under "count_tokens".
"""
class CallRecorder:
    def __init__(self, target: str):
        self.calls: list[dict] = []
        for name, module in LLM_AGENTS.items():
            module.client.messages.create = self.wrap(name, module.client.messages.create)
        if target == tokens.CLAUDE:
            tokens.client.messages.count_tokens = self.wrap("count_tokens", tokens.client.messages.count_tokens)

    def wrap(self, agent: str, create):
        def recorded(*args, **kwargs):
            call = {"agent": agent, "model": kwargs.get("model")}
            start = time.perf_counter()
            try:
                response = create(*args, **kwargs)
            except Exception as error:
                call["error"] = type(error).__name__
                raise
            finally:
                call["latencyMs"] = round((time.perf_counter() - start) * 1000)
                self.calls.append(call)
            usage = getattr(response, "usage", None)
            call["stopReason"] = getattr(response, "stop_reason", None)
            for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                call[key] = getattr(usage, key, None) or 0
            return response
        return recorded


#Records the pipeline's stages and the Optimizer's choices through the orchestrator's own hooks
class RecordingHooks(OrchestrationHooks):
    def __init__(self):
        self.stages: list[str] = []
        self.actions: list[str] = []

    def updateStage(self, status: str):
        self.stages.append(status)

    def saveOptimization(self, result):
        self.actions.append(result.action)


#"fillerOnly" is a rewrite accepted by the local deletion-only check with no Validator verdict (the local rewrite,
#or an Optimizer rewrite that only deleted filler); "optimized" is one the Validator passed
def outcomeOf(result) -> str:
    if result.needsClarification:
        return "ask"
    if result.wasOptimized:
        accepted = result.attempts[-1] if result.attempts else None
        if accepted and accepted.reasoning == fillerOnlyValidation("", "").reasoning:
            return "fillerOnly"
        return "optimized"
    return "error" if result.error else "unchanged"


#"ask" also matches an unchanged prompt the vagueness report rates vague, since its questions come back on the
#result for the extension to ask (backend/schema/orchestration.py takes answers to either kind)
def expectMet(expect: str | None, outcome: str, result) -> bool | None:
    if not expect:
        return None
    if expect == "ask" and outcome == "unchanged" and result.vagueness.level == "vague" and result.vagueness.questions:
        return True
    return outcome in EXPECTED_OUTCOMES[expect]


"""
* @brief Runs one eval case through runPipeline and builds its record.
* @post
* 1. The Auditor's review cache and the token caches are cleared first, so every run pays for its
*    own calls and repeats measure the same thing.
* 2. An exception from runPipeline is recorded as outcome "crash" instead of stopping the eval.
* 3. The record has the outcome and whether it matched the case's expect, savings, every mustKeep
*    string missing from the final prompt (case-insensitive), what findRewriteProblems finds in an
*    optimized prompt, every attempt's score and verdict (Validator, lock check or filler-only check),
*    LLM calls per agent and API tokens per model, and latency.
"""
def runCase(case: dict, target: str, recorder: CallRecorder, repeat: int = 0) -> dict:
    tokens.countTokens.cache_clear()
    tokens.estimateTokens.cache_clear()
    recorder.calls = []
    hooks = RecordingHooks()
    record = {"id": case["id"], "category": case["category"], "expect": case["expect"], "repeat": repeat}

    start = time.perf_counter()
    try:
        result = runPipeline(case["prompt"], target, hook=hooks)
    except Exception as error:  # pylint: disable=broad-except
        result = None
        record["crash"] = f"{type(error).__name__}: {error}"
    record["latencyMs"] = round((time.perf_counter() - start) * 1000)
    record["stages"] = hooks.stages
    record["optimizerActions"] = hooks.actions
    record.update(summarizeCalls(recorder.calls))

    if result is None:
        record["outcome"] = "crash"
        record["expectMet"] = False
        return record

    finalPrompt = result.finalPrompt
    record["outcome"] = outcomeOf(result)
    record["vaguenessLevel"] = result.vagueness.level
    record["vaguenessQuestions"] = result.vagueness.questions
    record["expectMet"] = expectMet(case["expect"], record["outcome"], result)
    record["error"] = result.error
    record["promptTypes"] = result.promptTypes
    record["originalTokens"] = result.auditResult.token_count
    record["tokensSaved"] = result.tokensSaved
    record["percentSaved"] = result.percentSaved
    record["auditIssues"] = len(result.auditResult.issues)
    record["finalPrompt"] = finalPrompt
    record["questions"] = result.questions
    record["missingMustKeep"] = [keep for keep in case["mustKeep"] if keep.lower() not in finalPrompt.lower()]
    record["rewriteProblems"] = findRewriteProblems(case["prompt"], finalPrompt) if result.wasOptimized else []
    record["attemptScores"] = [attempt.qualityScore for attempt in result.attempts]
    record["attemptPassed"] = [attempt.passed for attempt in result.attempts]
    #Why each attempt passed or failed, so a rejection can be read without the database
    record["attemptReasons"] = [attempt.reasoning for attempt in result.attempts]
    return record


def summarizeCalls(calls: list[dict]) -> dict:
    perAgent = Counter(call["agent"] for call in calls)
    perModel: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for call in calls:
        usage = perModel[call["model"] or "unknown"]
        for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            usage[key] += call.get(key, 0)
    return {
        "llmCalls": sum(count for agent, count in perAgent.items() if agent != "count_tokens"),
        "callsPerAgent": dict(perAgent),
        "optimizerTurns": perAgent.get("optimizer", 0),
        "validatorCalls": perAgent.get("validator", 0),
        "llmLatencyMs": sum(call["latencyMs"] for call in calls if call["agent"] != "count_tokens"),
        "callErrors": [f'{call["agent"]}: {call["error"]}' for call in calls if "error" in call],
        "tokensPerModel": {model: dict(usage) for model, usage in perModel.items()},
    }


#Nearest-rank percentile, so p95 of 40 runs is a real run's latency
def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def rate(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


#USD, rounded so a fraction of a cent still shows
def usd(amount: float) -> float:
    return round(amount, 6)


"""
* @brief Turns every record from a run into the numbers to compare between runs.
* @post Rates are fractions (0-1) rounded to 3 places, None when nothing could be measured. The same
* keys are always present, so two summaries can be compared key by key.
* Costs use pricing (loadPricing, read from config/prices.yaml when not given):
* 1. pipelineCostUsd is what the run's API calls cost, from each model's token usage. A model with usage
*    but no price is listed in unpricedModels and left out of the cost, so the cost is then too low.
*    Calls that raised (timeouts) report no usage, so they're never counted.
* 2. savedValueUsd is totalTokensSaved at the saved-token price, for one send of each prompt.
* 3. netSavingsUsd is savedValueUsd minus pipelineCostUsd, and breakEvenSends how many times each
*    optimized prompt would have to be sent for the savings to cover the pipeline (None if nothing was saved).
"""
def summarize(records: list[dict], pricing: tuple[dict[str, dict[str, float]], float] | None = None) -> dict:
    prices, savedTokenPrice = pricing or loadPricing()
    ran = [record for record in records if record["outcome"] != "crash"]
    optimized = [record for record in ran if record["outcome"] in ("optimized", "fillerOnly")]
    withExpect = [record for record in ran if record.get("expect")]
    optimizerRan = [record for record in records if record["optimizerTurns"]]
    llmLatencies = [record["latencyMs"] for record in records if record["llmCalls"]]
    outcomes = Counter(record["outcome"] for record in records)

    byCategory = defaultdict(list)
    for record in withExpect:
        byCategory[record["category"]].append(record["expectMet"])

    tokensPerModel: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for record in records:
        for model, usage in record["tokensPerModel"].items():
            for key, value in usage.items():
                tokensPerModel[model][key] += value

    costPerModel = {model: sum(usage.get(key, 0) * prices[model][key] for key in USAGE_KEYS)
                    for model, usage in tokensPerModel.items() if model in prices}
    unpricedModels = sorted(model for model, usage in tokensPerModel.items()
                            if model not in prices and any(usage.values()))
    pipelineCost = sum(costPerModel.values())
    totalTokensSaved = sum(record["tokensSaved"] for record in ran)
    savedValue = totalTokensSaved * savedTokenPrice

    return {
        "runs": len(records),
        "outcomes": {outcome: outcomes.get(outcome, 0) for outcome in OUTCOMES},
        "expectMatchRate": rate(sum(record["expectMet"] for record in withExpect), len(withExpect)),
        "expectMatchByCategory": {category: rate(sum(met), len(met)) for category, met in sorted(byCategory.items())},
        "expectMisses": sorted({record["id"] for record in withExpect if not record["expectMet"]}),
        "optimizedRate": rate(len(optimized), len(ran)),
        "totalOriginalTokens": sum(record["originalTokens"] for record in ran),
        "totalTokensSaved": totalTokensSaved,
        "meanPercentSavedAll": mean([record["percentSaved"] for record in ran]),
        "meanPercentSavedOptimized": mean([record["percentSaved"] for record in optimized]),
        "mustKeepViolations": sorted({record["id"] for record in ran if record["missingMustKeep"]}),
        "rewriteProblemCases": sorted({record["id"] for record in ran if record["rewriteProblems"]}),
        "validatorCalls": sum(record["validatorCalls"] for record in records),
        "attemptPassRate": rate(sum(record["attemptPassed"].count(True) for record in ran),
                                sum(len(record["attemptPassed"]) for record in ran)),
        "firstAttemptPassRate": rate(sum(bool(record["attemptPassed"]) and record["attemptPassed"][0]
                                         for record in optimizerRan),
                                     sum(bool(record["attemptPassed"]) for record in optimizerRan)),
        "optimizerRuns": len(optimizerRan),
        "optimizerTurnsMean": mean([record["optimizerTurns"] for record in optimizerRan]),
        "optimizerTurnsMax": max((record["optimizerTurns"] for record in optimizerRan), default=None),
        "optimizerTurnsDistribution": dict(sorted(Counter(record["optimizerTurns"] for record in optimizerRan).items())),
        "llmCallsMean": mean([record["llmCalls"] for record in records]),
        "llmCallsTotal": sum(record["llmCalls"] for record in records),
        "latencyMsP50": percentile([record["latencyMs"] for record in records], 50),
        "latencyMsP95": percentile([record["latencyMs"] for record in records], 95),
        "latencyMsP50WithLLM": percentile(llmLatencies, 50),
        "latencyMsP95WithLLM": percentile(llmLatencies, 95),
        "latencyMsMax": max((record["latencyMs"] for record in records), default=None),
        "apiErrors": sum(len(record["callErrors"]) for record in records),
        "crashes": sorted({record["id"] for record in records if record["outcome"] == "crash"}),
        "tokensPerModel": {model: dict(usage) for model, usage in sorted(tokensPerModel.items())},
        "pipelineCostUsd": usd(pipelineCost),
        "pipelineCostPerRunUsd": usd(pipelineCost / len(records)) if records else None,
        "pipelineCostPerLLMRunUsd": usd(pipelineCost / len(llmLatencies)) if llmLatencies else None,
        "pipelineCostPerModelUsd": {model: usd(cost) for model, cost in sorted(costPerModel.items())},
        "unpricedModels": unpricedModels,
        "savedValueUsd": usd(savedValue),
        "netSavingsUsd": usd(savedValue - pipelineCost),
        "breakEvenSends": round(pipelineCost / savedValue, 1) if savedValue else None,
    }


def printSummary(summary: dict):
    width = max(len(key) for key in summary)
    for key, value in summary.items():
        print(f"{key:<{width}}  {json.dumps(value) if isinstance(value, (dict, list)) else value}")


#Prints each number from two summaries side by side with the change, for the keys whose values are numbers
def compare(beforePath: Path, afterPath: Path):
    before = json.loads(beforePath.read_text(encoding="utf-8"))
    after = json.loads(afterPath.read_text(encoding="utf-8"))
    width = max(len(key) for key in before)
    print(f"{'':<{width}}  {'before':>10}  {'after':>10}  {'change':>10}")
    for key in before:
        old, new = before[key], after.get(key)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)) and not isinstance(old, bool):
            print(f"{key:<{width}}  {old:>10}  {new:>10}  {round(new - old, 3):>+10}")
        elif old != new:
            print(f"{key:<{width}}  before: {json.dumps(old)}\n{'':<{width}}  after:  {json.dumps(new)}")


def main():
    parser = argparse.ArgumentParser(description="Run the eval set through the pipeline and summarize it.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="eval set, one JSON case per line")
    parser.add_argument("--label", default="baseline", help="name for the results files (default: baseline)")
    parser.add_argument("--repeat", type=int, default=1, help="run every case this many times (default: 1)")
    parser.add_argument("--only", nargs="+", help="run only cases with these ids or categories")
    parser.add_argument("--target", choices=TARGETS, default=DEFAULT_TARGET,
                        help=f"LLM whose tokenizer is used for counts (default: {DEFAULT_TARGET})")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"),
                        help="compare two summary files instead of running")
    parser.add_argument("--summarize", metavar="LABEL",
                        help="rewrite LABEL's summary from its saved records instead of running (no API calls), "
                             "e.g. to add costs to an older run or reprice it")
    parser.add_argument("--saved-price-model", metavar="MODEL",
                        help="model in config/prices.yaml whose input price values a saved token "
                             "(default: the file's saved_token_model)")
    args = parser.parse_args()

    if args.compare:
        compare(*args.compare)
        return

    pricing = loadPricing(args.saved_price_model)
    if args.summarize:
        recordsPath = RESULTS_DIR / f"{args.summarize}.jsonl"
        records = [json.loads(line) for line in recordsPath.read_text(encoding="utf-8").splitlines() if line.strip()]
        writeSummary(records, RESULTS_DIR / f"{args.summarize}.summary.json", pricing)
        return

    cases = loadCases(args.cases)
    if args.only:
        cases = [case for case in cases if case["id"] in args.only or case["category"] in args.only]
    if not cases:
        sys.exit("No cases to run.")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    recordsPath = RESULTS_DIR / f"{args.label}.jsonl"
    summaryPath = RESULTS_DIR / f"{args.label}.summary.json"
    recorder = CallRecorder(args.target)
    records = []
    with recordsPath.open("w", encoding="utf-8") as out:
        for repeat in range(args.repeat):
            for index, case in enumerate(cases, start=1):
                record = runCase(case, args.target, recorder, repeat)
                records.append(record)
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                mark = {True: "ok  ", False: "MISS", None: "    "}[record["expectMet"]]
                print(f"[{repeat + 1}/{args.repeat} {index:>2}/{len(cases)}] {mark} {record['id']:<24} "
                      f"{record['outcome']:<9} saved {record.get('percentSaved', 0):>5}%  "
                      f"llm {record['llmCalls']}  {record['latencyMs']} ms")
                #Every later call would fail the same way, and the fallbacks would make the run look real
                if any(error.endswith("AuthenticationError") for error in record["callErrors"]):
                    sys.exit("\nStopped: the Anthropic API rejected the key (401). If ANTHROPIC_API_KEY is "
                             "exported in your shell, it's used instead of the one in .env.")

    summary = writeSummary(records, summaryPath, pricing)
    print(f"\nRecords: {recordsPath.relative_to(REPO)}")
    #A failed call falls back to the original or local rewrite, so the run still finishes and looks plausible
    if summary["apiErrors"]:
        print(f"\nWARNING: {summary['apiErrors']} API calls failed; these numbers don't measure the agents. "
              "See callErrors in the records.")


#Summarizes the records, writes the summary file and prints it, warning about any model it couldn't price
def writeSummary(records: list[dict], summaryPath: Path, pricing: tuple[dict[str, dict[str, float]], float]) -> dict:
    summary = summarize(records, pricing)
    summaryPath.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print()
    printSummary(summary)
    print(f"\nSummary: {summaryPath.relative_to(REPO)}")
    if summary["unpricedModels"]:
        print(f"\nWARNING: no price in {PRICES_FILE.name} for {', '.join(summary['unpricedModels'])}; "
              "pipelineCostUsd leaves their calls out.")
    return summary


if __name__ == "__main__":
    main()
