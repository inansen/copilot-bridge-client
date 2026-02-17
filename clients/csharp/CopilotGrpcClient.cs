// Copilot Bridge — C# gRPC Client
// Implements ICopilotClient over gRPC transport.
//
// Requires NuGet packages:
//   Grpc.Net.Client
//   Google.Protobuf
//   Grpc.Tools (for codegen from .proto)
//
// Usage:
//   using var client = new CopilotGrpcClient();
//   string answer = await client.ChatAsync("Explain LINQ");
//
//   await foreach (var chunk in client.ChatStreamAsync("Write hello world"))
//       Console.Write(chunk);

using System.Runtime.CompilerServices;
using Grpc.Core;
using Grpc.Net.Client;
using CopilotBridge.Grpc;

namespace CopilotBridge;

public class CopilotGrpcClient : ICopilotClient
{
    private readonly GrpcChannel _channel;
    private readonly CopilotBridgeService.CopilotBridgeServiceClient _client;

    public CopilotGrpcClient(string address = "http://127.0.0.1:3742")
    {
        _channel = GrpcChannel.ForAddress(address);
        _client = new CopilotBridgeService.CopilotBridgeServiceClient(_channel);
    }

    public async Task<StatusResponse> GetStatusAsync(CancellationToken ct = default)
    {
        var reply = await _client.GetStatusAsync(new StatusRequest(), cancellationToken: ct);
        return new StatusResponse
        {
            Status = reply.Status,
            Port = reply.Port,
            DefaultModel = reply.DefaultModel,
            RequestsServed = reply.RequestsServed,
            Version = reply.Version,
        };
    }

    public async Task<List<ModelInfo>> ListModelsAsync(CancellationToken ct = default)
    {
        var reply = await _client.ListModelsAsync(new ListModelsRequest(), cancellationToken: ct);
        return reply.Models.Select(m => new ModelInfo
        {
            Id = m.Id,
            Name = m.Name,
            Vendor = m.Vendor,
            Family = m.Family,
            Version = m.Version,
            MaxInputTokens = m.MaxInputTokens,
        }).ToList();
    }

    public Task<string> ChatAsync(string prompt, string? model = null, string? vendor = null,
        string? systemPrompt = null, CancellationToken ct = default)
        => ChatAsync(new[] { new ChatMessage("user", prompt) },
            new ChatOptions { Model = model, Vendor = vendor, SystemPrompt = systemPrompt }, ct);

    public async Task<string> ChatAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken ct = default)
    {
        var reply = await _client.ChatAsync(BuildRequest(messages, options), cancellationToken: ct);
        return reply.Content;
    }

    public async Task<ChatResponse> ChatFullAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken ct = default)
    {
        var reply = await _client.ChatAsync(BuildRequest(messages, options), cancellationToken: ct);
        return new ChatResponse { Id = reply.Id, Model = reply.Model, Content = reply.Content };
    }

    public async IAsyncEnumerable<string> ChatStreamAsync(string prompt, string? model = null,
        string? vendor = null, string? systemPrompt = null,
        [EnumeratorCancellation] CancellationToken ct = default)
    {
        await foreach (var chunk in ChatStreamAsync(
            new[] { new ChatMessage("user", prompt) },
            new ChatOptions { Model = model, Vendor = vendor, SystemPrompt = systemPrompt }, ct))
            yield return chunk;
    }

    public async IAsyncEnumerable<string> ChatStreamAsync(IEnumerable<ChatMessage> messages,
        ChatOptions? options = null, [EnumeratorCancellation] CancellationToken ct = default)
    {
        var call = _client.ChatStream(BuildRequest(messages, options), cancellationToken: ct);
        await foreach (var chunk in call.ResponseStream.ReadAllAsync(ct))
        {
            if (!string.IsNullOrEmpty(chunk.Error))
                throw new CopilotClientException(chunk.Error);
            if (chunk.Done) yield break;
            if (!string.IsNullOrEmpty(chunk.Content))
                yield return chunk.Content;
        }
    }

    public async Task<T> ChatJsonAsync<T>(string prompt, string? model = null, string? systemPrompt = null,
        CancellationToken ct = default)
    {
        var text = await ChatAsync(prompt, model: model, systemPrompt: systemPrompt, ct: ct);
        return System.Text.Json.JsonSerializer.Deserialize<T>(text)!;
    }

    private static Grpc.ChatRequest BuildRequest(IEnumerable<ChatMessage> messages, ChatOptions? options)
    {
        var req = new Grpc.ChatRequest
        {
            Model = options?.Model ?? "",
            Vendor = options?.Vendor ?? "",
            SystemPrompt = options?.SystemPrompt ?? "",
        };
        foreach (var m in messages)
            req.Messages.Add(new Grpc.ChatMessage { Role = m.Role, Content = m.Content });
        return req;
    }

    public void Dispose() => _channel.Dispose();
}
