"""
Shared Groq LLM client used across the recovery agent.
Follows the ChatGroq + dotenv pattern.
"""

import os
import time

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model="openai/gpt-oss-120b",
    temperature=0.2,  # low temp — this agent needs consistent, auditable decisions
)


def invoke_text(messages, *, retries: int = 2, base_delay: float = 0.6,
                fallback: str | None = None) -> str:
    """
    Call the LLM and return the stripped text content, retrying transient
    failures (rate limits, timeouts) with exponential backoff.

    If every attempt fails: return `fallback` when given, else re-raise.
    """
    last_err = None
    for attempt in range(retries):
        try:
            return llm.invoke(messages).content.strip()
        except Exception as e:  # noqa: BLE001 — Groq/network errors vary
            last_err = e
            if attempt < retries - 1:
                time.sleep(base_delay * (2 ** attempt))

    if fallback is not None:
        print(f"[LLM] {retries} attempts failed ({last_err}); using fallback")
        return fallback
    raise RuntimeError(f"LLM call failed after {retries} attempts") from last_err
