# Connecting to Grunt

The Grunt skills need the Grunt MCP server:

- URL: `https://mcp.grunt.io/mcp` (streamable HTTP)
- Sign-in: OAuth in the browser, with the user's own Grunt account

In Claude Desktop, claude.ai, Cowork and Claude for PowerPoint, users connect
Grunt through their organization's Grunt connector. In Claude Code and the
Codex CLI, installing the Grunt plugin adds the server, but each user still
signs in once. Use these steps when you tell the user how to connect.

| App | Steps |
| --- | --- |
| Claude Desktop, claude.ai and Cowork | Open **Customize > Connectors** (**Settings > Connectors** in older versions), find **Grunt** and choose **Connect**, then sign in with your Grunt account. In a chat, choose **+** > **Connectors** and check that Grunt is on. If Grunt is not listed, ask an organization owner to add it under **Organization settings > Connectors** with the server URL; on a personal plan, choose **Add custom connector** and enter the URL yourself. |
| Claude for PowerPoint | The add-in uses the connectors of your Claude account, so connect Grunt there first, as above. Then, in the Claude pane, choose **+** > **Connectors** and check that Grunt is on. |
| Claude Code | Run `/mcp`, choose the Grunt server (`plugin:grunt:Grunt` when it comes from the plugin) and choose **Authenticate**. Without the plugin, add the server first: `claude mcp add --transport http grunt https://mcp.grunt.io/mcp`. |
| Codex CLI | Run `codex mcp list` to find the Grunt server's name, then `codex mcp login <name>`. Without the plugin, add the server first: `codex mcp add grunt --url https://mcp.grunt.io/mcp`, then run `codex mcp login grunt`. |
| Other apps | Add the server URL in the app's MCP or connector settings, then sign in when the app asks. |

## Two Grunt servers

The Grunt plugin brings its own Grunt server: production, with its own sign-in.
An app that also has the organization's Grunt connector, such as Claude for
PowerPoint, then lists a second server named Grunt, and that one asks you to
sign in.

- Use the organization's Grunt connector. You don't need to sign in to the
  plugin's server as well.
- In Claude Code, the Grunt connector of your Claude account can appear next to
  `plugin:grunt:Grunt`. If it is connected, use it and skip **Authenticate** for
  the plugin's server.
- The skills use a Grunt server that is signed in, don't ask you to sign in to a
  second one, and keep to one server for a whole deck or report, so every asset
  belongs to the same account.

Some apps load a newly connected server's tools only in a new session or after a
restart.
