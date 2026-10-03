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

#GPT-4o and every newer ChatGPT model use o200k_base
CHATGPT_ENCODING = "o200k_base"

#Claude tokenizer So count against the current claude.ai model
CLAUDE_COUNT_MODEL = "claude-sonnet-5-5"

"""
* @brief Counts the number of tokens in a text string, as the target LLM would.
* @post
* 1. An unknown target raises a ValueError.
* 2. Empty text returns 0 without any API call.
* 3. ChatGPT text is encoded locally with the o200k_base tokenizer.
* 4. Claude text is counted by Anthropic's count_tokens endpoint; if that
*    call fails, the local ChatGPT count is used as an estimate instead.
* 5. Results are cached, so counting the same prompt twice (Auditor then
*    Optimizer) costs only one API call.
"""
@lru_cache(maxsize=1024)
def countTokens(text: str, target: str = DEFAULT_TARGET) -> int:
    if target not in TARGETS:
        raise ValueError(f"Unknown target '{target}', expected one of {TARGETS}")
    if not text:
        return 0
    if target == CLAUDE:
        try:
            return countClaudeTokens(text)
        except APIError as error:
            logger.warning("Claude token count failed, using %s estimate: %s",
                           CHATGPT_ENCODING, error)
    return len(tiktoken.get_encoding(CHATGPT_ENCODING).encode(text))

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
