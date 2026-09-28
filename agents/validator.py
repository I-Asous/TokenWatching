import os
from dataclasses import dataclass
from anthropic import Anthropic
 
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
 
 
@dataclass
class ValidationResult:
    originalPrompt: str
    optimizedPrompt: str
    qualityScore: int
    passed: bool
    reasoning: str

VALIDATOR_SYSTEM_PROMPT = """You are a prompt-quality validator. You will be given an ORIGINAL prompt and an 
OPTIMIZED version of it. Your job is to judge whether the optimized version still preserves the original's 
intent, meaning, and any explicit requirements (format, constraints, edge cases). 

Respond in the exact way:
Score <float 1, 10>
Passed <Yes or No>
Reasoning: Give a one sentence reason justifying your response.


Score should be based on the following scale:

9-10: Optimized prompt is functionally identical in intent and requirements.

7-8.99:

5-6.99:

3-4.99:

1-2.99:

0:

"""