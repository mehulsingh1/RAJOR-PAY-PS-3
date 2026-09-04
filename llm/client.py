"""
Shared Groq LLM client used across the recovery agent.
Follows the ChatGroq + dotenv pattern.
"""

import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model="openai/gpt-oss-120b",
    temperature=0.2,  # low temp — this agent needs consistent, auditable decisions
)
