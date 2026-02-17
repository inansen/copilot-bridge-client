// Copilot Bridge Client for C# / .NET
// Connects to the VS Code Copilot API Bridge extension via HTTP.
//
// Usage:
//   var client = new CopilotClient();
//   string answer = await client.ChatAsync("Explain LINQ");
//
//   // Streaming
//   await foreach (var chunk in client.ChatStreamAsync("Write hello world"))
//       Console.Write(chunk);
//
//   // Choose model
//   string answer = await client.ChatAsync("Hello", model: "gpt-4o-mini");

using System.Net.Http.Headers;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace CopilotBridge;

// ── Models ──────────────────────────────────────────────────────────────────

public record ChatMessage(string Role, string Content);

public class ChatOptions
{
    public string? Model { get; set; }
    public string? Vendor { get; set; }
    public string? SystemPrompt { get; set; }
}

public class StatusResponse
{
    [JsonPropertyName("status")] public string Status { get; set; } = "";
    [JsonPropertyName("port")] public int Port { get; set; }
    [JsonPropertyName("defaultModel")] public string DefaultModel { get; set; } = "";
    [JsonPropertyName("requestsServed")] public int RequestsServed { get; set; }
    [JsonPropertyName("version")] public string Version { get; set; } = "";
}

public class ModelInfo
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("vendor")] public string Vendor { get; set; } = "";
    [JsonPropertyName("family")] public string Family { get; set; } = "";
    [JsonPropertyName("version")] public string Version { get; set; } = "";
    [JsonPropertyName("maxInputTokens")] public int MaxInputTokens { get; set; }
}

public class ChatResponse
{
    [JsonPropertyName("id")] public int Id { get; set; }
    [JsonPropertyName("model")] public string Model { get; set; } = "";
    [JsonPropertyName("content")] public string Content { get; set; } = "";
}

// ── Client ──────────────────────────────────────────────────────────────────

public class CopilotClient : ICopilotClient
{
    private readonly HttpClient _http;
    private readonly string _baseUrl;
    private readonly string? _apiKey;
    private readonly string? _defaultModel;
    private readonly string? _defaultVendor;

    public CopilotClient(
        string baseUrl = "http://127.0.0.1:3741",
        string? apiKey = null,
        string? defaultModel = null,
        string? defaultVendor = null)
    {
        _baseUrl = baseUrl.TrimEnd('/');
        _apiKey = apiKey;
        _defaultModel = defaultModel;
        _defaultVendor = defaultVendor;

        _http = new HttpClient { Timeout = TimeSpan.FromMinutes(5) };
        if (!string.IsNullOrEmpty(_apiKey))
            _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
    }

    // ── Public API ──────────────────────────────────────────────────────

    /// <summary>Get server status.</summary>
    public async Task<StatusResponse> GetStatusAsync(CancellationToken ct = default)
    {
        var json = await GetAsync("/status", ct);
        return JsonSerializer.Deserialize<StatusResponse>(json)!;
    }

    /// <summary>List available models.</summary>
    public async Task<List<ModelInfo>> ListModelsAsync(CancellationToken ct = default)
    {
        var json = await GetAsync("/models", ct);
        using var doc = JsonDocument.Parse(json);
        var modelsJson = doc.RootElement.GetProperty("models").GetRawText();
        return JsonSerializer.Deserialize<List<ModelInfo>>(modelsJson) ?? [];
    }

    /// <summary>Send a chat request with a single prompt string.</summary>
    public Task<string> ChatAsync(string prompt, string? model = null, string? vendor = null,
        string? systemPrompt = null, CancellationToken ct = default)
        => ChatAsync([new("user", prompt)], new() { Model = model, Vendor = vendor, SystemPrompt = systemPrompt }, ct);

    /// <summary>Send a chat request with message history.</summary>
    public async Task<string> ChatAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken ct = default)
    {
        var payload = BuildPayload(messages, options);
        var json = await PostAsync("/chat", payload, ct);
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement.GetProperty("content").GetString() ?? "";
    }

    /// <summary>Send a chat request and get the full structured response.</summary>
    public async Task<ChatResponse> ChatFullAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken ct = default)
    {
        var payload = BuildPayload(messages, options);
        var json = await PostAsync("/chat", payload, ct);
        return JsonSerializer.Deserialize<ChatResponse>(json)!;
    }

    /// <summary>Stream a chat response. Yields content fragments.</summary>
    public async IAsyncEnumerable<string> ChatStreamAsync(
        string prompt, string? model = null, string? vendor = null, string? systemPrompt = null,
        [EnumeratorCancellation] CancellationToken ct = default)
    {
        var messages = new[] { new ChatMessage("user", prompt) };
        var options = new ChatOptions { Model = model, Vendor = vendor, SystemPrompt = systemPrompt };

        await foreach (var chunk in ChatStreamAsync(messages, options, ct))
            yield return chunk;
    }

    /// <summary>Stream a chat response with message history.</summary>
    public async IAsyncEnumerable<string> ChatStreamAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken ct = default)
    {
        var payload = BuildPayload(messages, options);
        var content = new StringContent(payload, Encoding.UTF8, "application/json");
        using var request = new HttpRequestMessage(HttpMethod.Post, $"{_baseUrl}/chat/stream") { Content = content };
        using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
        response.EnsureSuccessStatusCode();

        using var stream = await response.Content.ReadAsStreamAsync(ct);
        using var reader = new StreamReader(stream);

        var buffer = new StringBuilder();
        while (await reader.ReadLineAsync(ct) is { } line)
        {
            if (line.StartsWith("data: "))
            {
                var eventData = line[6..];
                using var doc = JsonDocument.Parse(eventData);
                var root = doc.RootElement;

                if (root.TryGetProperty("done", out var done) && done.GetBoolean())
                    yield break;
                if (root.TryGetProperty("error", out var error))
                    throw new CopilotClientException(error.GetString() ?? "Unknown error");
                if (root.TryGetProperty("content", out var c))
                    yield return c.GetString() ?? "";
            }
        }
    }

    /// <summary>Send a chat request and parse response as JSON.</summary>
    public async Task<T> ChatJsonAsync<T>(string prompt, string? model = null, string? systemPrompt = null,
        CancellationToken ct = default)
    {
        var text = await ChatAsync(prompt, model: model, systemPrompt: systemPrompt, ct: ct);
        return ParseJsonResponse<T>(text);
    }

    // ── Internals ───────────────────────────────────────────────────────

    private string BuildPayload(IEnumerable<ChatMessage> messages, ChatOptions? options)
    {
        var msgs = messages.Select(m => new { role = m.Role, content = m.Content }).ToArray();
        var dict = new Dictionary<string, object> { ["messages"] = msgs };

        var model = options?.Model ?? _defaultModel;
        var vendor = options?.Vendor ?? _defaultVendor;
        if (model != null) dict["model"] = model;
        if (vendor != null) dict["vendor"] = vendor;
        if (options?.SystemPrompt != null) dict["systemPrompt"] = options.SystemPrompt;

        return JsonSerializer.Serialize(dict);
    }

    private async Task<string> GetAsync(string path, CancellationToken ct)
    {
        var response = await _http.GetAsync($"{_baseUrl}{path}", ct);
        var body = await response.Content.ReadAsStringAsync(ct);
        if (!response.IsSuccessStatusCode)
            throw new CopilotClientException($"HTTP {(int)response.StatusCode}: {body}");
        return body;
    }

    private async Task<string> PostAsync(string path, string jsonPayload, CancellationToken ct)
    {
        var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");
        var response = await _http.PostAsync($"{_baseUrl}{path}", content, ct);
        var body = await response.Content.ReadAsStringAsync(ct);
        if (!response.IsSuccessStatusCode)
            throw new CopilotClientException($"HTTP {(int)response.StatusCode}: {body}");
        return body;
    }

    private static T ParseJsonResponse<T>(string text)
    {
        try { return JsonSerializer.Deserialize<T>(text)!; }
        catch (JsonException) { }

        var fenceMatch = Regex.Match(text, @"```(?:json)?\s*([\s\S]*?)```");
        if (fenceMatch.Success)
            return JsonSerializer.Deserialize<T>(fenceMatch.Groups[1].Value.Trim())!;

        var braceMatch = Regex.Match(text, @"\{[\s\S]*\}");
        if (braceMatch.Success)
            return JsonSerializer.Deserialize<T>(braceMatch.Value)!;

        throw new CopilotClientException($"Could not parse JSON from response: {text[..Math.Min(text.Length, 500)]}");
    }

    public void Dispose() => _http.Dispose();
}

// ── Exception ───────────────────────────────────────────────────────────────

public class CopilotClientException : Exception
{
    public CopilotClientException(string message) : base(message) { }
}

// ── Static convenience ──────────────────────────────────────────────────────

public static class Copilot
{
    private static CopilotClient? _client;

    /// <summary>
    /// One-liner to ask Copilot a question.
    ///   string answer = await Copilot.AskAsync("What is a monad?");
    /// </summary>
    public static async Task<string> AskAsync(string prompt, string? model = null, string baseUrl = "http://127.0.0.1:3741")
    {
        _client ??= new CopilotClient(baseUrl);
        return await _client.ChatAsync(prompt, model: model);
    }
}
