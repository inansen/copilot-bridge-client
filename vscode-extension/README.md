
# Copilot API Bridge (VS Code Extension)

Expose GitHub Copilot as a **local HTTP + gRPC API** via a VS Code extension. Call Copilot from any language (Python, C#, TypeScript, curl, etc.) by making HTTP or gRPC requests to your local machine.


## Architecture

```
┌──────────────┐  HTTP / gRPC ┌──────────────────┐  VS Code LM API  ┌──────────┐
│  Your Code   │ ───────────► │ Copilot Bridge    │ ───────────────► │ GitHub   │
│ (Python/C#/  │ ◄─────────── │ (VS Code ext)     │ ◄─────────────── │ Copilot  │
│  TS/curl)    │  JSON / SSE  │ HTTP :3741        │                  │          │
│              │  Protobuf    │ gRPC :3742        │                  │          │
└──────────────┘              └──────────────────┘                  └──────────┘
```


## Setup

### 1. Install Extension

```bash
cd vscode-extension
npm install -g vsce   # if not already installed
vsce package
code --install-extension copilot-api-bridge-1.0.0.vsix
```

Or for development:
1. Open VS Code in the `vscode-extension` folder
2. Press `F5` to launch Extension Development Host

### 2. (Optional) Enable gRPC

```bash
cd vscode-extension
npm install @grpc/grpc-js @grpc/proto-loader
```

### 3. Verify GitHub Copilot is Enabled

- Ensure GitHub Copilot extension is installed
- Check you're signed in with a valid Copilot subscription


## Configuration

You can configure the extension in VS Code settings (UI or settings.json):

- `copilotBridge.port`: Port for the local HTTP API server (default: 3741)
- `copilotBridge.grpcPort`: Port for the local gRPC server (default: 3742)
- `copilotBridge.autoStart`: Automatically start the server when VS Code opens
- `copilotBridge.apiKey`: Optional API key to protect the local server
- `copilotBridge.allowedOrigins`: Allowed origins for CORS
- `copilotBridge.defaultModel`: Default model family (e.g. gpt-4o)
- `copilotBridge.defaultVendor`: Default model vendor (e.g. copilot)

## Usage

Once installed and running, you can call the API from any language. See the main project README for code examples in Python, C#, TypeScript, and curl.

### Commands

- **Copilot Bridge: Start Server** — Start the HTTP/gRPC server
- **Copilot Bridge: Stop Server** — Stop the server
- **Copilot Bridge: Show Status** — Show current status and ports

### Logs

All logs and server info are available in the "Copilot Bridge" output channel in VS Code.

2. **Run extension manually:**
   - Press `Ctrl+Shift+P`
   - Type: `GDPR: Analyze Pages`
   - Press Enter
   - Wait for completion notification

3. **Process results:**
   ```powershell
   python use-vscode-ai.py  # Will continue from results
   ```

## File Flow

```
page-tree.json (input)
    ↓
agents/ai-input.json (prompts for extension)
    ↓
[VS Code Extension processes with Copilot]
    ↓
agents/ai-output.json (raw Copilot responses)
    ↓
agents/ai-findings.json (formatted for migration)
    ↓
sanitize-and-migrate.py (uses findings)
```

## Extension Development

### Testing the Extension

1. Open workspace in VS Code
2. Open `vscode-extension/extension.js`
3. Press `F5` to launch Extension Development Host
4. In new window: `Ctrl+Shift+P` → `GDPR: Analyze Pages`

### Debugging

- Extension logs appear in Debug Console (F5 window)
- Check VS Code Output panel → "GDPR AI Analyzer"
- Inspect `agents/ai-output.json` for raw responses

## Troubleshooting

**"No Copilot models available"**
- Ensure GitHub Copilot extension is installed and active
- Sign in to GitHub with Copilot subscription
- Reload VS Code

**"Extension command not found"**
- Extension not loaded: Press `F5` to load in dev mode
- Or install extension: `code --install-extension vscode-extension/`

**"ai-output.json not created"**
- Extension may still be running (check notifications)
- Check Debug Console for errors
- Manually verify `agents/ai-input.json` exists

**"Invalid JSON from Copilot"**
- Copilot may return markdown-wrapped JSON
- Extension should handle this, but check raw output
- Retry the analysis

## Benefits vs Other Approaches

✅ **No API keys needed** - Uses your Copilot subscription  
✅ **Free** - Already paying for Copilot  
✅ **Fully automated** - No copy/paste required  
✅ **Same model** - Uses GitHub Copilot's GPT-4  
✅ **Integrated** - Runs directly in VS Code  

❌ **Requires VS Code** - Can't run headless  
❌ **Dev mode** - Extension needs to be loaded  

## Alternative: Use OpenAI Directly

If you prefer fully automated without VS Code dependency:

```powershell
# Add to .env
OPENAI_API_KEY=sk-your-key-here

# Then just run
python sanitize-and-migrate.py
```

The script auto-detects OpenAI key and uses API instead.
