import json
import re
import logging
from typing import Optional, Type, TypeVar
from pydantic import BaseModel
from app.config import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    API_TIMEOUT_SECONDS,
    MAX_RETRIES,
)

logger = logging.getLogger("resqai.tools.llm_client")
T = TypeVar("T", bound=BaseModel)

def _clean_json_string(text: str) -> str:
    """Extracts JSON substring from markdown fences or surrounding prose."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    # Check if string starts with { or [
    start_brace = text.find("{")
    end_brace = text.rfind("}")
    if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
        return text[start_brace:end_brace + 1].strip()
    return text

def call_gemini_api(prompt: str, system_prompt: str = "") -> Optional[str]:
    """Use the configured model with bounded transport retries and a closed client."""
    if not GEMINI_API_KEY:
        return None

    try:
        from google import genai
        from google.genai import types

        # Do not multiply retries across models, SDKs, and schema validation.
        # A transport failure falls back; invalid JSON may be retried by the caller.
        with genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=int(API_TIMEOUT_SECONDS * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        ) as client:
            response = client.models.generate_content(
                model=DEFAULT_GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt or None,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            return response.text if response and response.text else None
    except Exception as exc:
        # Provider exception bodies can contain request data; keep them out of logs.
        logger.warning("Gemini request failed (%s); using provider fallback.", type(exc).__name__)
        return None

def call_groq_api(prompt: str, system_prompt: str = "") -> Optional[str]:
    """Invokes Groq API via groq SDK."""
    if not GROQ_API_KEY:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY, timeout=API_TIMEOUT_SECONDS)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        chat_completion = client.chat.completions.create(
            messages=messages,
            model=DEFAULT_GROQ_MODEL,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.warning(f"Groq API call failed: {e}")
        return None

def call_llm_json(
    prompt: str,
    schema_cls: Type[T],
    system_prompt: str = "",
    model_provider_preference: str = "auto"
) -> tuple[Optional[T], str, Optional[str]]:
    """
    Calls configured LLM with retry-on-invalid-output.
    Returns: (parsed_pydantic_instance_or_None, provider_or_model_name, error_message_or_None)
    """
    providers_to_try = []
    if model_provider_preference == "groq" or (not GEMINI_API_KEY and GROQ_API_KEY):
        providers_to_try = [("groq", call_groq_api), ("gemini", call_gemini_api)]
    else:
        providers_to_try = [("gemini", call_gemini_api), ("groq", call_groq_api)]

    last_error = None
    for provider_name, api_caller in providers_to_try:
        for attempt in range(MAX_RETRIES + 1):
            raw_response = None
            try:
                raw_response = api_caller(prompt, system_prompt)
                if not raw_response:
                    last_error = f"{provider_name} unavailable or returned no content"
                    break
                clean_json = _clean_json_string(raw_response)
                data = json.loads(clean_json)
                parsed = schema_cls.model_validate(data)
                model_name = DEFAULT_GEMINI_MODEL if provider_name == "gemini" else DEFAULT_GROQ_MODEL
                return parsed, f"{provider_name}:{model_name}", None
            except Exception as e:
                last_error = f"{provider_name} attempt {attempt+1} failed: {str(e)}"
                logger.warning(last_error)
                if attempt < MAX_RETRIES:
                    prompt = f"{prompt}\n\nIMPORTANT: The previous output failed schema validation ({str(e)}). You MUST output ONLY valid JSON matching the schema."

    return None, "fallback", last_error
