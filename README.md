# Copilot API Bridge

A VS Code extension that exposes GitHub Copilot as a **local HTTP + gRPC API**, so you can call it from any language — Python, C#, TypeScript, curl, or anything that speaks HTTP/gRPC.

## How It Works

```
┌──────────────┐  HTTP / gRPC ┌──────────────────┐  VS Code LM API  ┌──────────┐
│  Your Code   │ ───────────► │ Copilot Bridge   │ ───────────────► │ GitHub   │
│ (Python/C#/  │ ◄─────────── │ (VS Code ext)    │ ◄─────────────── │ Copilot  │
│  TS/curl)    │  JSON / SSE  │ HTTP :3741       │                  │          │
│              │  Protobuf    │ gRPC :3742       │                  │          │
└──────────────┘              └──────────────────┘                  └──────────┘
```

The extension starts local HTTP and gRPC servers on `127.0.0.1` that proxy requests to the GitHub Copilot language model API using your logged-in GitHub account.

All clients implement a shared **`ICopilotClient` interface**, so you can swap transports (HTTP ↔ gRPC) without changing your code.

## Project Structure

```
vs-copilot-client/
├── README.md
├── test.py                                 # Integration tests (HTTP + gRPC)
├── proto/
│   └── copilot_bridge.proto                # gRPC service definition
├── vscode-extension/
│   ├── extension.js                        # HTTP + gRPC server
│   └── package.json                        # VS Code config & settings
└── clients/
    ├── python/
    │   ├── copilot_interface.py            # ICopilotClient ABC + data models
    │   ├── copilot_client.py               # HTTP implementation
    │   └── copilot_grpc_client.py          # gRPC implementation
    ├── csharp/
    │   ├── ICopilotClient.cs               # ICopilotClient interface
    │   ├── CopilotClient.cs                # HTTP implementation
    │   └── CopilotGrpcClient.cs            # gRPC implementation
    └── typescript/
        ├── copilot-interface.ts            # ICopilotClient interface + types
        ├── copilot-client.ts               # HTTP implementation
        └── copilot-grpc-client.ts          # gRPC implementation
```

## Quick Start

## Extension Settings

You can configure the Copilot API Bridge extension in VS Code via the Settings UI or by editing your settings.json. The following options are available:

- `copilotBridge.port`: Port for the local HTTP API server (default: 3741)
- `copilotBridge.grpcPort`: Port for the local gRPC server (default: 3742)
- `copilotBridge.autoStart`: Automatically start the server when VS Code opens (default: true)
- `copilotBridge.apiKey`: Optional API key to protect the local server
- `copilotBridge.allowedOrigins`: Allowed origins for CORS (default: ["127.0.0.1", "localhost"])
- `copilotBridge.defaultModel`: Default model family (e.g. gpt-4o)
- `copilotBridge.defaultVendor`: Default model vendor (e.g. copilot)

To change these, open VS Code Settings and search for "Copilot Bridge" or add them to your `settings.json` file.


### 1. Install the Copilot Bridge Extension


#### Method 1: Command Line (Recommended)

1. Open a terminal and navigate to the `vscode-extension` folder:
  ```bash
  cd vscode-extension
  ```
2. Package the extension as a VSIX file (requires vsce):
  ```bash
  npm install -g vsce   # if not already installed
  vsce package
  ```
  This will create a file like `copilot-bridge-client-0.0.1.vsix`.
3. Install the extension using the VSIX file:
  ```bash
  code --install-extension copilot-bridge-client-0.0.1.vsix
  ```


#### Method 2: VS Code GUI (Development Mode)

1. Open the `vscode-extension` folder in VS Code.
2. Press `F5` to launch a new Extension Development Host with Copilot Bridge enabled.

#### Troubleshooting

- Make sure you have VS Code 1.95+ installed.
- Ensure the GitHub Copilot extension is installed and you are signed in.
- If you see connection errors, verify the extension is running and the server is started (see Commands below).

Once installed, the server will auto-start, or you can use the command palette (`Ctrl+Shift+P`) and run `Copilot Bridge: Start Server`.

### 2. (Optional) Enable gRPC

```bash
cd vscode-extension
npm install @grpc/grpc-js @grpc/proto-loader
```

### 3. The server auto-starts (or run command `Copilot Bridge: Start Server`)

### 4. Use from any language

**curl:**
```bash
# Check status
curl http://127.0.0.1:3741/status

# List available models
curl http://127.0.0.1:3741/models

# Chat
curl -X POST http://127.0.0.1:3741/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Explain Python decorators"}]}'

# Chat with specific model
curl -X POST http://127.0.0.1:3741/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}], "model": "gpt-4o-mini"}'
```

**Python (HTTP):**
```python
from copilot_client import CopilotClient

client = CopilotClient()
answer = client.chat("Explain Python decorators")
print(answer)

# Streaming
for chunk in client.chat_stream("Write a poem"):
    print(chunk, end="", flush=True)

# Choose model
answer = client.chat("Hello", model="claude-3.5-sonnet")
```

**Python (gRPC):**
```python
from copilot_grpc_client import CopilotGrpcClient

client = CopilotGrpcClient()
answer = client.chat("Explain Python decorators")
print(answer)
```

**Both implement the same interface:**
```python
from copilot_interface import ICopilotClient

def analyze(client: ICopilotClient):
    # Works with HTTP or gRPC!
    models = client.list_models()
    answer = client.chat("Hello", model=models[0].family)
    return answer
```

**C# (HTTP — implements ICopilotClient):**
```csharp
using CopilotBridge;

ICopilotClient client = new CopilotClient();   // HTTP
// ICopilotClient client = new CopilotGrpcClient(); // gRPC — same interface!

string answer = await client.ChatAsync("Explain LINQ");
Console.WriteLine(answer);

// Streaming
await foreach (var chunk in client.ChatStreamAsync("Write hello world"))
    Console.Write(chunk);

// One-liner
string result = await Copilot.AskAsync("What is a monad?");
```

**TypeScript (HTTP — implements ICopilotClient):**
```typescript
import { CopilotClient } from './copilot-client';
// import { CopilotGrpcClient } from './copilot-grpc-client'; // gRPC alternative

const client = new CopilotClient();
const answer = await client.chat("Explain generics");
console.log(answer);

// Streaming
for await (const chunk of client.chatStream("Write a poem")) {
    process.stdout.write(chunk);
}
```

## API Reference

### `GET /status`
Returns server status and configuration.

### `GET /models`
Lists all available Copilot language models.

Response:
```json
{
  "models": [
    { "id": "...", "name": "GPT-4o", "vendor": "copilot", "family": "gpt-4o", "maxInputTokens": 128000 }
  ]
}
```

### `POST /chat`
Send a chat request and receive the full response.

Request body:
```json
{
  "messages": [
    { "role": "user", "content": "Your prompt here" },
    { "role": "assistant", "content": "Previous assistant response" },
    { "role": "user", "content": "Follow-up question" }
  ],
  "model": "gpt-4o",
  "vendor": "copilot",
  "systemPrompt": "You are a helpful coding assistant"
}
```

Response:
```json
{
  "id": 1,
  "model": "copilot/gpt-4o",
  "content": "The response text...",
  "usage": { "promptTokens": null, "completionTokens": null }
}
```

### `POST /chat/stream`
Same request body as `/chat`, but returns Server-Sent Events (SSE):

```
data: {"content": "Hello"}
data: {"content": " world"}
data: {"done": true, "totalLength": 11}
```

## VS Code Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `copilotBridge.port` | `3741` | Port for the local HTTP server |
| `copilotBridge.grpcPort` | `3742` | Port for the local gRPC server |
| `copilotBridge.autoStart` | `true` | Auto-start server when VS Code opens |
| `copilotBridge.defaultModel` | `gpt-4o` | Default model family |
| `copilotBridge.defaultVendor` | `copilot` | Default model vendor |
| `copilotBridge.apiKey` | `""` | Optional API key to protect the server |
| `copilotBridge.allowedOrigins` | `["127.0.0.1", "localhost"]` | Allowed CORS origins |

## Commands

- **Copilot Bridge: Start Server** — Start the HTTP server
- **Copilot Bridge: Stop Server** — Stop the HTTP server
- **Copilot Bridge: Show Status** — Show current status

## Security

- The server binds to `127.0.0.1` only (not accessible from network)
- Optional API key authentication via `copilotBridge.apiKey` setting
- All requests pass through your locally authenticated GitHub Copilot session

## Requirements

- VS Code 1.95+
- GitHub Copilot extension installed and signed in
- (Optional for gRPC) `npm install @grpc/grpc-js @grpc/proto-loader` in the extension folder

## Testing

Run the integration tests (requires VS Code with the extension running):

```bash
# All tests (HTTP + gRPC)
python test.py

# HTTP only
python test.py --http-only

# gRPC only (requires generated stubs)
python test.py --grpc-only

# Custom ports
python test.py --base-url http://127.0.0.1:3741 --grpc-address 127.0.0.1:3742
```

To generate Python gRPC stubs:
```bash
pip install grpcio grpcio-tools
python -m grpc_tools.protoc -I proto --python_out=clients/python --grpc_python_out=clients/python proto/copilot_bridge.proto
```

## gRPC Proto File

The service is defined in `proto/copilot_bridge.proto`. Generate client stubs for any language:

```bash
# Python
python -m grpc_tools.protoc -I proto --python_out=clients/python --grpc_python_out=clients/python proto/copilot_bridge.proto

# C# (via dotnet-grpc or Grpc.Tools NuGet package)
# TypeScript (via @grpc/proto-loader — dynamic loading, no codegen needed)
```
