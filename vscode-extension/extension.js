/**
 * Copilot API Bridge
 * Local HTTP + gRPC server that proxies requests to GitHub Copilot via VS Code Language Model API.
 * Use from any language: Python, C#, TypeScript, curl, etc.
 */

const vscode = require('vscode');
const http = require('http');
const path = require('path');

// gRPC modules — loaded lazily so extension still works without them
let grpc, protoLoader;
try {
    grpc = require('@grpc/grpc-js');
    protoLoader = require('@grpc/proto-loader');
} catch (_) {
    // gRPC dependencies not installed — gRPC server will be disabled
}

let outputChannel;
let server = null;         // HTTP server
let grpcServer = null;     // gRPC server
let serverPort = 3741;
let grpcPort = 3742;
let requestCounter = 0;

// ─── Activation ───────────────────────────────────────────────────────────────

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('Copilot Bridge');
    log('Copilot API Bridge extension activated');

    context.subscriptions.push(
        vscode.commands.registerCommand('copilot-bridge.start', () => startServer()),
        vscode.commands.registerCommand('copilot-bridge.stop', () => stopServer()),
        vscode.commands.registerCommand('copilot-bridge.status', () => showStatus()),
    );

    // Auto-start if configured
    const config = vscode.workspace.getConfiguration('copilotBridge');
    if (config.get('autoStart', true)) {
        startServer();
    }

    // React to config changes
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('copilotBridge')) {
                log('Configuration changed — restart server to apply.');
            }
        })
    );
}

function deactivate() {
    stopServer();
    stopGrpcServer();
}

// ─── Logging ──────────────────────────────────────────────────────────────────

function log(message) {
    const ts = new Date().toISOString();
    outputChannel.appendLine(`[${ts}] ${message}`);
}

// ─── HTTP Server ──────────────────────────────────────────────────────────────

function getConfig() {
    const cfg = vscode.workspace.getConfiguration('copilotBridge');
    return {
        port: cfg.get('port', 3741),
        grpcPort: cfg.get('grpcPort', 3742),
        defaultModel: cfg.get('defaultModel', 'gpt-4o'),
        defaultVendor: cfg.get('defaultVendor', 'copilot'),
        apiKey: cfg.get('apiKey', ''),
        allowedOrigins: cfg.get('allowedOrigins', ['127.0.0.1', 'localhost']),
    };
}

async function startServer() {
    if (server) {
        vscode.window.showInformationMessage(`Copilot Bridge already running on port ${serverPort}`);
        return;
    }

    const config = getConfig();
    serverPort = config.port;
    grpcPort = config.grpcPort;

    server = http.createServer((req, res) => {
        handleRequest(req, res, config).catch(err => {
            log(`Unhandled error: ${err.message}`);
            sendJson(res, 500, { error: 'Internal server error', message: err.message });
        });
    });

    return new Promise((resolve, reject) => {
        server.listen(serverPort, '127.0.0.1', () => {
            let msg = `Copilot Bridge HTTP running on http://127.0.0.1:${serverPort}`;
            log(`HTTP server started on http://127.0.0.1:${serverPort}`);

            // Start gRPC server alongside
            startGrpcServer(config).then(() => {
                msg += ` | gRPC on 127.0.0.1:${grpcPort}`;
            }).catch(err => {
                log(`gRPC server skipped: ${err.message}`);
            }).finally(() => {
                vscode.window.showInformationMessage(msg);
                outputChannel.show(true);
                resolve();
            });
        });
        server.on('error', (err) => {
            log(`HTTP server error: ${err.message}`);
            vscode.window.showErrorMessage(`Copilot Bridge failed to start: ${err.message}`);
            server = null;
            reject(err);
        });
    });
}

function stopServer() {
    if (!server) {
        vscode.window.showInformationMessage('Copilot Bridge is not running');
        return;
    }
    server.close(() => {
        log('HTTP server stopped');
    });
    server = null;
    stopGrpcServer();
    vscode.window.showInformationMessage('Copilot Bridge stopped');
}

function showStatus() {
    const config = getConfig();
    if (server) {
        const grpcStatus = grpcServer ? ` | gRPC on :${grpcPort}` : '';
        vscode.window.showInformationMessage(
            `Copilot Bridge: RUNNING on :${serverPort}${grpcStatus} | model: ${config.defaultVendor}/${config.defaultModel} | requests: ${requestCounter}`
        );
    } else {
        vscode.window.showInformationMessage('Copilot Bridge: STOPPED');
    }
}

// ─── gRPC Server ──────────────────────────────────────────────────────────────

async function startGrpcServer(config) {
    if (!grpc || !protoLoader) {
        throw new Error('@grpc/grpc-js or @grpc/proto-loader not installed — run: npm install @grpc/grpc-js @grpc/proto-loader');
    }
    if (grpcServer) return;

    // Load proto from the project root's proto/ folder, or bundled alongside
    const protoPath = findProtoFile();
    const packageDefinition = protoLoader.loadSync(protoPath, {
        keepCase: false,
        longs: String,
        enums: String,
        defaults: true,
        oneofs: true,
    });
    const proto = grpc.loadPackageDefinition(packageDefinition).copilot_bridge;

    grpcServer = new grpc.Server();
    grpcServer.addService(proto.CopilotBridgeService.service, {
        getStatus: grpcGetStatus(config),
        listModels: grpcListModels(),
        chat: grpcChat(config),
        chatStream: grpcChatStream(config),
    });

    return new Promise((resolve, reject) => {
        grpcServer.bindAsync(
            `127.0.0.1:${grpcPort}`,
            grpc.ServerCredentials.createInsecure(),
            (err, port) => {
                if (err) {
                    grpcServer = null;
                    reject(err);
                    return;
                }
                log(`gRPC server started on 127.0.0.1:${port}`);
                resolve();
            }
        );
    });
}

function stopGrpcServer() {
    if (!grpcServer) return;
    grpcServer.forceShutdown();
    grpcServer = null;
    log('gRPC server stopped');
}

function findProtoFile() {
    // Try several locations
    const candidates = [
        path.join(__dirname, '..', 'proto', 'copilot_bridge.proto'),
        path.join(__dirname, 'proto', 'copilot_bridge.proto'),
    ];
    const fs = require('fs');
    for (const p of candidates) {
        if (fs.existsSync(p)) return p;
    }
    throw new Error(`copilot_bridge.proto not found. Looked in: ${candidates.join(', ')}`);
}

// gRPC handlers

function grpcGetStatus(config) {
    return (_call, callback) => {
        callback(null, {
            status: 'running',
            port: serverPort,
            defaultModel: `${config.defaultVendor}/${config.defaultModel}`,
            requestsServed: requestCounter,
            version: '1.0.0',
        });
    };
}

function grpcListModels() {
    return async (_call, callback) => {
        try {
            const models = await vscode.lm.selectChatModels();
            const list = models.map(m => ({
                id: m.id,
                name: m.name,
                vendor: m.vendor,
                family: m.family,
                version: m.version,
                maxInputTokens: m.maxInputTokens,
            }));
            callback(null, { models: list });
        } catch (err) {
            callback({ code: grpc.status.INTERNAL, message: err.message });
        }
    };
}

function grpcChat(config) {
    return async (call, callback) => {
        const req = call.request;
        const messages = req.messages || [];
        if (messages.length === 0) {
            callback({ code: grpc.status.INVALID_ARGUMENT, message: 'messages is required' });
            return;
        }

        requestCounter++;
        const reqId = requestCounter;
        const family = req.model || config.defaultModel;
        const vnd = req.vendor || config.defaultVendor;

        log(`[#${reqId}] gRPC Chat — ${vnd}/${family} — ${messages.length} msg(s)`);

        try {
            const lmModel = await resolveModel(vnd, family);
            const chatMessages = buildMessages(req.systemPrompt, messages);
            const cts = new vscode.CancellationTokenSource();
            const chatResponse = await lmModel.sendRequest(chatMessages, {}, cts.token);

            let responseText = '';
            for await (const fragment of chatResponse.text) {
                responseText += fragment;
            }

            log(`[#${reqId}] gRPC response (${responseText.length} chars)`);
            callback(null, { id: reqId, model: `${vnd}/${family}`, content: responseText });
        } catch (err) {
            log(`[#${reqId}] gRPC error: ${err.message}`);
            callback({ code: grpc.status.INTERNAL, message: err.message });
        }
    };
}

function grpcChatStream(config) {
    return async (call) => {
        const req = call.request;
        const messages = req.messages || [];
        if (messages.length === 0) {
            call.emit('error', { code: grpc.status.INVALID_ARGUMENT, message: 'messages is required' });
            call.end();
            return;
        }

        requestCounter++;
        const reqId = requestCounter;
        const family = req.model || config.defaultModel;
        const vnd = req.vendor || config.defaultVendor;

        log(`[#${reqId}] gRPC Stream — ${vnd}/${family} — ${messages.length} msg(s)`);

        try {
            const lmModel = await resolveModel(vnd, family);
            const chatMessages = buildMessages(req.systemPrompt, messages);
            const cts = new vscode.CancellationTokenSource();
            const chatResponse = await lmModel.sendRequest(chatMessages, {}, cts.token);

            let totalLength = 0;
            for await (const fragment of chatResponse.text) {
                totalLength += fragment.length;
                call.write({ content: fragment, done: false, error: '', totalLength: 0 });
            }

            call.write({ content: '', done: true, error: '', totalLength });
            call.end();

            log(`[#${reqId}] gRPC stream complete (${totalLength} chars)`);
        } catch (err) {
            log(`[#${reqId}] gRPC stream error: ${err.message}`);
            call.write({ content: '', done: true, error: err.message, totalLength: 0 });
            call.end();
        }
    };
}

// ─── Request Router ───────────────────────────────────────────────────────────

async function handleRequest(req, res, config) {
    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

    if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
    }

    // Auth check
    if (config.apiKey) {
        const auth = req.headers['authorization'];
        if (auth !== `Bearer ${config.apiKey}`) {
            sendJson(res, 401, { error: 'Unauthorized' });
            return;
        }
    }

    const url = new URL(req.url, `http://${req.headers.host}`);
    const pathname = url.pathname;

    try {
        if (pathname === '/status' && req.method === 'GET') {
            await handleStatus(req, res, config);
        } else if (pathname === '/models' && req.method === 'GET') {
            await handleListModels(req, res);
        } else if (pathname === '/chat' && req.method === 'POST') {
            await handleChat(req, res, config);
        } else if (pathname === '/chat/stream' && req.method === 'POST') {
            await handleChatStream(req, res, config);
        } else {
            sendJson(res, 404, {
                error: 'Not found',
                endpoints: {
                    'GET /status': 'Server status',
                    'GET /models': 'List available models',
                    'POST /chat': 'Send chat request (full response)',
                    'POST /chat/stream': 'Send chat request (SSE stream)',
                },
            });
        }
    } catch (err) {
        log(`Error handling ${req.method} ${pathname}: ${err.message}`);
        sendJson(res, 500, { error: err.message });
    }
}

// ─── Endpoint: GET /status ────────────────────────────────────────────────────

async function handleStatus(_req, res, config) {
    sendJson(res, 200, {
        status: 'running',
        port: serverPort,
        defaultModel: `${config.defaultVendor}/${config.defaultModel}`,
        requestsServed: requestCounter,
        version: '1.0.0',
    });
}

// ─── Endpoint: GET /models ────────────────────────────────────────────────────

async function handleListModels(_req, res) {
    try {
        const models = await vscode.lm.selectChatModels();
        const list = models.map(m => ({
            id: m.id,
            name: m.name,
            vendor: m.vendor,
            family: m.family,
            version: m.version,
            maxInputTokens: m.maxInputTokens,
        }));
        sendJson(res, 200, { models: list });
    } catch (err) {
        sendJson(res, 500, { error: 'Failed to list models', message: err.message });
    }
}

// ─── Endpoint: POST /chat ─────────────────────────────────────────────────────

async function handleChat(req, res, config) {
    const body = await readBody(req);
    const { messages, model: modelFamily, vendor, systemPrompt } = body;

    if (!messages || !Array.isArray(messages) || messages.length === 0) {
        sendJson(res, 400, { error: 'messages is required and must be a non-empty array' });
        return;
    }

    requestCounter++;
    const reqId = requestCounter;
    const family = modelFamily || config.defaultModel;
    const vnd = vendor || config.defaultVendor;

    log(`[#${reqId}] Chat request — ${vnd}/${family} — ${messages.length} message(s)`);

    try {
        const lmModel = await resolveModel(vnd, family);
        const chatMessages = buildMessages(systemPrompt, messages);
        const cts = new vscode.CancellationTokenSource();

        const chatResponse = await lmModel.sendRequest(chatMessages, {}, cts.token);

        let responseText = '';
        for await (const fragment of chatResponse.text) {
            responseText += fragment;
        }

        log(`[#${reqId}] Response received (${responseText.length} chars)`);

        sendJson(res, 200, {
            id: reqId,
            model: `${vnd}/${family}`,
            content: responseText,
            usage: {
                // VS Code LM API doesn't expose token counts yet
                promptTokens: null,
                completionTokens: null,
            },
        });
    } catch (err) {
        log(`[#${reqId}] Error: ${err.message}`);
        sendJson(res, 500, { error: err.message, id: reqId });
    }
}

// ─── Endpoint: POST /chat/stream ──────────────────────────────────────────────

async function handleChatStream(req, res, config) {
    const body = await readBody(req);
    const { messages, model: modelFamily, vendor, systemPrompt } = body;

    if (!messages || !Array.isArray(messages) || messages.length === 0) {
        sendJson(res, 400, { error: 'messages is required and must be a non-empty array' });
        return;
    }

    requestCounter++;
    const reqId = requestCounter;
    const family = modelFamily || config.defaultModel;
    const vnd = vendor || config.defaultVendor;

    log(`[#${reqId}] Stream request — ${vnd}/${family} — ${messages.length} message(s)`);

    try {
        const lmModel = await resolveModel(vnd, family);
        const chatMessages = buildMessages(systemPrompt, messages);
        const cts = new vscode.CancellationTokenSource();

        const chatResponse = await lmModel.sendRequest(chatMessages, {}, cts.token);

        // SSE headers
        res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
        });

        let totalLength = 0;
        for await (const fragment of chatResponse.text) {
            totalLength += fragment.length;
            res.write(`data: ${JSON.stringify({ content: fragment })}\n\n`);
        }

        res.write(`data: ${JSON.stringify({ done: true, totalLength })}\n\n`);
        res.end();

        log(`[#${reqId}] Stream complete (${totalLength} chars)`);
    } catch (err) {
        log(`[#${reqId}] Stream error: ${err.message}`);
        // If headers not sent yet, send JSON error
        if (!res.headersSent) {
            sendJson(res, 500, { error: err.message, id: reqId });
        } else {
            res.write(`data: ${JSON.stringify({ error: err.message })}\n\n`);
            res.end();
        }
    }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function resolveModel(vendor, family) {
    const models = await vscode.lm.selectChatModels({ vendor, family });
    if (models.length === 0) {
        // Fallback: try without family filter
        const allModels = await vscode.lm.selectChatModels({ vendor });
        if (allModels.length === 0) {
            throw new Error(`No models found for vendor="${vendor}". Is GitHub Copilot signed in?`);
        }
        // Try partial match on family
        const match = allModels.find(m => m.family && m.family.includes(family));
        if (match) return match;
        throw new Error(
            `Model "${vendor}/${family}" not found. Available: ${allModels.map(m => m.family).join(', ')}`
        );
    }
    return models[0];
}

function buildMessages(systemPrompt, messages) {
    const chatMessages = [];

    if (systemPrompt) {
        chatMessages.push(vscode.LanguageModelChatMessage.User(`[System Instruction]\n${systemPrompt}`));
    }

    for (const msg of messages) {
        const role = (msg.role || 'user').toLowerCase();
        const content = msg.content || '';
        if (role === 'user' || role === 'human') {
            chatMessages.push(vscode.LanguageModelChatMessage.User(content));
        } else if (role === 'assistant' || role === 'ai') {
            chatMessages.push(vscode.LanguageModelChatMessage.Assistant(content));
        } else {
            // Default to user
            chatMessages.push(vscode.LanguageModelChatMessage.User(content));
        }
    }

    return chatMessages;
}

function readBody(req) {
    return new Promise((resolve, reject) => {
        let data = '';
        req.on('data', chunk => { data += chunk; });
        req.on('end', () => {
            try {
                resolve(data ? JSON.parse(data) : {});
            } catch (e) {
                reject(new Error('Invalid JSON body'));
            }
        });
        req.on('error', reject);
    });
}

function sendJson(res, statusCode, data) {
    const body = JSON.stringify(data, null, 2);
    res.writeHead(statusCode, {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
    });
    res.end(body);
}

// ─── Exports ──────────────────────────────────────────────────────────────────

module.exports = { activate, deactivate };
