# Connecting to Grunt

The Grunt skills need the Grunt MCP server:

- URL: `https://mcp.grunt.io/mcp` (streamable HTTP)
- Sign-in: OAuth in the browser, with the user's own Grunt account

Installing the Grunt plugin adds the server, but each user still signs in once.
Use these steps when you tell the user how to connect.

| App | Steps |
| --- | --- |
| Claude Code | Run `/mcp`, choose the Grunt server (`plugin:grunt:Grunt` when it comes from the plugin) and choose **Authenticate**. Without the plugin, add the server first: `claude mcp add --transport http grunt https://mcp.grunt.io/mcp`. |
| Codex CLI | Run `codex mcp list` to find the Grunt server's name, then `codex mcp login <name>`. Without the plugin, add the server first: `codex mcp add grunt --url https://mcp.grunt.io/mcp`, then run `codex mcp login grunt`. |
| Other apps | Add the server URL in the app's MCP or connector settings, then sign in when the app asks. |

Some apps load a newly connected server's tools only in a new session or after a
restart.
