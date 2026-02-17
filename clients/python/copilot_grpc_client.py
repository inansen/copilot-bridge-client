"""
Copilot Bridge — Python gRPC Client
Implements ICopilotClient over gRPC transport.

Requires:
    pip install grpcio grpcio-tools

Generate stubs (from project root):
    python -m grpc_tools.protoc -I proto --python_out=clients/python --grpc_python_out=clients/python proto/copilot_bridge.proto

Usage:
    from copilot_grpc_client import CopilotGrpcClient

    client = CopilotGrpcClient()
    print(client.chat("Hello"))

    for chunk in client.chat_stream("Write a poem"):
        print(chunk, end="", flush=True)
"""

from __future__ import annotations

import grpc
from typing import Generator, Optional, Union

from copilot_interface import (
    ICopilotClient, ChatMessage, ChatResponse, ModelInfo, StatusResponse,
)

# Import generated protobuf stubs
import copilot_bridge_pb2 as pb2
import copilot_bridge_pb2_grpc as pb2_grpc


class CopilotGrpcClient(ICopilotClient):
    """gRPC-based client for the Copilot Bridge."""

    def __init__(
        self,
        address: str = "127.0.0.1:3742",
        default_model: Optional[str] = None,
        default_vendor: Optional[str] = None,
    ):
        self.address = address
        self.default_model = default_model or ""
        self.default_vendor = default_vendor or ""
        self._channel = grpc.insecure_channel(address)
        self._stub = pb2_grpc.CopilotBridgeServiceStub(self._channel)

    def close(self):
        self._channel.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── ICopilotClient implementation ─────────────────────────────────────

    def status(self) -> StatusResponse:
        reply = self._stub.GetStatus(pb2.StatusRequest())
        return StatusResponse(
            status=reply.status,
            port=reply.port,
            default_model=reply.default_model,
            requests_served=reply.requests_served,
            version=reply.version,
        )

    def list_models(self) -> list[ModelInfo]:
        reply = self._stub.ListModels(pb2.ListModelsRequest())
        return [
            ModelInfo(
                id=m.id, name=m.name, vendor=m.vendor,
                family=m.family, version=m.version,
                max_input_tokens=m.max_input_tokens,
            )
            for m in reply.models
        ]

    def chat(
        self,
        messages: Union[str, list[ChatMessage]],
        *,
        model: Optional[str] = None,
        vendor: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        req = self._build_request(messages, model, vendor, system_prompt)
        reply = self._stub.Chat(req)
        return reply.content

    def chat_full(
        self,
        messages: Union[str, list[ChatMessage]],
        *,
        model: Optional[str] = None,
        vendor: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        req = self._build_request(messages, model, vendor, system_prompt)
        reply = self._stub.Chat(req)
        return ChatResponse(id=reply.id, model=reply.model, content=reply.content)

    def chat_stream(
        self,
        messages: Union[str, list[ChatMessage]],
        *,
        model: Optional[str] = None,
        vendor: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Generator[str, None, None]:
        req = self._build_request(messages, model, vendor, system_prompt)
        for chunk in self._stub.ChatStream(req):
            if chunk.error:
                raise RuntimeError(f"gRPC stream error: {chunk.error}")
            if chunk.done:
                return
            if chunk.content:
                yield chunk.content

    # ── Internals ─────────────────────────────────────────────────────────

    def _build_request(
        self,
        messages: Union[str, list[ChatMessage]],
        model: Optional[str],
        vendor: Optional[str],
        system_prompt: Optional[str],
    ) -> pb2.ChatRequest:
        if isinstance(messages, str):
            msgs = [pb2.ChatMessage(role="user", content=messages)]
        else:
            msgs = [pb2.ChatMessage(role=m.role, content=m.content) for m in messages]

        return pb2.ChatRequest(
            messages=msgs,
            model=model or self.default_model,
            vendor=vendor or self.default_vendor,
            system_prompt=system_prompt or "",
        )
