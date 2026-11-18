"""Generates the Grunt plugin for harnesses that read the Agent Plugins format.

`plugins/grunt` is the plugin: Claude and Codex read it directly, each through
its own manifest. GitHub Copilot CLI, VS Code, Cursor and other harnesses read
the Agent Plugins layout, where every folder under `skills/` loads and the
server sits in `mcp.json`. That layout cannot leave a skill out, so this script
writes a second plugin folder for them, `agent-plugins/grunt`, with the skills
that work outside Claude and Grunt's MCP server. It also writes the two
marketplace files that point those harnesses at it.

Everything it writes is committed. Run it after changing a skill or the version:

    python agent-plugins/build.py          # write
    python agent-plugins/build.py --check  # fail if anything is out of date

Standard library only.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "grunt"
OUTPUT = ROOT / "agent-plugins" / "grunt"

AGENT_PLUGINS_VERSION = "1.0.0"
SCHEMAS = f"https://agent-plugins.org/schemas/{AGENT_PLUGINS_VERSION}"
MCP_SERVER_NAME = "grunt"
CLOUD_MCP_URL = "https://mcp.grunt.io/mcp"
MARKETPLACE_NAME = "grunt-plugins"

# Skills that only work in Claude. Every other harness gets the rest.
CLAUDE_ONLY_SKILLS = {"slides"}
# Claude and Codex list a plugin's skills under its name (`grunt:pptx`). The
# harnesses served here list them bare, where `pptx` or `html` would collide
# with other people's skills, so the names carry the prefix themselves.
SKILL_PREFIX = "grunt-"

DESCRIPTION = (
    "Grunt charts and tables: Grunt's MCP server and skills for charts and tables inside "
    "PowerPoint (grunt-powerpoint), in .pptx files built outside PowerPoint (grunt-pptx) and in "
    "interactive HTML reports (grunt-html). Sign in with your own Grunt account."
)

README = """# Grunt plugin (Agent Plugins)

Generated from [`plugins/grunt`](../../plugins/grunt) by
[`agent-plugins/build.py`](../build.py). Do not edit these files; change the
plugin there and run the script.

This folder is the Grunt plugin for harnesses that read the
[Agent Plugins](https://agent-plugins.org) format, such as GitHub Copilot CLI,
VS Code and Cursor: the `grunt-powerpoint`, `grunt-pptx` and `grunt-html`
skills, and Grunt's MCP server. See the [repository README](../../README.md) for
how to install it.
"""


def portable_skills():
    """The skill folders every harness gets, in name order."""
    skills = sorted(p.name for p in (PLUGIN / "skills").iterdir() if (p / "SKILL.md").is_file())
    return [name for name in skills if name not in CLAUDE_ONLY_SKILLS]


def excluded(relative):
    """Files of a skill folder that only Codex or the maintainers use: the Codex
    card and its icons, the helpers' own tests, and anything hidden or compiled."""
    parts = relative.parts
    if any(part in {"agents", "assets", "__pycache__"} or part.startswith(".") for part in parts):
        return True
    return parts[-1].endswith(".pyc") or (parts[0] == "scripts" and parts[-1].startswith("test_"))


def packaged_name(skill):
    return SKILL_PREFIX + skill


def renamed(text, skills, front_matter_of=None):
    """A skill's Markdown under the packaged names: the other skills where the
    text names them ("the `pptx` skill"), and for SKILL.md its own `name`."""
    names = "|".join(re.escape(name) for name in skills)
    text = re.sub(rf"(?<![\w/.-])(`?)({names})(`?) skill\b", rf"\1{SKILL_PREFIX}\2\3 skill", text)
    if front_matter_of:
        text, count = re.subn(rf"^name: {re.escape(front_matter_of)}$", f"name: {packaged_name(front_matter_of)}",
                              text, count=1, flags=re.MULTILINE)
        if count != 1:
            sys.exit(f"error: {front_matter_of}/SKILL.md has no 'name: {front_matter_of}' line")
    return text


def as_json(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def plugin_files():
    """Every file of the generated plugin, as {path inside the folder: bytes}."""
    source = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    shared = {key: source[key] for key in ("author", "homepage", "repository", "keywords") if key in source}
    files = {
        "plugin.json": as_json({
            "$schema": f"{SCHEMAS}/plugin.schema.json",
            "name": source["name"],
            "version": source["version"],
            "description": DESCRIPTION,
            **shared,
        }),
        # Agent Plugins has no sign-in settings: each harness finds Grunt's
        # sign-in server from the MCP server itself.
        "mcp.json": as_json({
            "$schema": f"{SCHEMAS}/mcp.schema.json",
            "mcpServers": {MCP_SERVER_NAME: {"type": "streamable-http", "url": CLOUD_MCP_URL}},
        }),
        # The same server for harness versions from before Agent Plugins, which
        # read `plugin.json` as their older format and look for `.mcp.json`.
        ".mcp.json": as_json({"mcpServers": {MCP_SERVER_NAME: {"type": "http", "url": CLOUD_MCP_URL}}}),
        # Cursor's own manifest. It finds `skills/` and `mcp.json` by itself.
        ".cursor-plugin/plugin.json": as_json({
            "name": source["name"],
            "version": source["version"],
            "description": DESCRIPTION,
            **shared,
            "logo": "assets/logo.png",
        }),
        "assets/logo.png": (PLUGIN / "assets" / "logo.png").read_bytes(),
        "README.md": README.encode("utf-8"),
    }
    skills = portable_skills()
    for skill in skills:
        folder = PLUGIN / "skills" / skill
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            relative = path.relative_to(folder)
            if excluded(relative):
                continue
            if path.suffix == ".md":
                text = path.read_text(encoding="utf-8")
                data = renamed(text, skills, skill if relative.as_posix() == "SKILL.md" else None).encode("utf-8")
            else:
                data = path.read_bytes()
            files[f"skills/{packaged_name(skill)}/{relative.as_posix()}"] = data
    return files


def marketplace_files():
    """The marketplace files that point at the generated plugin, as {path in the
    repository: bytes}. GitHub Copilot CLI and VS Code read `.github/plugin`
    before `.claude-plugin`; Cursor reads `.cursor-plugin`."""
    source = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    folder = OUTPUT.relative_to(ROOT).as_posix()
    entry = {
        "name": source["name"],
        "description": DESCRIPTION,
        "version": source["version"],
        "category": "productivity",
        "keywords": source["keywords"],
        "homepage": source["homepage"],
    }
    base = {"name": MARKETPLACE_NAME, "owner": {"name": "Grunt"}, "metadata": {"description": "Official Grunt plugins."}}
    return {
        ".github/plugin/marketplace.json": as_json({**base, "plugins": [{**entry, "source": f"./{folder}"}]}),
        ".cursor-plugin/marketplace.json": as_json({**base, "plugins": [{**entry, "source": folder}]}),
    }


def expected():
    """Everything this script owns, as {path in the repository: bytes}."""
    folder = OUTPUT.relative_to(ROOT).as_posix()
    return {**{f"{folder}/{path}": data for path, data in plugin_files().items()}, **marketplace_files()}


def differences():
    """Paths that are missing, stale or left over, compared with what is on disk."""
    wanted = expected()
    stale = [path for path, data in wanted.items() if not (ROOT / path).is_file() or (ROOT / path).read_bytes() != data]
    if OUTPUT.is_dir():
        folder = OUTPUT.relative_to(ROOT).as_posix()
        on_disk = {f"{folder}/{p.relative_to(OUTPUT).as_posix()}" for p in OUTPUT.rglob("*") if p.is_file()}
        stale += sorted(on_disk - set(wanted))
    return sorted(stale)


def write():
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    for path, data in expected().items():
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="change nothing; fail if a generated file is out of date")
    args = parser.parse_args()
    if args.check:
        stale = differences()
        if stale:
            sys.exit("out of date, run python agent-plugins/build.py:\n  " + "\n  ".join(stale))
        print("agent-plugins is up to date")
        return
    write()
    print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()} ({len(plugin_files())} files) and {len(marketplace_files())} marketplace files")


if __name__ == "__main__":
    main()
