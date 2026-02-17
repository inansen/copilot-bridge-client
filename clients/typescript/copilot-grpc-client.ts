/**
 * Copilot Bridge — TypeScript gRPC Client
 * Implements ICopilotClient over gRPC transport.
 *
 * Requires:
 *   npm install @grpc/grpc-js @grpc/proto-loader
 *
 * Usage:
 *   import { CopilotGrpcClient } from './copilot-grpc-client';
 *
 *   const client = new CopilotGrpcClient();
 *   const answer = await client.chat("Explain generics");
 *
 *   for await (const chunk of client.chatStream("Write a poem")) {
 *     process.stdout.write(chunk);
 *   }
 */

import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import * as path from 'path';
import type { ICopilotClient, ChatMessage, ChatOptions, ChatResponse, ModelInfo, StatusResponse } from './copilot-interface';

// ── Load Proto ──────────────────────────────────────────────────────────────

const PROTO_PATH = path.resolve(__dirname, '..', '..', 'proto', 'copilot_bridge.proto');

const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
    keepCase: false,
    longs: String,
    enums: String,
    defaults: true,
    oneofs: true,
});

const proto = grpc.loadPackageDefinition(packageDefinition).copilot_bridge as any;

// ── Client Class ────────────────────────────────────────────────────────────

export class CopilotGrpcClient implements ICopilotClient {
    private client: any;
    private defaultModel?: string;
    private defaultVendor?: string;

    constructor(options?: {
        address?: string;
        defaultModel?: string;
        defaultVendor?: string;
    }) {
        const address = options?.address ?? '127.0.0.1:3742';
        this.defaultModel = options?.defaultModel;
        this.defaultVendor = options?.defaultVendor;
        this.client = new proto.CopilotBridgeService(address, grpc.credentials.createInsecure());
    }

    close(): void {
        this.client.close();
    }

    // ── ICopilotClient ──────────────────────────────────────────────────

    async status(): Promise<StatusResponse> {
        return this.unaryCall('getStatus', {});
    }

    async listModels(): Promise<ModelInfo[]> {
        const reply = await this.unaryCall('listModels', {});
        return reply.models ?? [];
    }

    async chat(messages: string | ChatMessage[], options?: ChatOptions): Promise<string> {
        const req = this.buildRequest(messages, options);
        const reply = await this.unaryCall('chat', req);
        return reply.content ?? '';
    }

    async chatFull(messages: string | ChatMessage[], options?: ChatOptions): Promise<ChatResponse> {
        const req = this.buildRequest(messages, options);
        return this.unaryCall('chat', req);
    }

    async *chatStream(messages: string | ChatMessage[], options?: ChatOptions): AsyncGenerator<string> {
        const req = this.buildRequest(messages, options);
        const stream = this.client.chatStream(req);

        for await (const chunk of stream) {
            if (chunk.error) throw new Error(chunk.error);
            if (chunk.done) return;
            if (chunk.content) yield chunk.content;
        }
    }

    async chatJson<T = unknown>(messages: string | ChatMessage[], options?: ChatOptions): Promise<T> {
        const text = await this.chat(messages, options);
        try {
            return JSON.parse(text);
        } catch {
            const fenceMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/);
            if (fenceMatch) return JSON.parse(fenceMatch[1].trim());
            const braceMatch = text.match(/\{[\s\S]*\}/);
            if (braceMatch) return JSON.parse(braceMatch[0]);
            throw new Error(`Could not parse JSON from response: ${text.slice(0, 500)}`);
        }
    }

    // ── Internals ───────────────────────────────────────────────────────

    private buildRequest(messages: string | ChatMessage[], options?: ChatOptions): Record<string, unknown> {
        const msgs = typeof messages === 'string'
            ? [{ role: 'user', content: messages }]
            : messages;
        return {
            messages: msgs,
            model: options?.model ?? this.defaultModel ?? '',
            vendor: options?.vendor ?? this.defaultVendor ?? '',
            systemPrompt: options?.systemPrompt ?? '',
        };
    }

    private unaryCall(method: string, request: any): Promise<any> {
        return new Promise((resolve, reject) => {
            this.client[method](request, (err: grpc.ServiceError | null, response: any) => {
                if (err) reject(err);
                else resolve(response);
            });
        });
    }
}
