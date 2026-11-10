# Packaged grunt-html workflow

The skill includes its matching browser runtimes (`dist/`) and a bundled CLI
(`scripts/report.mjs`). Use Node 22.22 or newer; no checkout or `npm install` is
needed. Keep `dist/` beside `scripts/`.

Run the CLI by its absolute path from the report's working directory, quoting the
path in case it contains spaces. `<skill-dir>` stands for the absolute path of
the folder that contains SKILL.md:

```sh
node "<skill-dir>/scripts/report.mjs" assemble report.json report.html
```

Configuration and template paths resolve from the working directory. The CLI also
supports `regenerate`, `view-copy` and `detach`. Outputs must be new files; an
existing output is never overwritten. Keep report templates, configuration and
output in the user's directory, never in the installed plugin or its cache.

## Grunt connection

The plugin brings no Grunt server. The skill works through the Grunt connector
that is connected in the user's app, normally the organization's, which can be
Grunt's cloud service or a Grunt the organization runs itself. Each user signs
in with their own Grunt account; no credentials or capability links are bundled.
SKILL.md starts by checking the connection, and [CONNECT.md](CONNECT.md) lists
the steps to connect in common apps.

Origins of Grunt's cloud service for the report `config`:

```json
{
  "assetOrigins": ["https://assets.grunt.io"],
  "deliveryOrigins": ["https://assets.grunt.io"],
  "editorOrigin": "https://app.grunt.io"
}
```

A Grunt the organization runs itself, or a test environment, has its own
origins. The `assetUrl` that `create_asset_link` returns shows which asset origin
is in use: when it is not the cloud service's, ask the user to confirm it and to
give the delivery and editor origins, which their Grunt administrator has. Use
other origins only when the user or the deployment owner provides them; never
infer a trusted origin from a response. Existing reports keep their inlined runtime.
Reassemble from retained source to adopt a newer version; do not paste a new
script into an existing managed report.
