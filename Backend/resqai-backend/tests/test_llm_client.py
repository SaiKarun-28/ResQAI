from types import SimpleNamespace

from pydantic import BaseModel

from app.tools import llm_client

# Preserve the implementation before the global offline fixture stubs providers.
call_gemini = llm_client.call_gemini_api


class ConnectivityResult(BaseModel):
    ok: bool


def test_gemini_uses_configured_model_timeout_and_closes_client(monkeypatch):
    from google import genai
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            captured['closed'] = True

        def generate_content(self, **kwargs):
            captured['generation'] = kwargs
            return SimpleNamespace(text='{"ok": true}')

    monkeypatch.setattr(genai, 'Client', Client)
    monkeypatch.setattr(llm_client, 'GEMINI_API_KEY', 'test-key-not-a-credential')
    monkeypatch.setattr(llm_client, 'API_TIMEOUT_SECONDS', 20)
    assert call_gemini('Connectivity test', 'Return JSON') == '{"ok": true}'
    assert captured['http_options'].timeout == 20000
    assert captured['http_options'].retry_options.attempts == 1
    assert captured['generation']['model'] == llm_client.DEFAULT_GEMINI_MODEL
    assert captured['generation']['config'].response_mime_type == 'application/json'
    assert captured['generation']['config'].system_instruction == 'Return JSON'
    assert captured['closed']


def test_gemini_failure_does_not_log_sensitive_exception_body(monkeypatch, caplog):
    from google import genai

    def failed_client(**kwargs):
        raise RuntimeError('sensitive-request-body-marker')

    monkeypatch.setattr(genai, 'Client', failed_client)
    monkeypatch.setattr(llm_client, 'GEMINI_API_KEY', 'test-key-not-a-credential')
    assert call_gemini('Test') is None
    assert 'RuntimeError' in caplog.text
    assert 'sensitive-request-body-marker' not in caplog.text


def test_missing_key_never_constructs_sdk_client(monkeypatch):
    from google import genai

    def forbidden(**kwargs):
        raise AssertionError('SDK should not be initialized without a key')

    monkeypatch.setattr(genai, 'Client', forbidden)
    monkeypatch.setattr(llm_client, 'GEMINI_API_KEY', '')
    assert call_gemini('Test') is None


def test_unavailable_provider_is_not_repeated_for_schema_retries(monkeypatch):
    calls = []

    def unavailable(*args):
        calls.append(True)
        return None

    monkeypatch.setattr(llm_client, 'MAX_RETRIES', 5)
    monkeypatch.setattr(llm_client, 'call_gemini_api', unavailable)
    parsed, model, error = llm_client.call_llm_json('Test', ConnectivityResult)
    assert len(calls) == 1
    assert parsed is None and model == 'fallback'
    assert 'unavailable' in error


def test_invalid_json_retries_and_records_actual_configured_model(monkeypatch):
    outputs = iter(['invalid json', '{"ok": true}'])
    monkeypatch.setattr(llm_client, 'MAX_RETRIES', 1)
    monkeypatch.setattr(llm_client, 'call_gemini_api', lambda *args: next(outputs))
    parsed, model, error = llm_client.call_llm_json('Test', ConnectivityResult)
    assert parsed.ok
    assert model == f'gemini:{llm_client.DEFAULT_GEMINI_MODEL}'
    assert error is None
