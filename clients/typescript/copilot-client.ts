/**
 * Copilot Bridge Client for TypeScript / Node.js (HTTP transport)
 * Connects to the VS Code Copilot API Bridge extension via HTTP.
 *
 * Usage:
 *   import { CopilotClient, askCopilot } from './copilot-client';
 *
 *   const client = new CopilotClient();
 *   const answer = await client.chat("Explain TypeScript generics");
 *
 *   // Streaming
 *   for await (const chunk of client.chatStream("Write hello world")) {
 *     process.stdout.write(chunk);
 *   }
 *
 *   // One-liner
 *   const result = await askCopilot("What is a closure?");
 */

import type { ICopilotClient, ChatMessage, ChatOptions, ChatResponse, ModelInfo, StatusResponse } from './copilot-interface';
export type { ICopilotClient, ChatMessage, ChatOptions, ChatResponse, ModelInfo, StatusResponse };

// ── Client Class ─────────────────────────────────────────────────────────────

export class CopilotClient implements ICopilotClient {
    private baseUrl: string;
    private apiKey?: string;
    private defaultModel?: string;
    private defaultVendor?: string;

    constructor(options?: {
        baseUrl?: string;
        apiKey?: string;
        defaultModel?: string;
        defaultVendor?: string;
    }) {
        this.baseUrl = (options?.baseUrl ?? 'http://127.0.0.1:3741').replace(/\/$/, '');
        this.apiKey = options?.apiKey;
        this.defaultModel = options?.defaultModel;
        this.defaultVendor = options?.defaultVendor;
    }

    // ── Public API ───────────────────────────────────────────────────────

    async status(): Promise<StatusResponse> {
        return this.get('/status');
    }

    async listModels(): Promise<ModelInfo[]> {
        const data = await this.get('/models');
        return data.models ?? [];
    }

    /**
     * Send a chat request and get the full response.
     * @param messages - A string prompt or array of ChatMessage objects.
     * @param options - Model, vendor, and system prompt overrides.
     */
    async chat(messages: string | ChatMessage[], options?: ChatOptions): Promise<string> {
        const payload = this.buildPayload(messages, options);
        const data: ChatResponse = await this.post('/chat', payload);
        return data.content ?? '';
    }

    /**
     * Send a chat request and get the full structured response.
     */
    async chatFull(messages: string | ChatMessage[], options?: ChatOptions): Promise<ChatResponse> {
        const payload = this.buildPayload(messages, options);
        return this.post('/chat', payload);
    }

    /**
     * Stream a chat response via SSE. Yields content fragments.
     */
    async *chatStream(messages: string | ChatMessage[], options?: ChatOptions): AsyncGenerator<string> {
        const payload = this.buildPayload(messages, options);
        const url = `${this.baseUrl}/chat/stream`;

        const response = await fetch(url, {
            method: 'POST',
            headers: this.headers(),
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const text = await response.text();
            throw new Error(`HTTP ${response.status}: ${text}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            while (buffer.includes('\n\n')) {
                const idx = buffer.indexOf('\n\n');
                const event = buffer.slice(0, idx);
                buffer = buffer.slice(idx + 2);

                for (const line of event.split('\n')) {
                    if (line.startsWith('data: ')) {
                        const eventData = JSON.parse(line.slice(6));
                        if (eventData.done) return;
                        if (eventData.error) throw new Error(eventData.error);
                        if (eventData.content) yield eventData.content;
                    }
                }
            }
        }
    }

    /**
     * Send a chat request and parse the response as JSON.
     */
    async chatJson<T = unknown>(messages: string | ChatMessage[], options?: ChatOptions): Promise<T> {
        const text = await this.chat(messages, options);
        try {
            return JSON.parse(text);
        } catch {
            // Try extracting from code fences
            const fenceMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/);
            if (fenceMatch) return JSON.parse(fenceMatch[1].trim());
            const braceMatch = text.match(/\{[\s\S]*\}/);
            if (braceMatch) return JSON.parse(braceMatch[0]);
            throw new Error(`Could not parse JSON from response: ${text.slice(0, 500)}`);
        }
    }

    // ── Internals ────────────────────────────────────────────────────────

    private buildPayload(messages: string | ChatMessage[], options?: ChatOptions): Record<string, unknown> {
        const msgs = typeof messages === 'string'
            ? [{ role: 'user', content: messages }]
            : messages;

        const payload: Record<string, unknown> = { messages: msgs };

        const model = options?.model ?? this.defaultModel;
        const vendor = options?.vendor ?? this.defaultVendor;
        if (model) payload.model = model;
        if (vendor) payload.vendor = vendor;
        if (options?.systemPrompt) payload.systemPrompt = options.systemPrompt;

        return payload;
    }

    private headers(): Record<string, string> {
        const h: Record<string, string> = { 'Content-Type': 'application/json' };
        if (this.apiKey) h['Authorization'] = `Bearer ${this.apiKey}`;
        return h;
    }

    private async get(path: string): Promise<any> {
        const response = await fetch(`${this.baseUrl}${path}`, {
            method: 'GET',
            headers: this.headers(),
        });
        if (!response.ok) {
            const text = await response.text();
            throw new Error(`HTTP ${response.status}: ${text}`);
        }
        return response.json();
    }

    private async post(path: string, payload: Record<string, unknown>): Promise<any> {
        const response = await fetch(`${this.baseUrl}${path}`, {
            method: 'POST',
            headers: this.headers(),
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const text = await response.text();
            throw new Error(`HTTP ${response.status}: ${text}`);
        }
        return response.json();
    }
}

// ── Convenience function ─────────────────────────────────────────────────────

let _defaultClient: CopilotClient | null = null;

/**
 * One-liner to ask Copilot a question.
 *
 *   const answer = await askCopilot("What is a monad?");
 */
export async function askCopilot(
    prompt: string,
    options?: ChatOptions & { baseUrl?: string },
): Promise<string> {
    if (!_defaultClient || (options?.baseUrl && options.baseUrl !== 'http://127.0.0.1:3741')) {
        _defaultClient = new CopilotClient({ baseUrl: options?.baseUrl });
    }
    return _defaultClient.chat(prompt, options);
}
