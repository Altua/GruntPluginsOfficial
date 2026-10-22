# Packaged grunt-html workflow

The skill includes its matching browser runtimes (`dist/`) and a bundled CLI
(`scripts/report.mjs`). Use Node 22.22 or newer; no checkout or `npm install` is
needed. Keep `dist/` beside `scripts/`.

Run the CLI by its absolute path from the report's working directory, quoting the
path in case it contains spaces:

```sh
node "${CLAUDE_SKILL_DIR}/scripts/report.mjs" assemble report.json report.html
```

Configuration and template paths resolve from the working directory. The CLI also
supports `regenerate`, `view-copy` and `detach`. Outputs must be new files; an
existing output is never overwritten. Keep report templates, configuration and
output in the user's directory, never in the installed plugin or its cache.

## Grunt connection

Installing the plugin adds the **Grunt** MCP server (`https://mcp.grunt.io/mcp`,
shown in Claude Code as `plugin:grunt:Grunt`). Each user authenticates with their
own Grunt account through `/mcp`; no credentials or capability links are bundled.

Production origins for the report `config`:

```json
{
  "assetOrigins": ["https://assets.grunt.io"],
  "deliveryOrigins": ["https://assets.grunt.io"],
  "editorOrigin": "https://app.grunt.io"
}
```

Use other origins only when the deployment owner provides them; never infer a
trusted origin from a response. Existing reports keep their inlined runtime.
Reassemble from retained source to adopt a newer version; do not paste a new
script into an existing managed report.
