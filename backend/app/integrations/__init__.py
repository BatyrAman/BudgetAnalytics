"""Adapters to external systems.

* ``llm`` — provider-independent LLM interface (OpenAI implemented; Anthropic,
  Gemini and Ollama plug in by implementing ``LLMProvider``).

Bank statements are imported from exported FILES only (``app/services/imports``);
no bank APIs are used and no bank credentials are ever requested or stored.
"""
