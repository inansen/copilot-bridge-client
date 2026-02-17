/**
 * Copilot Bridge — TypeScript Interface
 * All transport implementations (HTTP, gRPC) implement this interface.
 */

// ── Data Models ─────────────────────────────────────────────────────────────

export interface ChatMessage {
    role: 'user' | 'assistant' | 'system';
    content: string;
}

export interface ChatOptions {
    model?: string;
    vendor?: string;
    systemPrompt?: string;
}

export interface ModelInfo {
    id: string;
    name: string;
    vendor: string;
    family: string;
    version: string;
    maxInputTokens: number;
}

export interface StatusResponse {
    status: string;
    port: number;
    defaultModel: string;
    requestsServed: number;
    version: string;
}

export interface ChatResponse {
    id: number;
    model: string;
    content: string;
    usage?: { promptTokens: number | null; completionTokens: number | null };
}

// ── Interface ───────────────────────────────────────────────────────────────

/**
 * Abstract interface for the Copilot Bridge client.
 * Implement for different transports (HTTP, gRPC, etc.)
 */
export interface ICopilotClient {
    /** Get server status. */
    status(): Promise<StatusResponse>;

    /** List available Copilot models. */
    listModels(): Promise<ModelInfo[]>;

    /** Send a chat request and get the full response text. */
    chat(messages: string | ChatMessage[], options?: ChatOptions): Promise<string>;

    /** Send a chat request and get the full structured response. */
    chatFull(messages: string | ChatMessage[], options?: ChatOptions): Promise<ChatResponse>;

    /** Stream a chat response via SSE/gRPC. Yields content fragments. */
    chatStream(messages: string | ChatMessage[], options?: ChatOptions): AsyncGenerator<string>;

    /** Send a chat and parse response as JSON. */
    chatJson<T = unknown>(messages: string | ChatMessage[], options?: ChatOptions): Promise<T>;
}
