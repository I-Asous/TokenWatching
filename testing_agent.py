"""
File to test connection to API
"""
import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
beta_message_tokens_count = client.beta.messages.count_tokens(
    messages=[
        {
            "content": "Hello, world",
            "role": "user",
        }
    ],
    model="claude-opus-5",
)

print(beta_message_tokens_count.context_management)