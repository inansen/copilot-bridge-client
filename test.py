#!/usr/bin/env python3
"""
test.py — Integration tests for Copilot API Bridge

Requires: VS Code running with the Copilot Bridge extension active.

Tests both HTTP and gRPC transports (gRPC tests skipped if stubs not generated).

Usage:
    python test.py                    # Run all tests
    python test.py --http-only        # HTTP tests only
    python test.py --grpc-only        # gRPC tests only
    python test.py --base-url http://127.0.0.1:3741
    python test.py --grpc-address 127.0.0.1:3742
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from typing import Optional

# Add clients/python to path
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "clients", "python"))

from copilot_interface import ICopilotClient, StatusResponse, ModelInfo, ChatResponse


# ── Test Framework ───────────────────────────────────────────────────────────

class TestResult:
    def __init__(self, name: str, passed: bool, message: str = "", duration: float = 0.0):
        self.name = name
        self.passed = passed
        self.message = message
        self.duration = duration

    def __str__(self):
        icon = "PASS" if self.passed else "FAIL"
        dur = f" ({self.duration:.2f}s)" if self.duration > 0 else ""
        msg = f" — {self.message}" if self.message else ""
        return f"  [{icon}] {self.name}{dur}{msg}"


def run_test(name: str, func, *args, **kwargs) -> TestResult:
    """Run a single test function and capture pass/fail."""
    start = time.time()
    try:
        result_msg = func(*args, **kwargs)
        duration = time.time() - start
        return TestResult(name, True, result_msg or "", duration)
    except Exception as e:
        duration = time.time() - start
        return TestResult(name, False, f"{type(e).__name__}: {e}", duration)


# ── Test Cases ───────────────────────────────────────────────────────────────

def test_status(client: ICopilotClient) -> str:
    """Test GET /status endpoint."""
    status = client.status()
    assert isinstance(status, StatusResponse), f"Expected StatusResponse, got {type(status)}"
    assert status.status == "running", f"Expected status='running', got '{status.status}'"
    assert status.version, "Version should not be empty"
    return f"status={status.status}, version={status.version}, requests={status.requests_served}"


def test_list_models(client: ICopilotClient) -> str:
    """Test GET /models endpoint."""
    models = client.list_models()
    assert isinstance(models, list), f"Expected list, got {type(models)}"
    assert len(models) > 0, "No models available — is GitHub Copilot signed in?"
    for m in models:
        assert isinstance(m, ModelInfo), f"Expected ModelInfo, got {type(m)}"
        assert m.id, "Model id should not be empty"
        assert m.vendor, "Model vendor should not be empty"
    families = [m.family for m in models]
    return f"{len(models)} models: {', '.join(families)}"


def test_chat_simple(client: ICopilotClient, model: Optional[str] = None) -> str:
    """Test simple chat with a string prompt."""
    response = client.chat("Reply with exactly: HELLO_TEST_OK", model=model)
    assert isinstance(response, str), f"Expected str, got {type(response)}"
    assert len(response) > 0, "Response should not be empty"
    return f"response length={len(response)}, preview='{response[:80]}'"


def test_chat_with_model(client: ICopilotClient, model: Optional[str] = None) -> str:
    """Test chat with the selected model."""
    response = client.chat("Reply with exactly: MODEL_TEST_OK", model=model)
    assert isinstance(response, str), f"Expected str, got {type(response)}"
    assert len(response) > 0, "Response should not be empty"
    return f"response length={len(response)}, model={model}"


def test_chat_with_system_prompt(client: ICopilotClient, model: Optional[str] = None) -> str:
    """Test chat with a system prompt."""
    response = client.chat(
        "What language should I use?",
        model=model,
        system_prompt="You are a Python expert. Always recommend Python. Keep answers under 20 words.",
    )
    assert isinstance(response, str), f"Expected str, got {type(response)}"
    assert len(response) > 0, "Response should not be empty"
    return f"response='{response[:100]}'"


def test_chat_conversation(client: ICopilotClient, model: Optional[str] = None) -> str:
    """Test multi-turn conversation."""
    from copilot_interface import ChatMessage

    response = client.chat(
        [
            ChatMessage(role="user", content="My name is TestBot."),
            ChatMessage(role="assistant", content="Hello TestBot! How can I help you?"),
            ChatMessage(role="user", content="What is my name? Reply in one word only."),
        ],
        model=model,
    )
    assert isinstance(response, str), f"Expected str, got {type(response)}"
    assert len(response) > 0, "Response should not be empty"
    return f"response='{response[:80]}'"


def test_chat_full(client: ICopilotClient, model: Optional[str] = None) -> str:
    """Test chat_full returning structured response."""
    resp = client.chat_full("Reply with: FULL_TEST_OK", model=model)
    assert isinstance(resp, ChatResponse), f"Expected ChatResponse, got {type(resp)}"
    assert resp.content, "Content should not be empty"
    assert resp.model, "Model should not be empty"
    return f"id={resp.id}, model={resp.model}, content_len={len(resp.content)}"


def test_chat_stream(client: ICopilotClient, model: Optional[str] = None) -> str:
    """Test streaming chat response."""
    chunks = []
    for chunk in client.chat_stream("Count from 1 to 5, one number per line", model=model):
        assert isinstance(chunk, str), f"Expected str chunk, got {type(chunk)}"
        chunks.append(chunk)

    full_text = "".join(chunks)
    assert len(chunks) > 0, "Should receive at least one chunk"
    assert len(full_text) > 0, "Combined text should not be empty"
    return f"{len(chunks)} chunks, total {len(full_text)} chars"


def test_chat_json(client: ICopilotClient, model: Optional[str] = None) -> str:
    """Test chat_json parsing."""
    result = client.chat_json(
        'Return a JSON object with keys "name" and "language". Values: "test" and "python". '
        'Return ONLY valid JSON, no markdown.',
        model=model,
    )
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "name" in result or "language" in result, f"Expected 'name' or 'language' key, got {list(result.keys())}"
    return f"parsed keys: {list(result.keys())}"


def test_chat_empty_rejected(client: ICopilotClient) -> str:
    """Test that empty messages are rejected."""
    try:
        client.chat([])
        raise AssertionError("Should have raised an error for empty messages")
    except Exception as e:
        if "AssertionError" in type(e).__name__:
            raise
        return f"correctly rejected: {type(e).__name__}"


# ── HTTP-only tests ──────────────────────────────────────────────────────────

def test_http_raw_status(base_url: str) -> str:
    """Test raw HTTP GET /status."""
    import urllib.request
    import json

    req = urllib.request.Request(f"{base_url}/status")
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "running"
        return f"raw HTTP OK, port={data.get('port')}"


def test_http_not_found(base_url: str) -> str:
    """Test that unknown endpoints return 404."""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(f"{base_url}/nonexistent")
        urllib.request.urlopen(req, timeout=10)
        raise AssertionError("Should have returned 404")
    except urllib.error.HTTPError as e:
        assert e.code == 404, f"Expected 404, got {e.code}"
        return "correctly returned 404"


def test_http_cors_headers(base_url: str) -> str:
    """Test CORS headers are present."""
    import urllib.request

    req = urllib.request.Request(f"{base_url}/status")
    with urllib.request.urlopen(req, timeout=10) as resp:
        cors = resp.headers.get("Access-Control-Allow-Origin")
        assert cors == "*", f"Expected CORS '*', got '{cors}'"
        return f"CORS header: {cors}"


# ── Test Runner ──────────────────────────────────────────────────────────────

def pick_model_interactive(client: ICopilotClient) -> str:
    """List models and let the user pick one interactively."""
    models = client.list_models()
    if not models:
        print("  No models available!")
        sys.exit(1)

    print(f"\n  Available models ({len(models)}):")
    print(f"  {'─' * 50}")
    for i, m in enumerate(models, 1):
        print(f"  {i:3d}) {m.family:<30s} [{m.vendor}]")
    print(f"  {'─' * 50}")

    while True:
        try:
            choice = input(f"  Select model [1-{len(models)}] (default=1): ").strip()
            if not choice:
                idx = 0
            else:
                idx = int(choice) - 1
            if 0 <= idx < len(models):
                return models[idx].family
            print(f"  Invalid choice. Enter 1-{len(models)}.")
        except (ValueError, EOFError):
            print(f"  Invalid input. Enter 1-{len(models)}.")


def run_interface_tests(client: ICopilotClient, transport_name: str, model: Optional[str] = None) -> list[TestResult]:
    """Run all ICopilotClient interface tests against a given client."""
    results = []
    tests = [
        ("status", test_status, client),
        ("list_models", test_list_models, client),
        ("chat_simple", test_chat_simple, client, model),
        ("chat_with_model", test_chat_with_model, client, model),
        ("chat_with_system_prompt", test_chat_with_system_prompt, client, model),
        ("chat_conversation", test_chat_conversation, client, model),
        ("chat_full", test_chat_full, client, model),
        ("chat_stream", test_chat_stream, client, model),
        ("chat_json", test_chat_json, client, model),
        ("chat_empty_rejected", test_chat_empty_rejected, client),
    ]

    print(f"\n{'=' * 60}")
    print(f"  {transport_name} Transport Tests (model: {model or 'default'})")
    print(f"{'=' * 60}")

    for name, func, *args in tests:
        result = run_test(f"{transport_name}::{name}", func, *args)
        results.append(result)
        print(result)

    return results


def run_http_specific_tests(base_url: str) -> list[TestResult]:
    """Run HTTP-specific tests (raw requests, CORS, etc.)"""
    results = []
    tests = [
        ("http_raw_status", test_http_raw_status, base_url),
        ("http_not_found", test_http_not_found, base_url),
        ("http_cors_headers", test_http_cors_headers, base_url),
    ]

    print(f"\n{'=' * 60}")
    print(f"  HTTP-Specific Tests")
    print(f"{'=' * 60}")

    for name, func, *args in tests:
        result = run_test(f"HTTP::{name}", func, *args)
        results.append(result)
        print(result)

    return results


def main():
    parser = argparse.ArgumentParser(description="Test the Copilot API Bridge")
    parser.add_argument("--base-url", default="http://127.0.0.1:3741", help="HTTP base URL")
    parser.add_argument("--grpc-address", default="127.0.0.1:3742", help="gRPC address")
    parser.add_argument("--http-only", action="store_true", help="Only run HTTP tests")
    parser.add_argument("--grpc-only", action="store_true", help="Only run gRPC tests")
    parser.add_argument("--api-key", default=None, help="API key if configured")
    parser.add_argument("--model", default=None, help="Model family to use (interactive picker if not specified)")
    args = parser.parse_args()

    all_results: list[TestResult] = []

    # ── HTTP Tests ────────────────────────────────────────────────────────

    if not args.grpc_only:
        from copilot_client import CopilotClient
        http_client = CopilotClient(base_url=args.base_url, api_key=args.api_key)

        # First check connectivity
        print(f"\nConnecting to HTTP server at {args.base_url}...")
        try:
            s = http_client.status()
            print(f"  Connected! Server version: {s.version}")
        except Exception as e:
            print(f"  CANNOT CONNECT: {e}")
            print("  Make sure VS Code is running with the Copilot Bridge extension.")
            if not args.grpc_only:
                sys.exit(1)

        # ── Model selection ───────────────────────────────────────────
        selected_model = args.model
        if not selected_model:
            selected_model = pick_model_interactive(http_client)
        print(f"\n  Using model: {selected_model}\n")

        all_results.extend(run_interface_tests(http_client, "HTTP", selected_model))
        all_results.extend(run_http_specific_tests(args.base_url))

    # ── gRPC Tests ────────────────────────────────────────────────────────

    if not args.http_only:
        try:
            from copilot_grpc_client import CopilotGrpcClient

            print(f"\nConnecting to gRPC server at {args.grpc_address}...")
            grpc_client = CopilotGrpcClient(address=args.grpc_address)

            try:
                s = grpc_client.status()
                print(f"  Connected! Server version: {s.version}")
                all_results.extend(run_interface_tests(grpc_client, "gRPC", selected_model if 'selected_model' in dir() else None))
            except Exception as e:
                print(f"  gRPC connection failed: {e}")
                print("  Skipping gRPC tests. To enable: install @grpc/grpc-js in the extension and generate Python stubs.")
            finally:
                grpc_client.close()

        except ImportError as e:
            print(f"\n  gRPC tests skipped — missing dependencies: {e}")
            print("  To enable gRPC tests:")
            print("    pip install grpcio grpcio-tools")
            print("    python -m grpc_tools.protoc -I proto --python_out=clients/python --grpc_python_out=clients/python proto/copilot_bridge.proto")

    # ── Summary ───────────────────────────────────────────────────────────

    print(f"\n{'=' * 60}")
    print(f"  TEST SUMMARY")
    print(f"{'=' * 60}")

    passed = sum(1 for r in all_results if r.passed)
    failed = sum(1 for r in all_results if not r.passed)
    total = len(all_results)
    total_time = sum(r.duration for r in all_results)

    print(f"  Total:  {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Time:   {total_time:.2f}s")

    if failed > 0:
        print(f"\n  Failed tests:")
        for r in all_results:
            if not r.passed:
                print(f"    - {r.name}: {r.message}")

    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
