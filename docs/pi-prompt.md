# Pi prompt example

[README](../README.md) · [MCP setup](mcp.md)

Use the [`yt.md` prompt template](examples/yt.md) to summarize a YouTube video, explain a concept, or create an Obsidian note from captions.
The template becomes the `/yt` command in Pi.

## Setup

1. Install yt-transcript with the MCP extra and [configure Pi's MCP connection](mcp.md#configure-pi).
2. Review the [template](examples/yt.md). From this repository's root, copy it to Pi's user prompt directory:

   ```sh
   mkdir -p ~/.pi/agent/prompts
   cp -i docs/examples/yt.md ~/.pi/agent/prompts/yt.md
   ```

   `cp -i` asks before replacing an existing prompt. Keep your existing file if it contains changes you want to preserve.
   If you use a custom Pi agent directory, use its `prompts` directory instead.
3. Run `/reload` in an active Pi session.
4. For Obsidian note mode, make the `obsidian-markdown` skill available to Pi. The template references this skill but does not install it.

See Pi's [prompt template documentation](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/prompt-templates.md) for argument syntax and loading rules.

## Usage

Replace `URL` with a YouTube video URL. Enter these commands in Pi, not in a shell.

```text
/yt URL
/yt URL brief
/yt URL brief "Focus on the deployment trade-offs"
/yt URL explain "context windows"
/yt URL note
/yt URL note "/absolute/path/to/vault/Video notes.md"
/yt URL note "/absolute/path/to/vault/" "Focus on practical examples"
```

| Mode | Result |
|---|---|
| `brief` (default) | A concise summary in chat, usually 150–300 words |
| `explain` | An explanation of the named concept, grounded in relevant caption passages |
| `note` | An Obsidian Flavored Markdown note, returned in chat or saved to the supplied path |

Quote concepts, paths, and instructions that contain spaces.
An omitted note path returns the note in chat. A directory path uses a filesystem-safe video-title filename.
The prompt asks before overwriting an existing note.

## Retrieval and cost

The template uses yt-transcript metadata and caption tools rather than a web summary.
For `brief` and `note`, it reads every available caption page in `full` mode before producing a whole-video result.
For `explain`, it searches relevant passages and reads surrounding context.

Caption retrieval does not make a separate model call.
Pi's answer still uses the model selected for your Pi session and can incur charges.
The template does not request yt-transcript's separately charged Markdown processing.
It asks before external fact-checking and treats caption content as untrusted source material.

Captions do not provide complete audiovisual coverage.
The prompt reports material retrieval limits, preserves uncertain terms without guessing, and links to verified timestamps when available.
These are prompt instructions, not guarantees enforced by the MCP server.
