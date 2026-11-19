# Release the ChatGPT package

The Claude and Codex marketplace catalogs both point to `plugins/grunt`.
ChatGPT workspace admins can [import the same GitHub repository](https://learn.chatgpt.com/docs/enterprise/plugin-management).
Those marketplace installs use the Grunt connection configured for the user
or workspace. Claude organization-wide GitHub sync uses a private or internal
copy of the marketplace.

The **public ChatGPT directory** uses the separately built ZIP. The build
copies the shared HTML and PPTX skills and logo, adapts the skill instructions
for ChatGPT, and adds the listing and OAuth settings from `packaging/chatgpt`.
The ZIP contains the production Grunt Cloud MCP connection. Publish it as a
GitHub Release asset and upload the same file to OpenAI.

## Build locally

From a Git checkout with Node.js and Info-ZIP installed, run:

```sh
node packaging/chatgpt/build.mjs
```

The default output is `dist/Grunt-ChatGPT-<version>.zip`. Pass a directory
as the first argument to write the ZIP elsewhere. The build reads the version
from the matching Claude and Codex manifests and uses the tracked skill files.

## Release

1. Raise the version in both marketplace manifests for distribution changes.
   Open a PR to `main` and wait for **Validate plugin**. Download the
   `chatgpt-plugin` artifact to smoke-test the package if it changed.
2. Merge the release PR to `main`. A merge makes the marketplace changes
   available to customers who track that branch.
3. Push a matching version tag on the merged commit, such as `v0.3.12`.
   The workflow validates the tag and publishes a GitHub Release with the
   ZIP and `SHA256SUMS`.
4. Upload that ZIP to the existing listing in the
   [OpenAI Plugins dashboard](https://platform.openai.com/plugins).
   Complete the checks and review, then publish the approved version.
   Keep reviewer credentials in the dashboard.

Require **Validate plugin** on `main` and restrict creation of `v*` tags
to release maintainers in GitHub rulesets. The workflow also checks the
tagged commit is on `main` and its version matches the manifests.

Deploy Grunt MCP changes through Oak's existing deployment workflow. OpenAI
[scans the hosted server](https://developers.openai.com/plugins/deploy/submission#update-to-your-mcp-server)
after publication. Keep the server compatible with live tool definitions
while changes are in review. Ship a new ZIP when the package changes.
