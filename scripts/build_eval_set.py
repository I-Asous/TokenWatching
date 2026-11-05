"""
Builds evals/prompts.jsonl, the eval set scripts/eval_baseline.py runs, from:
1. evals/sources/seed.jsonl: the first 71 hand-written cases, ids unchanged so earlier results still line up
2. evals/sources/hand-*.jsonl: hand-written edge cases, one file per theme
3. Cases composed here from CORES (direct, specific requests) and the waste pools below (greetings, request
   wrappers, closings, backstory, repeated instructions, wordy phrases, noise). Each one is labeled by measuring
   what its waste costs against the core's direct form, so no composed label is a judgment call

Labeling policy, for what the pipeline should do (not what it does today):
- optimize: a rewrite can cut at least POLICY_MIN_TOKENS tokens (o200k_base) and POLICY_MIN_PERCENT of the prompt
  without changing what it asks for: greetings, politeness, hedging, backstory that doesn't change the answer,
  repeated instructions, wordy phrases, decoration.
- unchanged: already direct; the cuttable part is under that bar (a lone "Please"); the words that look cuttable
  carry meaning (an option's "maybe", "thank you" as the subject, quoted, pasted or code material, context that
  changes the answer); a chat follow-up whose meaning comes from the conversation ("Keep going."); not English;
  or a prompt-injection attempt.
- ask: too vague to answer well without a question first: an action with nothing attached or no target ("Fix this.",
  "Translate this.", "Review my resume."). Vague beats filler: "Hi! Can you help with my essay? Thanks!" is ask.
English instructions around foreign-language material are English: the instructions can be cut, the material can't.

The bar is set here, not imported from agents/orchestrator.py, so tuning MIN_TOKENS_SAVED there can't move the
labels that judge it.

A hand-written case may give "direct", its shortest faithful rewrite. Its expect is then checked against the
measured saving, or set from it when expect is "auto". "direct" stays in the source file and isn't written out.

The build fails on a duplicate id, an unknown expect, a mustKeep string missing from its prompt (case-sensitive, as
tests/test_eval_baseline.py checks) or from its direct form (case-insensitive, as the eval checks rewrites), a label
that disagrees with its direct form, a repeated prompt, or a set that isn't TARGET_SIZE cases. It warns on
near-duplicate hand-written prompts.

Usage:
python3 scripts/build_eval_set.py           # rebuild evals/prompts.jsonl and print its make-up
python3 scripts/build_eval_set.py --check   # validate the sources and print the make-up, without writing
"""
#The cases below are a data table; wrapping every row under 100 characters would only make it harder to read
# pylint: disable=line-too-long
import argparse
import json
import random
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import tiktoken

REPO = Path(__file__).resolve().parent.parent
SOURCES = REPO / "evals" / "sources"
SEED_FILE = SOURCES / "seed.jsonl"
OUTPUT = REPO / "evals" / "prompts.jsonl"
TARGET_SIZE = 1000
RANDOM_SEED = 20261104
POLICY_MIN_TOKENS = 5
POLICY_MIN_PERCENT = 2.0
EXPECTS = ("optimize", "unchanged", "ask")
#Word 3-gram overlap at or above this between two hand-written prompts is reported as a near-duplicate
NEAR_DUPLICATE = 0.8
#Key order of each written case
FIELDS = ("id", "category", "prompt", "mustKeep", "expect", "source")
ENCODING = tiktoken.get_encoding("o200k_base")


def countTokens(text: str) -> int:
    return len(ENCODING.encode(text))


#The policy label for a prompt whose shortest faithful rewrite is direct
def measuredLabel(prompt: str, direct: str) -> str:
    total = countTokens(prompt)
    saved = total - countTokens(direct)
    return "optimize" if total and saved >= POLICY_MIN_TOKENS and saved / total * 100 >= POLICY_MIN_PERCENT \
        else "unchanged"


@dataclass(frozen=True)
class Core:
    slug: str
    head: str #the request, lowercase first ("write a haiku about rain"); with "q" in flags, a question
    tail: str #what follows it: sentences, or material on its own lines (starting with "\n")
    keep: tuple[str, ...]
    #q: a question, so no request wrapper; len: states a length; fmt: states a format; prose: writing with a tone
    flags: frozenset[str]

    @property
    def block(self) -> bool:
        return self.tail.startswith("\n")


#Markers in a core that a wordy variant spells out long. Each is only placed where both forms read correctly
WORDY = {
    "[to]": ("to", "in order to"),
    "[because]": ("because", "due to the fact that"),
    "[before]": ("before", "prior to"),
    "[if]": ("if", "in the event that"),
    "[now]": ("now", "at this point in time"),
    "[soon]": ("soon", "in the near future"),
    "[every]": ("every", "each and every"),
    "[although]": ("although", "despite the fact that"),
    "[first]": ("first", "first and foremost"),
    "[for]": ("for", "for the purpose of"),
}

#(slug, head, tail, mustKeep, flags). Every one is already direct and specific, so its plain form is "unchanged"
CORE_ROWS = [
    #Writing and email
    ("email-heater", "write an email to my landlord asking when the broken heater will be repaired",
     "Mention that it has been out since Monday.", ["landlord", "heater", "Monday"], "prose"),
    ("sick-day", "draft a message to my manager saying I'm out sick today and will be back tomorrow", "",
     ["manager", "out sick", "tomorrow"], "prose"),
    ("refund-blender", "write an email to an online store requesting a refund for a blender that arrived cracked",
     "Include order number 48213.", ["refund", "blender", "48213"], "prose"),
    ("standup-move", "write a note to my team moving Thursday's standup to 10:30", "", ["Thursday", "10:30"], "prose"),
    ("decline-offer", "write a polite email declining a job offer from Northwind Labs",
     "Leave the door open for future roles.", ["Northwind Labs", "future roles"], "prose"),
    ("interview-followup", "write a follow-up email after a product manager interview on Tuesday",
     "Keep it under 120 words.", ["product manager", "Tuesday", "120 words"], "prose len"),
    ("intro-priya-tom", "write a two-sentence introduction connecting my colleague Priya, a data engineer, with Tom, "
     "who runs analytics at Fabrikam", "", ["two-sentence", "Priya", "Tom", "Fabrikam"], "prose len"),
    ("price-increase", "write a customer email announcing that our basic plan goes from $9 to $12 a month on March 1",
     "", ["$9", "$12", "March 1"], "prose"),
    ("order-delay", "write an apology to a customer whose order is delayed by two weeks [because] our supplier ran out "
     "of stock", "", ["two weeks", "supplier ran out of stock"], "prose"),
    ("cover-nurse", "write a cover letter for a pediatric nurse position at St. Mary's Hospital",
     "Mention my 4 years in the NICU.", ["pediatric nurse", "St. Mary's Hospital", "4 years", "NICU"], "prose"),
    ("resume-bullet", "rewrite this resume bullet to sound more results-focused",
     "\n\"Responsible for managing social media accounts.\"", ["Responsible for managing social media accounts."], ""),
    ("linkedin-promo", "write a LinkedIn post announcing my promotion to senior designer at Contoso",
     "Keep it humble and under 80 words.", ["LinkedIn", "senior designer", "Contoso", "80 words"], "prose len"),
    ("toast-sister", "write a two-minute wedding toast for my sister Ana and her husband Leo",
     "Include a light joke about their first camping trip.", ["two-minute", "Ana", "Leo", "camping trip"], "prose len"),
    ("card-teacher", "write a thank-you card message for my son's second-grade teacher, Ms. Park", "",
     ["thank-you card", "second-grade", "Ms. Park"], "prose"),
    ("bio-ortiz", "write a 50-word speaker bio for Dr. Lena Ortiz, a climate economist at the University of Leeds", "",
     ["50-word", "Lena Ortiz", "climate economist", "University of Leeds"], "prose len"),
    ("complaint-luggage", "write a complaint to an airline about a lost suitcase on flight BA 117",
     "Ask for compensation for the clothes I had to buy.", ["lost suitcase", "BA 117", "compensation"], "prose"),
    ("reference-intern", "write a reference letter for my former intern, Sam Lee, who built our inventory dashboard",
     "", ["Sam Lee", "inventory dashboard"], "prose"),
    ("rsvp-dinner", "write a short reply accepting a dinner invitation for Saturday at 7", "Say I'll bring dessert.",
     ["Saturday at 7", "dessert"], "prose len"),
    ("slack-outage", "write a Slack update telling the support team that checkout is down and engineering is on it",
     "", ["Slack", "checkout is down"], "prose"),
    ("press-sunpack", "write a press release headline and first paragraph for the launch of our solar backpack, the "
     "SunPack 2", "", ["headline", "SunPack 2"], "prose"),
    ("proofread-weather", "proofread this sentence",
     "\n\"Their going to announce the winners tomorow, weather or not it rains.\"",
     ["Their going to announce the winners tomorow, weather or not it rains."], ""),
    ("formal-push", "rewrite this message so it sounds more formal",
     "\n\"hey, can't make the call, can we push to next week?\"",
     ["hey, can't make the call, can we push to next week?"], ""),
    ("shorten-founded", "shorten this paragraph to two sentences",
     "\n\"Our company was founded in 2009 by three friends who wanted to make outdoor gear that lasts. Since then we "
     "have grown to 200 employees across four countries, but our mission has stayed the same: build products that "
     "you can hand down to your kids.\"", ["two sentences", "founded in 2009"], "len"),
    ("subject-spring-sale", "suggest five subject lines for an email inviting customers to our spring sale", "",
     ["five subject lines", "spring sale"], ""),
    ("out-of-office", "write an out-of-office reply for December 22 to January 3",
     "Point urgent requests to helpdesk@example.com.", ["December 22", "January 3", "helpdesk@example.com"], "prose"),
    ("newsletter-garden", "write the opening paragraph of our monthly newsletter for a community garden",
     "Mention the tomato swap on June 14.", ["community garden", "tomato swap", "June 14"], "prose"),
    ("condolence-coworker", "write a short condolence message to a coworker whose father passed away", "",
     ["condolence", "father"], "prose len"),
    ("tweet-dark-mode", "write a tweet announcing that our app now supports dark mode", "", ["tweet", "dark mode"],
     "prose"),
    ("agenda-kickoff", "write an agenda for a 30-minute project kickoff with the design and engineering leads", "",
     ["30-minute", "kickoff", "design and engineering leads"], "len"),
    ("feedback-reviews", "write constructive feedback for a teammate who often misses code review deadlines",
     "Keep it kind but direct.", ["code review deadlines", "kind but direct"], "prose"),
    #Creative
    ("haiku-tin-roof", "write a haiku about rain on a tin roof", "", ["haiku", "tin roof"], "prose"),
    ("limerick-cat", "write a limerick about a cat who learns to code", "", ["limerick", "cat"], "prose"),
    ("story-lighthouse", "write a 300-word story about a lighthouse keeper who finds a message in a bottle", "",
     ["300-word", "lighthouse keeper", "message in a bottle"], "prose len"),
    ("poem-lisbon-kitchen", "write a free-verse poem about my grandmother's kitchen in Lisbon", "",
     ["free-verse", "grandmother's kitchen", "Lisbon"], "prose"),
    ("slogans-crumb", "suggest three slogans for a gluten-free bakery called Crumb", "",
     ["three slogans", "gluten-free", "Crumb"], ""),
    ("names-garden-podcast", "brainstorm ten names for a podcast about urban gardening", "",
     ["ten names", "podcast", "urban gardening"], ""),
    ("chorus-small-town", "write a chorus for a country song about leaving a small town", "",
     ["chorus", "country song", "small town"], "prose"),
    ("dialogue-detective", "write a short dialogue between a tired detective and a nervous witness", "",
     ["detective", "witness"], "prose len"),
    ("bedtime-dinosaur", "write a bedtime story for a 5-year-old about a sleepy dinosaur", "Keep it under 200 words.",
     ["5-year-old", "sleepy dinosaur", "200 words"], "prose len"),
    ("sonnet-coffee", "write a sonnet about the first cup of coffee in the morning", "", ["sonnet", "coffee"], "prose"),
    ("riddle-shadow", "write a riddle whose answer is \"shadow\"", "", ["riddle", "\"shadow\""], ""),
    ("npc-innkeeper", "create a Dungeons & Dragons innkeeper NPC with a secret",
     "Give a name, a personality, and the secret.", ["Dungeons & Dragons", "innkeeper", "secret"], ""),
    ("twist-heist", "suggest a plot twist for a heist movie where the crew robs a museum", "",
     ["plot twist", "heist", "museum"], ""),
    ("tagline-climbing", "write a tagline for a 24-hour climbing gym", "", ["tagline", "24-hour climbing gym"], ""),
    ("acrostic-ocean", "write an acrostic poem using the word OCEAN", "", ["acrostic", "OCEAN"], "prose"),
    ("flash-door", "write a 100-word flash fiction piece that ends with the line \"and the door was already open.\"",
     "", ["100-word", "\"and the door was already open.\""], "prose len"),
    ("backstory-astronaut", "write a one-paragraph backstory for a retired astronaut who now runs a bakery", "",
     ["one-paragraph", "retired astronaut", "bakery"], "prose len"),
    ("rap-cooking", "write an eight-line rap verse about learning to cook", "", ["eight-line", "rap verse"],
     "prose len"),
    ("fable-fox-crow", "write a fable about a fox and a crow with a moral about patience", "",
     ["fable", "fox", "crow", "patience"], "prose"),
    ("names-bamboo-cup", "suggest six names for a reusable coffee cup made from bamboo", "", ["six names", "bamboo"],
     ""),
    ("speech-dana", "write a retirement speech for my coworker Dana, who has been our accountant for 31 years", "",
     ["Dana", "accountant", "31 years"], "prose"),
    ("card-brother-40", "write a funny birthday card message for my brother turning 40", "", ["birthday card", "40"],
     "prose"),
    ("scene-umbrella", "write a one-page screenplay scene where two strangers share an umbrella", "",
     ["one-page", "screenplay", "umbrella"], "prose len"),
    ("city-wind", "describe a floating city powered by wind, in three paragraphs", "",
     ["floating city", "wind", "three paragraphs"], "prose len"),
    ("caption-dog", "write an Instagram caption for a photo of my dog wearing sunglasses", "",
     ["Instagram caption", "sunglasses"], "prose"),
    #Code
    ("py-fibonacci", "write a Python function that returns the n-th Fibonacci number iteratively", "",
     ["Python", "Fibonacci", "iteratively"], ""),
    ("js-debounce", "write a JavaScript debounce function", "It should take a callback and a delay in milliseconds.",
     ["JavaScript", "debounce", "milliseconds"], ""),
    ("sql-top-five", "write a SQL query that returns the five customers with the most orders in 2024", "",
     ["SQL", "five customers", "2024"], ""),
    ("regex-phone", "write a regex that matches US phone numbers like (555) 123-4567", "",
     ["regex", "(555) 123-4567"], ""),
    ("bash-jpeg", "write a bash script [to] rename every .jpeg file in the current folder to .jpg", "",
     ["bash", ".jpeg", ".jpg"], ""),
    ("py-csv-dedupe", "write a Python script that removes duplicate rows from a CSV file by the email column", "",
     ["Python", "CSV", "email column"], ""),
    ("js-closures", "explain JavaScript closures with one short example", "", ["JavaScript closures"], "len"),
    ("ts-convert", "convert this JavaScript function to TypeScript with proper types",
     "\n```js\nfunction total(items) {\n  return items.reduce((sum, item) => sum + item.price * item.qty, 0);\n}\n```",
     ["TypeScript", "items.reduce((sum, item) => sum + item.price * item.qty, 0)"], ""),
    ("py-off-by-one", "fix the off-by-one error in this loop",
     "\n```python\nfor i in range(1, len(items)):\n    print(items[i])\n```",
     ["for i in range(1, len(items)):", "print(items[i])"], ""),
    ("js-undefined-map", "explain what this error means and how to fix it",
     "\n```\nTypeError: Cannot read properties of undefined (reading 'map')\n```",
     ["TypeError: Cannot read properties of undefined (reading 'map')"], ""),
    ("go-health", "write a minimal HTTP server in Go that responds \"ok\" on /health", "",
     ["Go", "\"ok\"", "/health"], ""),
    ("rust-reverse-words", "write a Rust function that reverses the words in a sentence", "",
     ["Rust", "reverses the words"], ""),
    ("pytest-leap", "write pytest tests for this function",
     "\n```python\ndef is_leap(year):\n    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)\n```",
     ["pytest", "def is_leap(year):", "year % 400 == 0"], ""),
    ("git-undo-commit", "show me how to undo my last git commit but keep the changes", "",
     ["git commit", "keep the changes"], ""),
    ("dockerfile-node", "write a Dockerfile for a Node 20 app that runs npm start on port 3000", "",
     ["Dockerfile", "Node 20", "npm start", "3000"], ""),
    ("css-center", "show the CSS to center a div horizontally and vertically with flexbox", "", ["CSS", "flexbox"], ""),
    ("py-nested-ifs", "refactor this function to remove the nested if statements",
     "\n```python\ndef grade(score):\n    if score >= 90:\n        return 'A'\n    else:\n        if score >= 80:\n"
     "            return 'B'\n        else:\n            return 'C'\n```",
     ["def grade(score):", "score >= 90", "score >= 80"], ""),
    ("binary-search-log", "explain the time complexity of binary search and why it's O(log n)", "",
     ["binary search", "O(log n)"], ""),
    ("py-retry-decorator", "write a Python decorator that retries a function up to 3 times with exponential backoff",
     "", ["Python decorator", "3 times", "exponential backoff"], ""),
    ("sql-joins", "explain the difference between a LEFT JOIN and an INNER JOIN with a small example", "",
     ["LEFT JOIN", "INNER JOIN"], ""),
    ("react-clicks", "write a React component with a button that counts clicks", "Use hooks.",
     ["React", "counts clicks", "hooks"], ""),
    ("cron-monday", "write a cron expression that runs at 2:30 AM every Monday", "",
     ["cron expression", "2:30 AM", "Monday"], ""),
    ("py-deep-merge", "write a Python function that deep-merges two dictionaries",
     "Values from the second one should win on conflicts.", ["Python", "deep-merges", "second one should win"], ""),
    ("java-singleton", "write a thread-safe singleton class in Java", "", ["thread-safe", "singleton", "Java"], ""),
    ("rest-pagination", "design a REST endpoint for listing orders with cursor-based pagination", "",
     ["REST endpoint", "cursor-based pagination"], ""),
    ("diff-timeout", "explain what this diff changes",
     "\n```diff\n- timeout = 30\n+ timeout = int(os.environ.get(\"TIMEOUT\", 30))\n```",
     ["timeout = int(os.environ.get(\"TIMEOUT\", 30))"], ""),
    ("py-list-comp", "rewrite this loop as a list comprehension",
     "\n```python\nsquares = []\nfor n in nums:\n    if n % 2 == 0:\n        squares.append(n * n)\n```",
     ["squares.append(n * n)", "n % 2 == 0"], ""),
    ("k8s-readiness", "add a readiness probe to a Kubernetes container that checks /ready on port 8080", "",
     ["readiness probe", "/ready", "8080"], ""),
    ("excel-sumif", "write an Excel formula that sums column B only where column A says \"Paid\"", "",
     ["Excel formula", "column B", "\"Paid\""], ""),
    ("py-asyncio", "convert this function to use asyncio and aiohttp",
     "\n```python\nimport requests\n\ndef fetch(url):\n    return requests.get(url).text\n```",
     ["asyncio", "aiohttp", "def fetch(url):"], ""),
    ("sql-review-year", "review this query for performance problems",
     "\n```sql\nSELECT * FROM orders WHERE YEAR(created_at) = 2024 ORDER BY total DESC;\n```",
     ["SELECT * FROM orders WHERE YEAR(created_at) = 2024 ORDER BY total DESC;"], ""),
    ("git-merge-rebase", "explain the difference between git merge and git rebase", "", ["git merge", "git rebase"],
     ""),
    ("py-argparse", "write a Python CLI with argparse that takes an input file and an optional --verbose flag", "",
     ["argparse", "--verbose"], ""),
    ("swift-date", "write a Swift function that formats a Date as \"Mar 4, 2025\"", "", ["Swift", "\"Mar 4, 2025\""],
     ""),
    ("sql-indexes", "suggest indexes for a users table that is queried by email and by created_at range", "",
     ["users table", "email", "created_at"], ""),
    ("js-async-await", "explain how async and await work in JavaScript for a beginner", "",
     ["async", "await", "beginner"], ""),
    ("shell-largest-files", "write a one-line shell command that lists the 10 largest files under /var/log", "",
     ["10 largest files", "/var/log"], ""),
    ("py-dataclass", "turn this dictionary into a Python dataclass",
     "\n```python\nuser = {\"id\": 7, \"name\": \"Ada\", \"active\": True}\n```", ["dataclass", "\"name\": \"Ada\""], ""),
    ("regex-password", "explain what this regex matches", "\n```\n^(?=.*\\d)(?=.*[A-Z]).{8,}$\n```",
     ["^(?=.*\\d)(?=.*[A-Z]).{8,}$"], ""),
    ("html-signup", "write an HTML signup form with email and password fields and a submit button", "",
     ["HTML", "email and password fields"], ""),
    ("pandas-groupby", "write pandas code that groups sales by region and month and sums revenue", "",
     ["pandas", "region and month", "revenue"], ""),
    ("kafka-groups", "explain what a Kafka consumer group is", "", ["Kafka consumer group"], ""),
    ("c-null-pointer", "explain why this C code crashes", "\n```c\nint *p = NULL;\n*p = 5;\n```",
     ["int *p = NULL;", "*p = 5;"], ""),
    ("gh-actions-pytest", "write a GitHub Actions workflow that runs pytest on every push to main", "",
     ["GitHub Actions", "pytest", "main"], ""),
    ("py-type-hints", "add type hints to this function",
     "\n```python\ndef scale(values, factor):\n    return [v * factor for v in values]\n```",
     ["def scale(values, factor):", "[v * factor for v in values]"], ""),
    #Data and analysis
    ("stats-house-prices", "list the summary statistics I should report for a dataset of 2,000 house prices", "",
     ["summary statistics", "2,000 house prices"], ""),
    ("chart-revenue", "recommend a chart type for showing monthly revenue across five product lines", "",
     ["chart type", "monthly revenue", "five product lines"], ""),
    ("ab-significance", "explain how to tell if an A/B test with 1,200 visitors per variant is statistically "
     "significant", "", ["A/B test", "1,200 visitors"], ""),
    ("saas-kpis", "list the five most important KPIs for an early-stage SaaS company", "", ["five", "KPIs", "SaaS"],
     ""),
    ("pivot-sheets", "explain how to build a pivot table in Google Sheets that shows sales by rep", "",
     ["pivot table", "Google Sheets", "sales by rep"], ""),
    ("survey-remote", "write eight survey questions to measure employee satisfaction with remote work", "",
     ["eight survey questions", "remote work"], ""),
    ("forecast-sales", "explain how to forecast next quarter's sales from three years of monthly data", "",
     ["next quarter", "three years of monthly data"], ""),
    ("correlation-ice-cream", "explain why correlation doesn't imply causation, using an ice cream example", "",
     ["correlation", "causation", "ice cream"], ""),
    ("support-metrics", "suggest metrics for a customer support dashboard",
     "Group them by speed, quality, and volume.", ["customer support dashboard", "speed, quality, and volume"], "fmt"),
    ("outliers-delivery", "explain two ways to detect outliers in a column of delivery times", "",
     ["outliers", "delivery times"], ""),
    ("cohort-chart", "explain what a cohort retention chart shows and how to read it", "", ["cohort retention chart"],
     ""),
    ("sample-size", "calculate the sample size needed for a survey with a 95% confidence level and a 5% margin of "
     "error", "", ["95% confidence level", "5% margin of error"], ""),
    ("clean-phones", "list the steps to clean a customer spreadsheet with duplicate rows and inconsistent phone "
     "formats", "", ["duplicate rows", "inconsistent phone formats"], ""),
    ("median-salary", "explain when to use the median instead of the mean, with a salary example", "",
     ["median", "mean", "salary"], ""),
    ("vlookup-price", "explain how VLOOKUP works with an example that finds a price by product ID", "",
     ["VLOOKUP", "product ID"], ""),
    #Learning and explaining
    ("photosynthesis-10", "explain photosynthesis to a 10-year-old", "", ["photosynthesis", "10-year-old"], ""),
    ("tides", "what causes ocean tides", "", ["ocean tides"], "q"),
    ("inflation-why", "why does inflation happen", "", ["inflation"], "q"),
    ("blockchain-plain", "explain how a blockchain works in plain English", "", ["blockchain", "plain English"], ""),
    ("sky-blue", "why is the sky blue", "", ["sky blue"], "q"),
    ("compound-interest", "explain compound interest with an example of $1,000 at 5% for 10 years", "",
     ["compound interest", "$1,000", "5%", "10 years"], ""),
    ("mrna", "how do mRNA vaccines train the immune system", "", ["mRNA vaccines", "immune system"], "q"),
    ("ww2-causes", "summarize the main causes of World War II in five bullet points", "",
     ["World War II", "five bullet points"], "fmt len"),
    ("supply-demand", "explain supply and demand using concert tickets as the example", "",
     ["supply and demand", "concert tickets"], ""),
    ("event-horizon", "what happens at the event horizon of a black hole", "", ["event horizon", "black hole"], "q"),
    ("stocks-bonds", "compare stocks and bonds for a first-time investor", "", ["stocks and bonds",
     "first-time investor"], ""),
    ("url-enter", "explain what happens when I type a URL into my browser and press Enter", "",
     ["URL", "browser", "press Enter"], ""),
    ("french-rev-effects", "what were the long-term effects of the French Revolution on Europe", "",
     ["French Revolution", "Europe"], "q"),
    ("fractions", "explain how to add fractions with different denominators, with two worked examples", "",
     ["fractions", "different denominators", "two worked examples"], ""),
    ("jet-lag", "how can I reduce jet lag when flying from New York to Tokyo", "", ["jet lag", "New York", "Tokyo"],
     "q"),
    ("greenhouse-100", "explain the greenhouse effect in under 100 words", "", ["greenhouse effect", "100 words"],
     "len"),
    ("dough-rise", "why does bread dough rise", "", ["bread dough"], "q"),
    ("mitosis", "explain the stages of mitosis in order", "", ["stages of mitosis", "in order"], ""),
    ("opportunity-cost", "define opportunity cost and give an everyday example", "",
     ["opportunity cost", "everyday example"], ""),
    ("seismology", "how do seismologists measure earthquakes", "", ["seismologists", "earthquakes"], "q"),
    ("space-race", "make a timeline of the space race from Sputnik to Apollo 11", "",
     ["timeline", "Sputnik", "Apollo 11"], "fmt"),
    ("overfitting", "explain overfitting in machine learning with an analogy", "", ["overfitting", "analogy"], ""),
    ("spanish-3-months", "what is the fastest way to learn basic conversational Spanish in three months", "",
     ["conversational Spanish", "three months"], "q"),
    ("electoral-college", "explain how the US Electoral College works", "", ["Electoral College"], ""),
    ("caffeine", "how long does caffeine stay in the body", "", ["caffeine"], "q"),
    ("aws-plan", "make a 4-week study plan for the AWS Cloud Practitioner exam", "",
     ["4-week", "AWS Cloud Practitioner"], ""),
    ("tcp-handshake", "explain the TCP three-way handshake", "", ["TCP three-way handshake"], ""),
    ("himalayas", "how did the Himalayas form", "", ["Himalayas"], "q"),
    ("placebo", "explain the placebo effect and why trials use control groups", "",
     ["placebo effect", "control groups"], ""),
    ("ram-storage", "explain the difference between RAM and storage for someone buying a laptop", "",
     ["RAM", "storage", "laptop"], ""),
    ("rainbows", "why do rainbows form after rain", "", ["rainbows"], "q"),
    ("gdp", "explain what GDP measures and what it leaves out", "", ["GDP", "leaves out"], ""),
    ("organelle-cards", "make 10 flashcards on cell organelles, question on one side and answer on the other", "",
     ["10 flashcards", "cell organelles"], "fmt"),
    ("china-time-zone", "why does China use a single time zone", "", ["China", "single time zone"], "q"),
    ("recursion-dolls", "explain recursion using a set of Russian nesting dolls", "",
     ["recursion", "Russian nesting dolls"], ""),
    #Research and summaries
    ("summarize-remote-url", "summarize the article at https://example.com/blog/remote-work-2025",
     "Include its three main claims.", ["https://example.com/blog/remote-work-2025", "three main claims"], ""),
    ("teen-sleep-studies", "find peer-reviewed studies from the last five years on screen time and teen sleep",
     "Cite each one.", ["peer-reviewed", "last five years", "teen sleep", "Cite"], ""),
    ("ev-reports", "compare what https://example.com/report-a and https://example.com/report-b say about electric "
     "vehicle adoption", "", ["https://example.com/report-a", "https://example.com/report-b",
                              "electric vehicle adoption"], ""),
    ("brain-myth", "fact-check the claim that humans only use 10% of their brains", "",
     ["check the claim", "10% of their brains"], ""),
    ("sapiens-200", "summarize the book Sapiens in 200 words", "", ["Sapiens", "200 words"], "len"),
    ("nuclear-args", "list the main arguments for and against nuclear power, with a source for each", "",
     ["nuclear power", "source for each"], ""),
    ("pet-insurance", "estimate the market size for pet insurance in Canada and show your assumptions", "",
     ["pet insurance", "Canada", "assumptions"], ""),
    ("printing-press", "summarize how the printing press changed European religion and science", "",
     ["printing press", "religion and science"], ""),
    ("four-day-week", "summarize the evidence on four-day work weeks and productivity",
     "Note where studies disagree.", ["four-day work weeks", "productivity", "studies disagree"], ""),
    ("notes-apps", "compare Notion, Obsidian, and Evernote for a student taking lecture notes", "",
     ["Notion", "Obsidian", "Evernote", "lecture notes"], ""),
    ("apa-gomez", "format this source as an APA citation",
     "\nAuthor: Maria Gomez. Title: Cities and Heat. Publisher: Island Press. Year: 2021.",
     ["APA citation", "Maria Gomez", "Island Press", "2021"], ""),
    ("brief-food-waste", "write a one-page policy brief on reducing food waste in school cafeterias", "",
     ["one-page", "food waste", "school cafeterias"], "len"),
    ("transcript-stroller", "summarize this interview transcript in three bullet points",
     "\nQ: Why did you start the company?\nA: I couldn't find a stroller that folded with one hand, so I built one.\n"
     "Q: What's next?\nA: A version for twins, launching in May.",
     ["three bullet points", "stroller", "twins", "May"], "fmt len"),
    ("internet-history", "outline the history of the internet from ARPANET to the web", "", ["ARPANET"], ""),
    ("cohort-vs-rct", "explain the difference between a cohort study and a randomized controlled trial", "",
     ["cohort study", "randomized controlled trial"], ""),
    #Business
    ("pitch-meal-prep", "write a 30-second elevator pitch for a meal-prep delivery startup", "",
     ["30-second", "meal-prep delivery"], "prose len"),
    ("swot-bookstore", "do a SWOT analysis for a small independent bookstore", "", ["SWOT", "independent bookstore"],
     "fmt"),
    ("job-barista", "write a job post for a part-time barista at a café in Austin",
     "List the hours as weekends 7am-1pm.", ["part-time barista", "Austin", "weekends 7am-1pm"], "prose"),
    ("earbuds-desc", "write a product description for noise-canceling earbuds with 30-hour battery life", "",
     ["noise-canceling earbuds", "30-hour battery life"], "prose"),
    ("faq-dog-walking", "write five FAQ entries for a dog-walking service", "", ["five FAQ entries", "dog-walking"], ""),
    ("okrs-churn", "draft three OKRs for a customer success team trying to reduce churn", "",
     ["three OKRs", "customer success", "churn"], ""),
    ("yoga-pricing", "suggest a pricing structure for a yoga studio with drop-in, monthly, and annual options", "",
     ["yoga studio", "drop-in, monthly, and annual"], ""),
    ("raise-points", "give me talking points for negotiating a 10% raise", "", ["talking points", "10% raise"], ""),
    ("one-on-one-template", "make a template for weekly one-on-one meeting notes", "", ["template", "one-on-one"], ""),
    ("mission-seniors", "write a mission statement for a nonprofit that teaches seniors to use smartphones", "",
     ["mission statement", "seniors", "smartphones"], "prose"),
    ("ads-plumbing", "write three Google ad headlines for a plumbing company in Denver",
     "Each must be under 30 characters.", ["three Google ad headlines", "Denver", "30 characters"], "len"),
    ("onboarding-sales", "make a first-week onboarding checklist for a new sales hire", "",
     ["first-week", "onboarding checklist", "sales hire"], "fmt"),
    ("welcome-sequence", "outline a three-email welcome sequence for new newsletter subscribers", "",
     ["three-email", "welcome sequence"], ""),
    ("value-prop-rent", "write a one-sentence value proposition for an app that splits rent between roommates", "",
     ["one-sentence", "splits rent", "roommates"], "prose len"),
    ("nps", "explain how to calculate a Net Promoter Score from survey answers", "", ["Net Promoter Score"], ""),
    ("budget-5000", "make a monthly marketing budget split for $5,000 across search, social, and email", "",
     ["$5,000", "search, social, and email"], ""),
    ("cold-email-laundry", "write a cold email to a hotel manager pitching our laundry service",
     "Keep it under 100 words.", ["cold email", "hotel manager", "laundry service", "100 words"], "prose len"),
    ("persona-travel", "create a customer persona for a budget travel app aimed at college students", "",
     ["customer persona", "budget travel app", "college students"], ""),
    ("roadmap-sso", "turn these features into a three-month product roadmap: SSO, audit logs, a mobile app", "",
     ["three-month", "SSO, audit logs, a mobile app"], ""),
    ("names-landscaping", "suggest names for a landscaping LLC that specializes in native plants", "",
     ["landscaping LLC", "native plants"], ""),
    #Everyday life
    ("chickpea-dinner", "give me a vegetarian dinner recipe using chickpeas and spinach that takes under 30 minutes",
     "", ["vegetarian", "chickpeas and spinach", "30 minutes"], ""),
    ("meal-plan-dairy", "make a 5-day meal plan for someone eating 2,000 calories a day with no dairy", "",
     ["5-day", "2,000 calories", "no dairy"], ""),
    ("lisbon-budget", "plan a 3-day itinerary for Lisbon on a budget", "", ["3-day", "Lisbon", "on a budget"], ""),
    ("dumbbell-plan", "make a beginner 3-day-a-week strength workout I can do at home with dumbbells", "",
     ["beginner", "3-day-a-week", "dumbbells"], ""),
    ("budget-salary", "make a monthly budget for a $3,200 take-home salary with $1,100 rent", "",
     ["$3,200", "$1,100 rent"], ""),
    ("tomato-zone-6", "explain when and how to transplant tomato seedlings outdoors in zone 6", "",
     ["tomato seedlings", "zone 6"], ""),
    ("cat-toxic-foods", "list foods that are toxic to cats", "", ["toxic to cats"], ""),
    ("oven-cleaning", "explain how to clean an oven with baking soda and vinegar", "", ["baking soda and vinegar"], ""),
    ("tire-check", "explain how to check if my car tires need replacing", "", ["car tires"], ""),
    ("screenless-routine", "suggest an evening routine to fall asleep faster without using screens", "",
     ["evening routine", "without using screens"], ""),
    ("gift-fishing-jazz", "suggest gift ideas under $50 for a dad who likes fishing and jazz", "",
     ["under $50", "fishing and jazz"], ""),
    ("packing-highlands", "make a packing list for a 4-day hiking trip in the Scottish Highlands in October", "",
     ["packing list", "4-day", "Scottish Highlands", "October"], "fmt"),
    ("fiddle-leaf", "explain how often to water a fiddle-leaf fig in a bright apartment", "", ["fiddle-leaf fig"], ""),
    ("moving-checklist", "make a checklist for moving to a new apartment in two weeks", "",
     ["checklist", "two weeks"], "fmt"),
    ("party-7yo", "plan activities for a 7-year-old's birthday party with 12 kids in a small backyard", "",
     ["7-year-old", "12 kids", "small backyard"], ""),
    ("freeze-rice", "can cooked rice be frozen, and for how long", "", ["cooked rice", "how long"], "q"),
    ("jammy-egg", "how long should I boil an egg for a jammy yolk", "", ["jammy yolk"], "q"),
    ("buttermilk-sub", "tell me what I can substitute for buttermilk in pancakes", "", ["buttermilk", "pancakes"], ""),
    ("rail-pass", "explain whether a Japan Rail Pass is worth it for a 10-day trip covering Tokyo, Kyoto, and "
     "Hiroshima", "", ["Japan Rail Pass", "10-day", "Tokyo, Kyoto, and Hiroshima"], ""),
    ("couch-5k", "make an 8-week plan to go from walking to running a 5K", "", ["8-week", "5K"], ""),
    ("emergency-fund", "explain how big an emergency fund should be for a single renter with no kids", "",
     ["emergency fund", "single renter"], ""),
    ("paint-bedroom", "estimate how much paint I need for a 12-by-14-foot bedroom with 8-foot ceilings", "",
     ["12-by-14-foot", "8-foot ceilings"], ""),
    ("pothos-yellow", "why are the leaves on my pothos turning yellow", "", ["pothos", "turning yellow"], "q"),
    ("sourdough-fridge", "explain how to feed a sourdough starter that's been in the fridge for a month", "",
     ["sourdough starter", "a month"], ""),
    ("brazil-visit", "explain what documents a US citizen needs to visit Brazil for two weeks", "",
     ["US citizen", "Brazil", "two weeks"], ""),
    ("screen-rules", "suggest screen-time rules for a 9-year-old on school nights", "",
     ["9-year-old", "school nights"], ""),
    ("scale-recipe", "scale this recipe from 4 servings to 10", "\n2 cups flour, 1 cup sugar, 3 eggs, 1/2 cup butter",
     ["4 servings", "2 cups flour, 1 cup sugar, 3 eggs, 1/2 cup butter"], ""),
    ("lease-buy", "compare leasing and buying a car for someone who drives 15,000 miles a year", "",
     ["leasing and buying", "15,000 miles"], ""),
    ("desk-stretches", "suggest stretches for lower back pain from sitting at a desk all day", "",
     ["lower back pain", "desk"], ""),
    ("wedding-budget", "make a wedding budget breakdown for 80 guests and $20,000", "", ["80 guests", "$20,000"], ""),
    ("mortgage-15-30", "how does a 15-year mortgage compare with a 30-year one on total interest", "",
     ["15-year mortgage", "30-year", "total interest"], "q"),
    ("chore-chart", "make a weekly chore chart for two kids aged 8 and 11", "", ["chore chart", "8 and 11"], "fmt"),
    ("estimated-taxes", "explain how quarterly estimated taxes work for a freelancer in the US", "",
     ["quarterly estimated taxes", "freelancer"], ""),
    ("puppy-biting", "explain how to stop a puppy from biting during play [before] the habit sets in", "",
     ["puppy", "biting"], ""),
    ("solar-seattle", "are solar panels worth it in Seattle", "", ["solar panels", "Seattle"], "q"),
    #Security and compliance
    ("bcrypt", "write a Python function that hashes passwords with bcrypt",
     "Never store or log the plain-text password.", ["bcrypt", "Never store or log the plain-text password."], ""),
    ("cookie-gdpr", "write a cookie consent notice that complies with GDPR", "Do not pre-check any optional cookies.",
     ["GDPR", "Do not pre-check any optional cookies."], "prose"),
    ("node-api-keys", "explain how to store API keys in a Node app without committing them to git", "",
     ["API keys", "committing them to git"], ""),
    ("xss-innerhtml", "review this snippet for XSS", "\n```js\nel.innerHTML = params.get('name');\n```",
     ["XSS", "el.innerHTML = params.get('name');"], ""),
    ("sql-parameters", "rewrite this query to use parameters instead of string concatenation",
     "\n```python\ncur.execute(\"SELECT * FROM users WHERE email = '\" + email + \"'\")\n```",
     ["cur.execute(\"SELECT * FROM users WHERE email = '\" + email + \"'\")"], ""),
    ("breach-template", "write an incident report template for a data breach",
     "It must include a timeline, affected systems, and the notification deadline.",
     ["incident report template", "data breach", "timeline, affected systems, and the notification deadline"], ""),
    ("patient-portal", "write an email to patients about a new portal login",
     "Never include any health information in the email.",
     ["patients", "portal login", "Never include any health information"], "prose"),
    ("clinic-rbac", "design role-based access control for a clinic app with admin, doctor, and receptionist roles", "",
     ["role-based access control", "admin, doctor, and receptionist"], ""),
    ("phishing-note", "write a short training note that teaches staff how to spot phishing emails", "",
     ["phishing emails"], "prose len"),
    ("jwt-server", "explain how to validate a JWT on the server", "Always check the signature, expiry, and issuer.",
     ["JWT", "Always check the signature, expiry, and issuer."], ""),
    ("pci-checkout", "list what our checkout must do to stay PCI compliant if we never store card numbers", "",
     ["PCI compliant", "never store card numbers"], ""),
    ("csp-header", "write a Content Security Policy header that only allows scripts from our own domain", "",
     ["Content Security Policy", "our own domain"], ""),
    ("totp-django", "explain how to add TOTP two-factor authentication to a Django app", "", ["TOTP", "Django"], ""),
    ("mask-cards", "write a log filter that masks credit card numbers before they are written",
     "Keep only the last 4 digits.", ["credit card numbers", "last 4 digits"], ""),
    ("backup-policy", "draft a backup policy for a 20-person company",
     "Backups must be encrypted and tested every quarter.",
     ["20-person", "Backups must be encrypted and tested every quarter."], ""),
    #Wordy-friendly: markers only where the long form still reads correctly
    ("s3-photo-backup", "write a Python script [to] back up my photos to S3 [every] night and email me [if] the "
     "upload fails", "", ["Python", "S3", "upload fails"], ""),
    ("office-closed", "write a note telling staff the office is closed today [because] the heating failed", "",
     ["office is closed", "heating failed"], "prose"),
    ("interview-checklist", "make a checklist [to] get ready for a job interview, starting a week [before] the "
     "interview", "", ["checklist", "job interview"], "fmt"),
    ("test-backups", "explain why I should test backups regularly [although] they rarely fail", "",
     ["test backups"], ""),
    ("rent-late", "write a message to my landlord saying rent will be three days late [because] my paycheck was "
     "delayed", "", ["landlord", "three days late", "paycheck"], "prose"),
    ("frost-planting", "explain what to plant [before] the first frost and what to cover [if] it arrives early", "",
     ["first frost", "arrives early"], ""),
    ("cache-api", "write a function that caches API responses [to] avoid repeat calls, and clears the cache [if] it "
     "grows past 100 entries", "", ["caches API responses", "100 entries"], ""),
    ("renewal-reminder", "write a reminder telling customers that their plan renews [soon] and that they can cancel "
     "[before] the renewal date", "", ["renews", "cancel", "renewal date"], "prose"),
    ("exam-schedule", "make a study schedule [to] review [every] chapter [before] the final exam on May 12", "",
     ["study schedule", "final exam", "May 12"], ""),
    ("emergency-fund-first", "explain [first] why an emergency fund matters, then how to build one on a tight budget",
     "", ["emergency fund", "tight budget"], ""),
    ("oslo-packing", "make a packing list [for] staying warm on a winter trip to Oslo", "", ["packing list", "Oslo"],
     "fmt"),
    ("launch-june", "write an announcement that the launch moves to June [because] testing found a billing bug", "",
     ["June", "billing bug"], "prose"),
    ("bathroom-mold", "explain how to remove mold from a bathroom ceiling [before] painting it, and what to do [if] "
     "the mold keeps coming back", "", ["mold", "bathroom ceiling"], ""),
    ("knee-exercises", "suggest exercises [to] strengthen my knees [because] I want to start running", "",
     ["strengthen my knees", "start running"], ""),
    ("supplier-friday", "write an email asking our supplier to confirm delivery [before] Friday [because] we open on "
     "Saturday", "", ["supplier", "Friday", "Saturday"], "prose"),
    ("unit-tests-why", "why should I write unit tests [if] my code already works", "", ["unit tests"], "q"),
    ("form-validation", "add input validation to a signup form handler [to] reject empty emails [before] they reach "
     "the database", "", ["input validation", "empty emails", "database"], ""),
    ("vietnam-budget", "make a budget [for] a two-week trip to Vietnam, and flag costs I should book [now]", "",
     ["two-week trip", "Vietnam"], ""),
    ("backup-321", "explain the 3-2-1 backup rule [to] help me protect family photos", "",
     ["3-2-1 backup rule", "family photos"], ""),
    ("deploy-freeze", "write a message telling engineers that deploys are frozen [now] [because] of the holiday "
     "traffic, and that the freeze ends [soon]", "", ["deploys are frozen", "holiday traffic"], "prose"),
]
CORES = [Core(slug, head, tail, tuple(keep), frozenset(flags.split())) for slug, head, tail, keep, flags in CORE_ROWS]

#Waste pools. A wrapper is (text, whether it makes the request a question)
GREETINGS = ["Hi!", "Hey!", "Hello!", "Hi there!", "Hey there, hope you're well!", "Hello, I hope you're having a "
             "great day!", "Good morning!", "Hi, hope your week is going well."]
STRONG_WRAPPERS = [("Could you please", True), ("Can you please", True), ("Would you kindly", True),
                   ("Could you possibly", True), ("Would you be so kind as to", True), ("Is it possible for you to", True),
                   ("I was wondering if you could", False), ("I'd really appreciate it if you could", False),
                   ("I would love it if you could", False), ("If it's not too much trouble, could you", True)]
LIGHT_WRAPPERS = [("Please", False), ("Can you", True), ("Could you", True), ("Would you", True)]
CLOSINGS = ["Thanks!", "Thank you!", "Thanks so much!", "Thank you so much in advance!",
            "Thanks a lot, I really appreciate it!", "Many thanks!", "Cheers!", "Any help would be greatly appreciated.",
            "Thanks in advance, you're a lifesaver!", "Thank you, I really appreciate your help!"]
LIGHT_CLOSINGS = ["Thanks!", "Thank you!", "Thanks."]
#Backstory that doesn't change the answer
BACKSTORIES = ["I've been stuck on this for a while.", "Sorry to bother you with this.",
               "Sorry if this is a silly question.", "I hope this isn't too much to ask.",
               "It's been a really long week, haha.", "So I was thinking about this earlier today.",
               "I've been meaning to ask about this for a while now.",
               "My coffee just went cold while I was trying to figure this out."]
#(instruction, the same instruction reworded, flags the core must not have, flags it must have)
REPEATS = [("Keep it short.", "It shouldn't be long.", {"len"}, set()),
           ("Keep it brief.", "Don't make it too long either.", {"len"}, set()),
           ("Use plain language.", "Avoid jargon and keep the wording simple.", set(), set()),
           ("Make it easy to follow.", "It should be clear and easy to understand.", set(), set()),
           ("Use bullet points.", "Format it as a bulleted list.", {"fmt"}, set()),
           ("Double-check that it's accurate.", "Make sure everything in it is correct.", {"prose"}, set()),
           ("Keep the tone friendly.", "It should sound warm and friendly.", set(), {"prose"})]
#Composed categories, in the order they're written out
COMPOSED_CATEGORIES = ("concise", "filler", "filler-light", "hedging", "duplicates", "wordy", "formatting")
#The waste variant every core gets, and how often each is picked
WASTE_CATEGORIES = ("filler", "filler-light", "hedging", "duplicates")
WASTE_WEIGHTS = (50, 15, 20, 15)


def fill(text: str, wordy: bool) -> str:
    for marker, (short, long) in WORDY.items():
        text = text.replace(marker, long if wordy else short)
    return text


"""
* @brief Writes a core out as a prompt.
* @post
* 1. With a wrapper, the request follows it as written ("Could you please write..."); without one its first letter
*    is capitalized.
* 2. It ends with ":" before material on its own lines, "?" when it's a question, "." otherwise, unless end is given.
* 3. A sentence tail follows after gap; a material tail follows directly. The opener goes first, the closer last.
"""
def render(core: Core, wrapper: tuple[str, bool] | None = None, opener: str = "", closer: str = "",
           wordy: bool = False, end: str | None = None, gap: str = " ") -> str:
    head, tail = fill(core.head, wordy), fill(core.tail, wordy)
    if wrapper:
        text, asked = f"{wrapper[0]} {head}", wrapper[1]
    else:
        text, asked = head[0].upper() + head[1:], "q" in core.flags
    if end is None:
        end = ":" if core.block else "?" if asked else "."
    text += end
    if tail:
        text += tail if core.block else gap + tail
    if opener:
        text = f"{opener} {text}"
    if closer:
        text += ("\n" if core.block else " ") + closer
    return text


#Each builder returns (prompt, its shortest faithful rewrite)
def concise(core: Core, _rng: random.Random) -> tuple[str, str]:
    direct = render(core)
    return direct, direct


def filler(core: Core, rng: random.Random) -> tuple[str, str]:
    opener = rng.choice(GREETINGS) if rng.random() < 0.7 else ""
    closer = rng.choice(CLOSINGS)
    if "q" in core.flags:
        return render(core, opener=opener or rng.choice(GREETINGS), closer=closer), render(core)
    return render(core, wrapper=rng.choice(STRONG_WRAPPERS), opener=opener, closer=closer), render(core)


def fillerLight(core: Core, rng: random.Random) -> tuple[str, str]:
    if "q" in core.flags:
        return render(core, closer=rng.choice(LIGHT_CLOSINGS)), render(core)
    return render(core, wrapper=rng.choice(LIGHT_WRAPPERS)), render(core)


def hedging(core: Core, rng: random.Random) -> tuple[str, str]:
    opener = rng.choice(BACKSTORIES)
    if rng.random() < 0.4:
        opener = f"{rng.choice(GREETINGS)} {opener}"
    closer = rng.choice(CLOSINGS) if rng.random() < 0.5 else ""
    return render(core, opener=opener, closer=closer), render(core)


def duplicates(core: Core, rng: random.Random) -> tuple[str, str]:
    fitting = [(first, second) for first, second, excluded, required in REPEATS
               if not excluded & core.flags and required <= core.flags]
    first, second = rng.choice(fitting)
    direct = render(core) + ("\n" if core.block else " ") + first
    return f"{direct} {second}", direct


def wordy(core: Core, _rng: random.Random) -> tuple[str, str]:
    return render(core, wordy=True), render(core)


def formatting(core: Core, _rng: random.Random) -> tuple[str, str]:
    return render(core, end="???" if "q" in core.flags else "!!!", gap="\n\n\n\n"), render(core)


BUILDERS = {"concise": concise, "filler": filler, "filler-light": fillerLight, "hedging": hedging,
            "duplicates": duplicates, "wordy": wordy, "formatting": formatting}


"""
* @brief Composes cases from every core.
* @post
* 1. Each core gets one waste variant (filler most often) and sometimes a second, its plain form about a third of
*    the time, a wordy variant when it has markers, and now and then a formatting variant (sentence tails only).
* 2. Each case's expect is measured against the core's plain form (measuredLabel), and keeps the core's mustKeep.
* 3. The same seed always gives the same cases.
"""
def composeCases(rng: random.Random) -> list[dict]:
    cases = []
    for core in CORES:
        categories = ["concise"] if rng.random() < 0.35 else []
        waste = rng.choices(WASTE_CATEGORIES, weights=WASTE_WEIGHTS)[0]
        categories.append(waste)
        if rng.random() < 0.2:
            categories.append(rng.choice([category for category in WASTE_CATEGORIES if category != waste]))
        if any(marker in core.head + core.tail for marker in WORDY):
            categories.append("wordy")
        if not core.block and rng.random() < 0.05:
            categories.append("formatting")
        for category in categories:
            prompt, direct = BUILDERS[category](core, rng)
            cases.append({"id": f"{category}-{core.slug}", "category": category, "prompt": prompt,
                          "mustKeep": list(core.keep), "expect": measuredLabel(prompt, direct),
                          "source": "composed", "direct": direct})
    return cases


def loadSource(path: Path) -> list[dict]:
    cases = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as error:
            sys.exit(f"{path.relative_to(REPO)}:{number}: {error}")
        case.setdefault("mustKeep", [])
        case["source"] = path.stem
        case["line"] = f"{path.relative_to(REPO)}:{number}"
        cases.append(case)
    return cases


#A hand-written case's direct form sets its expect ("auto") or must agree with it
def resolveExpect(case: dict) -> str | None:
    if "direct" not in case or case.get("expect") == "ask":
        return None
    measured = measuredLabel(case["prompt"], case["direct"])
    if case.get("expect") == "auto":
        case["expect"] = measured
        return None
    if case.get("expect") != measured:
        saved = countTokens(case["prompt"]) - countTokens(case["direct"])
        return f"{case['id']}: expect {case.get('expect')} but its direct form saves {saved} tokens ({measured})"
    return None


def findProblems(cases: list[dict]) -> list[str]:
    problems = []
    ids = Counter(case["id"] for case in cases)
    problems += [f"duplicate id {caseId} ({count}x)" for caseId, count in ids.items() if count > 1]
    #Whitespace-only prompts are compared as written, so an empty prompt and a blank one stay two cases
    prompts = Counter(" ".join(case["prompt"].lower().split()) or case["prompt"] for case in cases)
    problems += [f"repeated prompt: {prompt[:60]!r} ({count}x)" for prompt, count in prompts.items() if count > 1]
    for case in cases:
        where = case.get("line", case["id"])
        if case.get("expect") not in EXPECTS:
            problems.append(f"{where}: unknown expect {case.get('expect')!r}")
        if not case.get("category"):
            problems.append(f"{where}: no category")
        for keep in case["mustKeep"]:
            if keep not in case["prompt"]:
                problems.append(f"{where}: mustKeep {keep!r} isn't in the prompt")
            if "direct" in case and keep.lower() not in case["direct"].lower():
                problems.append(f"{where}: mustKeep {keep!r} isn't in the direct form")
        if "direct" in case and case["source"] != "composed" and case["direct"] == case["prompt"]:
            problems.append(f"{where}: direct form is the prompt itself")
    return problems


#Pairs of hand-written prompts that share most of their word 3-grams. Prompts under 3 words have none to compare
def findNearDuplicates(cases: list[dict]) -> list[tuple[str, str, float]]:
    def shingles(text: str) -> set[tuple[str, ...]]:
        words = text.lower().split()
        return {tuple(words[i:i + 3]) for i in range(len(words) - 2)}
    sets = [(case["id"], shingles(case["prompt"])) for case in cases if case["source"] != "composed"]
    pairs = []
    for (firstId, first), (secondId, second) in combinations(sets, 2):
        if first and second:
            overlap = len(first & second) / len(first | second)
            if overlap >= NEAR_DUPLICATE:
                pairs.append((firstId, secondId, round(overlap, 2)))
    return pairs


def printMakeUp(cases: list[dict]):
    print(f"{len(cases)} cases")
    print("By source:", dict(Counter(case["source"] for case in cases).most_common()))
    print("By expect:", dict(Counter(case["expect"] for case in cases).most_common()))
    lengths = sorted(countTokens(case["prompt"]) for case in cases)
    print(f"Tokens per prompt: min {lengths[0]}, median {statistics.median(lengths):g}, "
          f"p90 {lengths[int(len(lengths) * 0.9)]}, max {lengths[-1]}")
    print("By category (optimize / unchanged / ask):")
    byCategory: dict[str, Counter] = {}
    for case in cases:
        byCategory.setdefault(case["category"], Counter())[case["expect"]] += 1
    for category, counts in sorted(byCategory.items(), key=lambda item: -sum(item[1].values())):
        print(f"  {category:20} {sum(counts.values()):4}   "
              f"{counts['optimize']:3} / {counts['unchanged']:3} / {counts['ask']:3}")


def main():
    parser = argparse.ArgumentParser(description="Build evals/prompts.jsonl from evals/sources and the cores here")
    parser.add_argument("--check", action="store_true", help="validate and print the make-up without writing")
    args = parser.parse_args()

    fixed = loadSource(SEED_FILE)
    for path in sorted(SOURCES.glob("hand-*.jsonl")):
        fixed += loadSource(path)
    problems = [problem for case in fixed if (problem := resolveExpect(case))]

    rng = random.Random(RANDOM_SEED)
    composed = composeCases(rng)
    needed = TARGET_SIZE - len(fixed)
    if needed > len(composed):
        problems.append(f"{len(fixed)} hand-written cases leave {needed} to compose, but the cores only give "
                        f"{len(composed)}: add cores")
    rng.shuffle(composed)
    order = {category: index for index, category in enumerate(COMPOSED_CATEGORIES)}
    composed = sorted(composed[:max(needed, 0)], key=lambda case: (order[case["category"]], case["id"]))
    cases = fixed + composed

    problems += findProblems(cases)
    if len(cases) != TARGET_SIZE:
        problems.append(f"{len(cases)} cases, expected {TARGET_SIZE}")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        sys.exit(f"{len(problems)} problem(s), nothing written")

    for first, second, overlap in findNearDuplicates(cases):
        print(f"warning: near-duplicate prompts {first} and {second} ({overlap})", file=sys.stderr)
    printMakeUp(cases)
    if args.check:
        return
    with OUTPUT.open("w", encoding="utf-8") as out:
        for case in cases:
            out.write(json.dumps({field: case[field] for field in FIELDS}, ensure_ascii=False) + "\n")
    print(f"Wrote {OUTPUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
