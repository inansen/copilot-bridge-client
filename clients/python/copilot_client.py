"""
Copilot Bridge Client for Python
Connects to the VS Code Copilot API Bridge extension via HTTP.

Usage:
    from copilot_client import CopilotClient

    client = CopilotClient()  # defaults to http://127.0.0.1:3741
    response = client.chat("Explain Python decorators")
    print(response)

    # With conversation history
    response = client.chat([
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Python is a high-level programming language."},
        {"role": "user", "content": "What are its main features?"},
    ])

    # Streaming
    for chunk in client.chat_stream("Write a hello world"):
        print(chunk, end="", flush=True)

    # Choose model
    response = client.chat("Hello", model="gpt-4o-mini")
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Generator, Optional, Union

from copilot_interface import (
    ICopilotClient, ChatMessage, ChatResponse, ModelInfo, StatusResponse,
)


class CopilotClientError(Exception):
    """Raised when the Copilot Bridge returns an error."""
    pass


class CopilotClient(ICopilotClient):
    """HTTP-based client for the Copilot API Bridge VS Code extension."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:3741",
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        default_vendor: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.default_vendor = default_vendor

    # ── Public API ────────────────────────────────────────────────────────

    def status(self) -> StatusResponse:
        """Get server status."""
        data = self._get("/status")
        return StatusResponse(
            status=data.get("status", ""),
            port=data.get("port", 0),
            default_model=data.get("defaultModel", ""),
            requests_served=data.get("requestsServed", 0),
            version=data.get("version", ""),
        )

    def list_models(self) -> list[ModelInfo]:
        """List available Copilot models."""
        data = self._get("/models")
        return [
            ModelInfo(
                id=m.get("id", ""), name=m.get("name", ""),
                vendor=m.get("vendor", ""), family=m.get("family", ""),
                version=m.get("version", ""),
                max_input_tokens=m.get("maxInputTokens", 0),
            )
            for m in data.get("models", [])
        ]

    def chat(
        self,
        messages: Union[str, list[dict]],
        *,
        model: Optional[str] = None,
        vendor: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Send a chat request and return the full response text.

        Args:
            messages: A single string prompt, or a list of {"role": "user"|"assistant", "content": "..."} dicts.
            model: Model family override (e.g. "gpt-4o", "gpt-4o-mini", "claude-3.5-sonnet").
            vendor: Model vendor override (e.g. "copilot").
            system_prompt: Optional system-level instruction.

        Returns:
            The assistant's response text.
        """
        payload = self._build_payload(messages, model, vendor, system_prompt)
        data = self._post("/chat", payload)
        return data.get("content", "")

    def chat_stream(
        self,
        messages: Union[str, list[dict]],
        *,
        model: Optional[str] = None,
        vendor: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """
        Send a chat request and yield response chunks as they arrive (SSE stream).

        Args:
            messages: A single string prompt or list of message dicts.
            model: Model family override.
            vendor: Model vendor override.
            system_prompt: Optional system instruction.

        Yields:
            Response text fragments.
        """
        payload = self._build_payload(messages, model, vendor, system_prompt)
        yield from self._post_stream("/chat/stream", payload)

    def chat_full(
        self,
        messages: Union[str, list[dict]],
        *,
        model: Optional[str] = None,
        vendor: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """Send a chat request and return the structured response."""
        payload = self._build_payload(messages, model, vendor, system_prompt)
        data = self._post("/chat", payload)
        return ChatResponse(
            id=data.get("id", 0),
            model=data.get("model", ""),
            content=data.get("content", ""),
        )

    def chat_json(
        self,
        messages: Union[str, list[dict]],
        *,
        model: Optional[str] = None,
        vendor: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """
        Send a chat request and parse the response as JSON.
        Tries to extract JSON even if the response contains markdown fences.
        """
        import re

        text = self.chat(messages, model=model, vendor=vendor, system_prompt=system_prompt)
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try extracting from code fences or raw braces
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            return json.loads(match.group(1).strip())
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise CopilotClientError(f"Could not parse JSON from response:\n{text[:500]}")

    # ── Internals ─────────────────────────────────────────────────────────

    def _build_payload(
        self,
        messages: Union[str, list[dict]],
        model: Optional[str],
        vendor: Optional[str],
        system_prompt: Optional[str],
    ) -> dict:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        else:
            # Convert ChatMessage dataclass objects to dicts if needed
            messages = [
                {"role": m.role, "content": m.content} if hasattr(m, "role") and not isinstance(m, dict) else m
                for m in messages
            ]

        payload: dict = {"messages": messages}
        m = model or self.default_model
        v = vendor or self.default_vendor
        if m:
            payload["model"] = m
        if v:
            payload["vendor"] = v
        if system_prompt:
            payload["systemPrompt"] = system_prompt
        return payload

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise CopilotClientError(f"HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise CopilotClientError(
                f"Cannot connect to Copilot Bridge at {self.base_url}. "
                f"Is VS Code running with the extension? Error: {e.reason}"
            ) from e

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise CopilotClientError(f"HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise CopilotClientError(
                f"Cannot connect to Copilot Bridge at {self.base_url}. "
                f"Is VS Code running with the extension? Error: {e.reason}"
            ) from e

    def _post_stream(self, path: str, payload: dict) -> Generator[str, None, None]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise CopilotClientError(f"HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise CopilotClientError(
                f"Cannot connect to Copilot Bridge at {self.base_url}. Error: {e.reason}"
            ) from e

        try:
            buffer = ""
            while True:
                chunk = resp.read(1024)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8")
                while "\n\n" in buffer:
                    event, buffer = buffer.split("\n\n", 1)
                    for line in event.split("\n"):
                        if line.startswith("data: "):
                            event_data = json.loads(line[6:])
                            if event_data.get("done"):
                                return
                            if "error" in event_data:
                                raise CopilotClientError(event_data["error"])
                            if "content" in event_data:
                                yield event_data["content"]
        finally:
            resp.close()


# ── Convenience function ──────────────────────────────────────────────────────

_default_client: Optional[CopilotClient] = None


def ask_copilot(
    prompt: str,
    *,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    base_url: str = "http://127.0.0.1:3741",
) -> str:
    """
    One-liner to ask Copilot a question.

    >>> from copilot_client import ask_copilot
    >>> answer = ask_copilot("What is a monad?")
    """
    global _default_client
    if _default_client is None or _default_client.base_url != base_url:
        _default_client = CopilotClient(base_url=base_url)
    return _default_client.chat(prompt, model=model, system_prompt=system_prompt)


if __name__ == "__main__":
    # Quick test
    client = CopilotClient()
    print("Status:", client.status())
    print("Models:", client.list_models())
    print()
    print("Chat response:")
    resp = client.chat("Say hello in 3 languages")
    print(resp)
