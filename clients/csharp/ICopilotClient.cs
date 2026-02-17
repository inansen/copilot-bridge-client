// Copilot Bridge — C# Interface
// All transport implementations (HTTP, gRPC) implement this interface.

namespace CopilotBridge;

/// <summary>
/// Abstract interface for communicating with the Copilot Bridge server.
/// Implement this interface for different transports (HTTP, gRPC, etc.)
/// </summary>
public interface ICopilotClient : IDisposable
{
    /// <summary>Get server status.</summary>
    Task<StatusResponse> GetStatusAsync(CancellationToken ct = default);

    /// <summary>List available Copilot models.</summary>
    Task<List<ModelInfo>> ListModelsAsync(CancellationToken ct = default);

    /// <summary>Send a chat request with a single prompt.</summary>
    Task<string> ChatAsync(string prompt, string? model = null, string? vendor = null,
        string? systemPrompt = null, CancellationToken ct = default);

    /// <summary>Send a chat request with full message history.</summary>
    Task<string> ChatAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken ct = default);

    /// <summary>Send a chat request and return the structured response.</summary>
    Task<ChatResponse> ChatFullAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken ct = default);

    /// <summary>Stream a chat response. Yields content fragments.</summary>
    IAsyncEnumerable<string> ChatStreamAsync(string prompt, string? model = null,
        string? vendor = null, string? systemPrompt = null, CancellationToken ct = default);

    /// <summary>Stream a chat response with message history.</summary>
    IAsyncEnumerable<string> ChatStreamAsync(IEnumerable<ChatMessage> messages,
        ChatOptions? options = null, CancellationToken ct = default);

    /// <summary>Send a chat request and parse the response as JSON.</summary>
    Task<T> ChatJsonAsync<T>(string prompt, string? model = null, string? systemPrompt = null,
        CancellationToken ct = default);
}
