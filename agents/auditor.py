import os
#import re
#from dataclasses import dataclass, field 
#import tiktoken
from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))