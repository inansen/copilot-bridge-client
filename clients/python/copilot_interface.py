"""
Copilot Bridge — Python Abstract Interface
All transport implementations (HTTP, gRPC) implement this interface.

Usage:
    from copilot_interface import ICopilotClient

    def do_work(client: ICopilotClient):
        print(client.chat("Hello"))
        for chunk in client.chat_stream("Write a poem"):
            print(chunk, end="")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generator, Iterator, Optional, Union


# ── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class ChatMessage:
    role: str       # "user" | "assistant"
    content: str


@dataclass
class ChatOptions:
    model: Optional[str] = None
    vendor: Optional[str] = None
    system_prompt: Optional[str] = None


@dataclass
class StatusResponse:
    status: str = ""
    port: int = 0
    default_model: str = ""
    requests_served: int = 0
    version: str = ""


@dataclass
class ModelInfo:
    id: str = ""
    name: str = ""
    vendor: str = ""
    family: str = ""
    version: str = ""
    max_input_tokens: int = 0


@dataclass
class ChatResponse:
    id: int = 0
    model: str = ""
    content: str = ""


# ── Interface ────────────────────────────────────────────────────────────────

class ICopilotClient(ABC):
    """Abstract interface for the Copilot Bridge client.
    Implement for different transports (HTTP, gRPC, etc.)"""

    @abstractmethod
    def status(self) -> StatusResponse:
        """Get server status."""
        ...

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """List available Copilot models."""
        ...

    @abstractmethod
    def chat(
        self,
        messages: Union[str, list[ChatMessage]],
        *,
        model: Optional[str] = None,
        vendor: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Send a chat request and return the full response text."""
        ...

    @abstractmethod
    def chat_full(
        self,
        messages: Union[str, list[ChatMessage]],
        *,
        model: Optional[str] = None,
        vendor: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """Send a chat request and return the structured response."""
        ...

    @abstractmethod
    def chat_stream(
        self,
        messages: Union[str, list[ChatMessage]],
        *,
        model: Optional[str] = None,
        vendor: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Stream a chat response. Yields content fragments."""
        ...

    def chat_json(
        self,
        messages: Union[str, list[ChatMessage]],
        *,
        model: Optional[str] = None,
        vendor: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """Send a chat request and parse the response as JSON."""
        import json
        import re

        text = self.chat(messages, model=model, vendor=vendor, system_prompt=system_prompt)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            return json.loads(match.group(1).strip())
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Could not parse JSON from response:\n{text[:500]}")
