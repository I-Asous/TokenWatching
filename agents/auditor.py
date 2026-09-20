import os
#import re
from dataclasses import dataclass, field 
import tiktoken
from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

@dataclass
class Auditor:
    tokenCount: int
    estimatedCost: float
    issues: list[str] = field(default_factory = list)
    
"""
 * @brief Counts the number of tokens in a text string
 * @post
 *  1. The text is encoded using the cl100k_base tokenizer
 *  2. The number of resulting tokens is calculated then returned
"""
def countTokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

#Test dummy haha
if __name__ == "__main__":
    test1 = "Hi world me llamo islam"
    test2 = "Please PLEASE please could you really kindly help me write a essay about some dragons?"
    test3 = ""

    print("Text:", test1)
    print("Token count:", countTokens(test1))
    print()

    print("Text:", test2)
    print("Token count:", countTokens(test2))
    print()

    print("Text:", test3)
    print("Token count:", countTokens(test3))
    