# Model providers

[README](../README.md) · [CLI reference](cli.md) · [MCP setup](mcp.md) · [Troubleshooting](troubleshooting.md)

Model editing is optional. Raw CLI output, MCP plain text, and retrieval tools do not call a model.
Markdown sends transcript text to the selected backend and can incur charges.
The source-caption cache does not store model output or reasoning.

## Pi

Pi is the default Markdown backend.
Install and authenticate Pi separately using the [installation guide](installation.md#prerequisites).
If you do not specify a model, Pi uses its configured default.
An explicit `--model` overrides that selection:

```sh
yt-transcript URL --no-config --max-chunks 3 -o transcript.md
yt-transcript URL --no-config --model provider/model-id --max-chunks 3 -o transcript.md
```

The wrapper uses independent in-memory sessions and does not save local Pi sessions.
The provider can still log or retain data.

## OpenRouter

Direct OpenRouter formatting does not require Pi. Specify the provider and model:

```sh
yt-transcript URL --no-config --provider openrouter --model openai/gpt-4o -o transcript.md
```

Set `OPENROUTER_API_KEY` in the process environment.
Never put the key in TOML or command arguments.
OpenRouter requires an explicit model. It does not require Pi.
Raw modes require neither a model nor credentials.
Preview requires a selected OpenRouter model, but it does not require an API key.
Preview does not make a model request.

**TOML migration:** rename `[pi]` to `[formatting]`.
The wrapper rejects the old table instead of merging it.
Add `provider = "openrouter"` or keep the default `"pi"`.
The `[openrouter]` table accepts only `max_output_tokens`.
The default is 16384, and the range is 1–131072.
The wrapper sends this value as `max_tokens`.
The supported limits depend on the model.
Reasoning tokens can use this allowance.
If output is truncated or empty, processing fails without repair.

The wrapper sends one nonstreaming HTTPS request per completion through a supervised Python helper.
It rejects redirects, HTTP error bodies, tool calls, and incomplete output.
A monotonic deadline applies to the helper and HTTP work.
Socket timeouts do not enforce this deadline on their own.
The wrapper does not retry or change providers automatically.
Requests disable OpenRouter upstream fallback and require parameter support. They request providers with `data_collection="deny"`.
These settings can leave no available route.
The settings do not guarantee zero retention, accuracy, or a fixed upstream identity.
Transcript text reaches OpenRouter and its selected upstream provider.
Calls can incur charges, including work completed after a local timeout.

## DeepSeek

```sh
# Set DEEPSEEK_API_KEY in the process environment first.
yt-transcript URL --no-config --provider deepseek --model deepseek-flash -o transcript.md
```

DeepSeek requires an explicit model. It does not require Pi.
`deepseek-flash` and `deepseek-v4-pro` are examples, not a fixed model catalog.
The key comes only from `DEEPSEEK_API_KEY` in the helper environment.
Never put it in TOML, command arguments, or MCP tool arguments.
Preview requires an explicit model but does not require a key. Doctor checks whether a model and key are present locally, not whether authentication works.
Raw modes require neither a model nor a key.

The fixed endpoint is `https://api.deepseek.com/chat/completions`.
The supervised helper uses standard-library HTTP. It makes one nonstreaming request per planned call and requires no new dependency.
It rejects redirects. It does not retry, make repair calls, or switch to a fallback provider.
`[deepseek]` accepts only `max_output_tokens`. The default is 16384, and the integer range is 1–393216.
The model must support the requested allowance.
Thinking shares this allowance with visible text. Enabling thinking does not raise the limit.
If output is invalid, oversized, empty, or incomplete, processing fails without publishing partial output.
See [byte limits](behavior.md#backend-independent-formatting).

Transcript text reaches DeepSeek directly.
OpenRouter's `data_collection="deny"` routing request does not apply.
Read DeepSeek's privacy policy. The wrapper gives no equivalent retention guarantee.
A local timeout cannot undo charges already incurred.

## Thinking policy

Configure thinking in TOML only. There are no new CLI thinking flags or public MCP arguments.
Both settings are optional. Keep them commented to use the automatic policy:

```toml
[formatting]
# thinking = false
# thinking_level = "medium"
```

`thinking` must be a Boolean. `thinking_level` must be one scalar string: `low`, `medium`, or `high`. It must not be an array.
TOML has no null value. Omit the key instead.

| `thinking` | Editorial mode | Requested policy |
|---|---|---|
| Omitted | Standard/focused | Preserve Pi/OpenRouter defaults; DeepSeek off |
| Omitted | Summarized | On at configured level, otherwise medium |
| `true` | Any | On at configured level, otherwise medium |
| `false` | Any | Off; a valid configured level stays inactive |

A level alone is valid in summarized mode because automatic thinking enables it.
In standard/focused mode, a level requires `thinking = true`, unless explicit false keeps the level inactive.
Otherwise, formatting reports a safe configuration error. It does not silently enable paid behavior.
Raw and model-free MCP operations validate configuration but never call a model because of these settings.
Direct summaries, each notes call, and final synthesis all use the same requested level.

Pi receives `--thinking off` or the selected level. If thinking is omitted in standard/focused mode, no flag is added.
OpenRouter receives explicit reasoning enabled/effort settings that exclude response reasoning. If defaults are preserved, no reasoning field is added.
DeepSeek receives `thinking.type` enabled or disabled and maps low/medium/high to low/high/high when enabled.
Medium therefore requests high from DeepSeek.
These states are requests. They do not verify provider behavior or indicate equal token budgets.
Pi and OpenRouter can clamp or map levels or reject unsupported parameters.
Some models cannot disable reasoning.
OpenRouter still requires parameter support and disables upstream fallback.

Thinking can increase cost and latency. It can also increase competition for tokens between thinking and visible output.
Reasoning exclusion hides response content but does not disable thinking or billing.
The wrapper does not raise token limits automatically, add calls, retry, repair, or return partial output.
Automatic summary thinking is application policy, not evidence of improved fidelity.

## Saved settings and MCP

Use [config.example.toml](../config.example.toml) as a reference. Edit existing tables rather than replacing your configuration.
For example:

```toml
[formatting]
provider = "deepseek"   # "pi", "openrouter", or "deepseek"
model = "deepseek-flash"
# thinking = false
# thinking_level = "medium"

[deepseek]
max_output_tokens = 16384
```

For OpenRouter, select `provider = "openrouter"`, set an explicit OpenRouter model ID, and use `[openrouter]` for its token limit.
For Pi, omit both provider and model to keep its defaults.

MCP uses server TOML for provider, model, thinking, and editorial settings.
These settings are not public tool arguments.
Make API keys available in the server's inherited process environment, not TOML, tool arguments, or chat.
A running client does not inherit a key that you export later in another terminal.
`--no-config` bypasses saved server settings.
See [MCP setup](mcp.md) for client configuration and restart steps.
