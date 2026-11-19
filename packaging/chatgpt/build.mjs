import { execFileSync } from "node:child_process";
import {
  chmodSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, utimesSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packaging = dirname(fileURLToPath(import.meta.url));
const repository = resolve(packaging, "../..");
const plugin = "plugins/grunt";
const skills = ["html", "pptx"];
const readJson = (path) => JSON.parse(readFileSync(path, "utf8"));
const { version } = readJson(join(repository, plugin, ".codex-plugin/plugin.json"));
if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)
    || version !== readJson(join(repository, plugin, ".claude-plugin/plugin.json")).version) {
  throw new Error("Claude and Codex must have the same stable version (major.minor.patch).");
}

const connect = `# Connect Grunt in ChatGPT

Install Grunt and select it in the chat. Follow ChatGPT's connection prompt
and sign in to Grunt Cloud in your browser. Your Grunt account determines
which assets and features you can access. If the tools are unavailable, check
whether your workspace permits Grunt and start a new chat after connecting.
`;

const connectionCheck = `## Before you start: check the Grunt connection

1. Use the Grunt Cloud connection included with this plugin. Look for
   \`create_or_update_bar_chart\`, \`create_asset_link\`, and \`get_rendering_fonts\`.
   ChatGPT may prefix tool names.
2. Call \`get_rendering_fonts\` without arguments to confirm access. If ChatGPT
   requests authorization, let the user complete the browser sign-in.
3. If the tools are unavailable, use [CONNECT.md](CONNECT.md) to help the user
   connect Grunt. Use the same account and connection for the deliverable.
`;

function replaceRequired(text, pattern, replacement) {
  if (!pattern.test(text)) {
    throw new Error(`The shared skill changed. Update the ChatGPT adaptation for ${pattern}.`);
  }
  return text.replace(pattern, replacement);
}

function adaptSkill(name, text) {
  text = replaceRequired(text, /^## Before you start: check the Grunt connection\n[\s\S]*?(?=^## )/m, `${connectionCheck}\n`);
  if (name === "html") return text;

  text = replaceRequired(text, / Not for use inside PowerPoint \(Claude[^\n]+? applies\./, "");
  text = replaceRequired(text, /^Inside PowerPoint \(Claude[^\n]*\nuse the \`powerpoint\` skill instead\.\n\n/m, "");
  text = replaceRequired(text, /^On Windows, \`render_deck\.py\`[\s\S]*?(?=^## Workflow)/m,
    "Use the renderer available in the execution environment. If it has no renderer, run the inventory and layout checks and report that visual verification is pending.\n\n");
  text = replaceRequired(text, / When the values come from an Excel\n[\s\S]*?\]\(#excel-workbooks-on-the-users-computer\)\./,
    " For a workbook attached to the\n   chat, use the requested range and identify the worksheet in the result.");
  text = replaceRequired(text, /^## Excel workbooks on the user's computer\n[\s\S]*?(?=^## Sizing rules)/m, "");
  return replaceRequired(text, /^## Tests\n[\s\S]*$/m, "").trimEnd() + "\n";
}

const manifest = { ...readJson(join(packaging, "plugin.json")), version };
const mcp = readJson(join(packaging, "mcp.json"));
const listing = manifest.extensions["com.openai"].interface;
const server = mcp.mcpServers.grunt;
const auth = server.extensions["com.openai"].auth;
if (Object.keys(mcp.mcpServers).length !== 1 || Object.hasOwn(server, "headers")
    || server.type !== "streamable-http" || server.url !== "https://mcp.grunt.io/mcp"
    || auth.type !== "oauth" || auth.client.mode !== "cimd" || auth.client.clientSecret
    || auth.baseScopes.length !== 1 || auth.baseScopes[0] !== "mcp.access") {
  throw new Error("The public ZIP must use OAuth discovery for the production Grunt MCP server.");
}
if (![listing.displayName, listing.shortDescription].every((value) => value?.length && value.length <= 30)
    || !["websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"].every((key) => {
      const url = new URL(listing[key]);
      return url.protocol === "https:" && !url.username && !url.password;
    })) {
  throw new Error("Check the required OpenAI listing names and URLs.");
}

const output = resolve(process.argv[2] ?? "dist");
mkdirSync(output, { recursive: true });
const filename = `Grunt-ChatGPT-${version}.zip`;
const stage = mkdtempSync(join(tmpdir(), "grunt-chatgpt-"));
const files = new Set();
// A fixed date and file order keep repeated builds of the same inputs stable.
const timestamp = new Date("2000-01-01T00:00:00Z");
function addFile(path, content) {
  const target = join(stage, path);
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, content);
  chmodSync(target, 0o644);
  utimesSync(target, timestamp, timestamp);
  files.add(path);
}

try {
  const tracked = execFileSync("git", [
    "ls-files", "-z", "--", `${plugin}/assets/logo.png`, ...skills.map((skill) => `${plugin}/skills/${skill}`),
  ], { cwd: repository, encoding: "utf8" }).split("\0").filter(Boolean);
  for (const source of tracked) {
    const path = source.slice(plugin.length + 1);
    if (path.split("/").some((part) => part.startsWith(".") || part.startsWith("test_"))) continue;
    if (path.endsWith("/CONNECT.md")) {
      addFile(path, connect);
    } else if (path.endsWith("/SKILL.md")) {
      addFile(path, adaptSkill(path.split("/")[1], readFileSync(join(repository, source), "utf8")));
    } else if (path === "skills/html/PACKAGED.md") {
      addFile(path, replaceRequired(readFileSync(join(repository, source), "utf8"),
        /^## Grunt connection\n[\s\S]*?(?=^Origins of Grunt)/m,
        "## Grunt connection\n\nUse the Grunt Cloud connection included with this plugin. Follow [CONNECT.md](CONNECT.md) to sign in.\n\n"));
    } else {
      addFile(path, readFileSync(join(repository, source)));
    }
  }
  for (const path of [listing.logo.slice(2), listing.composerIcon.slice(2),
    ...skills.flatMap((name) => [`skills/${name}/SKILL.md`, `skills/${name}/CONNECT.md`]),
    "skills/html/scripts/report.mjs", "skills/html/dist/grunt-report.js", "skills/pptx/scripts/insert_chart.py"]) {
    if (!files.has(path)) throw new Error(`Missing package file: ${path}`);
  }
  addFile("plugin.json", JSON.stringify(manifest, null, 2) + "\n");
  addFile("mcp.json", JSON.stringify(mcp, null, 2) + "\n");
  const archive = join(stage, filename);
  execFileSync("zip", ["-X", "-q", archive, "-@"], {
    cwd: stage,
    env: { ...process.env, TZ: "UTC" },
    input: [...files].sort().join("\n") + "\n",
  });
  // Copy to a temporary path in the destination before replacing an earlier build.
  const pending = mkdtempSync(join(output, ".grunt-chatgpt-"));
  try {
    const stagedArchive = join(pending, filename);
    copyFileSync(archive, stagedArchive);
    renameSync(stagedArchive, join(output, filename));
  } finally {
    rmSync(pending, { recursive: true, force: true });
  }
  console.log(join(output, filename));
} finally {
  rmSync(stage, { recursive: true, force: true });
}
