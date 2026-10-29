import os
import logging
from functools import lru_cache
import tiktoken
from anthropic import Anthropic, APIError

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
logger = logging.getLogger(__name__)

#Which LLM the user is prompting, since each one tokenizes text differently
CHATGPT = "chatgpt"
CLAUDE = "claude"
TARGETS = (CHATGPT, CLAUDE)
DEFAULT_TARGET = CHATGPT

#had the old stuff...
#GPT-4o and every newer gpt model use o200k_base
CHATGPT_ENCODING = "o200k_base"

#Claude tokenizer soso count against the current claude.ai model
CLAUDE_COUNT_MODEL = "claude-sonnet-5-5"
#Claude tokens per o200k_base token. Claude's tokenizer isn't public, so estimateTokens multiplies the local
#count by this. Measured with scripts/calibrate_claude_tokens.py on 10/28/2026 (14 samples, 1.19-1.90 per prompt);
#re-run it when CLAUDE_COUNT_MODEL changes, and on real prompts once there are some
CLAUDE_TOKEN_RATIO = 1.48

def checkTarget(target: str):
    if target not in TARGETS:
        raise ValueError(f"Unknown target '{target}', expected one of {TARGETS}")

#o200k_base count, no API call
def localTokenCount(text: str) -> int:
    return len(tiktoken.get_encoding(CHATGPT_ENCODING).encode(text))

"""
* @brief Counts the number of tokens in a text string, as the target LLM would.
* @post
* 1. An unknown target raises a ValueError.
* 2. Empty text returns 0 without any API call.
* 3. ChatGPT text is encoded locally with the o200k_base tokenizer.
* 4. Claude text is counted by Anthropic's count_tokens endpoint; if that
*    call fails, estimateTokens is used instead.
* 5. Results are cached, so counting the same prompt twice (Auditor then
*    Optimizer) costs only one API call.
* 6. Use this for counts the user sees. Counts that only compare drafts use estimateTokens.
"""
@lru_cache(maxsize=1024)
def countTokens(text: str, target: str = DEFAULT_TARGET) -> int:
    checkTarget(target)
    if not text:
        return 0
    if target == CLAUDE:
        try:
            return countClaudeTokens(text)
        except APIError as error:
            logger.warning("Claude token count failed, using the local estimate: %s", error)
    return estimateTokens(text, target)

"""
* @brief Estimates tokens locally, for comparisons that run often and don't need the exact count.
* @post
* 1. An unknown target raises a ValueError, and empty text is 0.
* 2. ChatGPT counts are exact (o200k_base, same as countTokens).
* 3. Claude counts are the o200k_base count times CLAUDE_TOKEN_RATIO (at least 1), with no API call.
*    The ratio scales every text alike, so comparing a draft with the original still works.
"""
@lru_cache(maxsize=1024)
def estimateTokens(text: str, target: str = DEFAULT_TARGET) -> int:
    checkTarget(target)
    if not text:
        return 0
    count = localTokenCount(text)
    return count if target == CHATGPT else max(round(count * CLAUDE_TOKEN_RATIO), 1)

"""
* @brief Counts tokens with Anthropic's count_tokens endpoint.
* @post
* 1. The text is sent as a single user message.
* 2. The fixed message-framing overhead is subtracted so only the
*    prompt's own tokens are returned.
"""
def countClaudeTokens(text: str) -> int:
    return max(countClaudeMessage(text) - claudeMessageOverhead(), 1)

def countClaudeMessage(text: str) -> int:
    response = client.messages.count_tokens(
        model=CLAUDE_COUNT_MODEL,
        messages=[{"role": "user", "content": text}],
    )
    return response.input_tokens

#count_tokens includes the user-turn wrapper; measure it once with a one-token message
@lru_cache(maxsize=1)
def claudeMessageOverhead() -> int:
    return countClaudeMessage("a") - 1
