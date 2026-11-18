"""Checks that each harness is pointed at the right variant of the plugin.

Every harness reads its own marketplace file first, so one repository serves
them all: Claude gets every skill and no MCP server; the others get the skills
that work outside Claude, and Grunt's MCP server.

Run from the repository root:
    python -m unittest discover -s tests -p "test_*.py"
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "grunt"
GENERATED = ROOT / "agent-plugins" / "grunt"

_spec = importlib.util.spec_from_file_location("agent_plugins_build", ROOT / "agent-plugins" / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

AGENT_PLUGINS = "https://agent-plugins.org/schemas/1.0.0"
CLOUD = "https://mcp.grunt.io/mcp"
ALL_SKILLS = sorted(p.name for p in (PLUGIN / "skills").iterdir() if p.is_dir())
PORTABLE = [name for name in ALL_SKILLS if name not in build.CLAUDE_ONLY_SKILLS]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def plugin_folder(marketplace, entry_path):
    """The folder a marketplace file's only plugin entry points at."""
    plugins = read_json(ROOT / marketplace)["plugins"]
    assert len(plugins) == 1, marketplace
    return (ROOT / entry_path(plugins[0])).resolve()


class RoutingTests(unittest.TestCase):
    def test_claude_reads_the_plugin_with_every_skill(self):
        folder = plugin_folder(".claude-plugin/marketplace.json", lambda entry: entry["source"])
        self.assertEqual(folder, PLUGIN.resolve())
        manifest = read_json(folder / ".claude-plugin" / "plugin.json")
        # No `skills` field: Claude scans `skills/`, which holds all of them.
        self.assertNotIn("skills", manifest)
        self.assertLessEqual(build.CLAUDE_ONLY_SKILLS, set(ALL_SKILLS))

    def test_claude_gets_no_mcp_server(self):
        # In Claude a bundled server takes the place of the organization's Grunt
        # connector. Claude Code starts one from `.mcp.json` at the plugin root or
        # from `mcpServers` in its manifest, and from nowhere else.
        self.assertFalse((PLUGIN / ".mcp.json").exists())
        self.assertNotIn("mcpServers", read_json(PLUGIN / ".claude-plugin" / "plugin.json"))

    def test_the_claude_folder_has_no_agent_plugins_manifest(self):
        # Codex reads a root `plugin.json` with the Agent Plugins schema before
        # `.codex-plugin/plugin.json`. It would then load every skill, and lose
        # the Codex listing texts and icons.
        self.assertFalse((PLUGIN / "plugin.json").exists())
        self.assertFalse((PLUGIN / "mcp.json").exists())

    def test_codex_reads_the_same_folder_through_its_own_manifest(self):
        folder = plugin_folder(".agents/plugins/marketplace.json", lambda entry: entry["source"]["path"])
        self.assertEqual(folder, PLUGIN.resolve())
        manifest = read_json(folder / ".codex-plugin" / "plugin.json")
        # A list replaces Codex's scan of `skills/`, which keeps Claude-only skills out.
        self.assertEqual(manifest["skills"], [f"./skills/{name}" for name in ("powerpoint", "pptx", "html")])
        self.assertEqual(sorted(Path(path).name for path in manifest["skills"]), PORTABLE)
        for path in manifest["skills"]:
            self.assertTrue((folder / path / "SKILL.md").is_file(), path)

    def test_codex_gets_the_server_from_a_file_claude_does_not_read(self):
        manifest = read_json(PLUGIN / ".codex-plugin" / "plugin.json")
        config = PLUGIN / manifest["mcpServers"]
        self.assertTrue(config.is_file())
        self.assertEqual(config.parent.name, ".codex-plugin")
        self.assertEqual(read_json(config), {"mcpServers": {"grunt": {"type": "http", "url": CLOUD}}})

    def test_copilot_and_vs_code_read_the_generated_plugin(self):
        folder = plugin_folder(".github/plugin/marketplace.json", lambda entry: entry["source"])
        self.assertEqual(folder, GENERATED.resolve())
        self.assertEqual(read_json(folder / "plugin.json")["$schema"], f"{AGENT_PLUGINS}/plugin.schema.json")

    def test_cursor_reads_the_generated_plugin(self):
        folder = plugin_folder(".cursor-plugin/marketplace.json", lambda entry: entry["source"])
        self.assertEqual(folder, GENERATED.resolve())
        self.assertTrue((folder / ".cursor-plugin" / "plugin.json").is_file())

    def test_no_marketplace_file_shadows_the_others(self):
        # GitHub Copilot CLI and VS Code read these two before `.github/plugin`.
        self.assertFalse((ROOT / "marketplace.json").exists())
        self.assertFalse((ROOT / ".plugin" / "marketplace.json").exists())

    def test_marketplaces_and_manifests_agree_on_name_and_version(self):
        marketplaces = [".claude-plugin", ".agents/plugins", ".github/plugin", ".cursor-plugin"]
        self.assertEqual({read_json(ROOT / m / "marketplace.json")["name"] for m in marketplaces}, {"grunt-plugins"})
        manifests = [
            PLUGIN / ".claude-plugin" / "plugin.json", PLUGIN / ".codex-plugin" / "plugin.json",
            GENERATED / "plugin.json", GENERATED / ".cursor-plugin" / "plugin.json",
        ]
        self.assertEqual(len({(read_json(m)["name"], read_json(m)["version"]) for m in manifests}), 1)
        for marketplace in (".github/plugin", ".cursor-plugin"):
            entry = read_json(ROOT / marketplace / "marketplace.json")["plugins"][0]
            self.assertEqual(entry["version"], read_json(manifests[0])["version"], marketplace)


class GeneratedPluginTests(unittest.TestCase):
    def test_generated_files_are_up_to_date(self):
        self.assertEqual(build.differences(), [], "run python agent-plugins/build.py")

    def test_manifest_keeps_to_the_agent_plugins_fields(self):
        # The format's schema is closed: any other top-level field is reported.
        manifest = read_json(GENERATED / "plugin.json")
        allowed = {"$schema", "name", "version", "description", "author", "homepage", "repository", "license", "keywords", "extensions"}
        self.assertLessEqual(set(manifest), allowed)
        self.assertRegex(manifest["name"], r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
        self.assertLessEqual(set(manifest["author"]), {"name", "email", "url"})

    def test_mcp_json_declares_grunts_cloud_server(self):
        config = read_json(GENERATED / "mcp.json")
        self.assertEqual(set(config), {"$schema", "mcpServers"})
        # A version other than the manifest's switches MCP off for the plugin.
        self.assertEqual(config["$schema"], f"{AGENT_PLUGINS}/mcp.schema.json")
        self.assertEqual(config["mcpServers"], {"grunt": {"type": "streamable-http", "url": CLOUD}})

    def test_older_harness_versions_find_the_same_server(self):
        # Before Agent Plugins, GitHub Copilot CLI read `.mcp.json`; newer versions
        # read only `mcp.json`. With both files each version loads the server once.
        self.assertEqual(read_json(GENERATED / ".mcp.json"), {"mcpServers": {"grunt": {"type": "http", "url": CLOUD}}})

    def test_it_holds_the_skills_that_work_outside_claude(self):
        folders = sorted(p.name for p in (GENERATED / "skills").iterdir() if p.is_dir())
        self.assertEqual(folders, [f"grunt-{name}" for name in PORTABLE])
        for folder in folders:
            text = (GENERATED / "skills" / folder / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(re.search(r"^name: (\S+)$", text, re.MULTILINE).group(1), folder)

    def test_skills_name_each_other_by_their_new_names(self):
        for doc in (GENERATED / "skills").rglob("*.md"):
            text = doc.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"(?<![\w/.-])`?(powerpoint|pptx|html)`? skill\b", text), doc.name)

    def test_codex_cards_and_tests_are_left_out(self):
        for path in (GENERATED / "skills").rglob("*"):
            parts = path.relative_to(GENERATED).parts
            self.assertNotIn("agents", parts, path)
            self.assertFalse(path.name.startswith("test_"), path)

    def test_links_between_skill_files_resolve(self):
        for doc in (GENERATED / "skills").rglob("*.md"):
            for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", doc.read_text(encoding="utf-8")):
                if not re.match(r"[a-z]+:", target):
                    self.assertTrue((doc.parent / target).exists(), f"{doc.name} links to {target}")


if __name__ == "__main__":
    unittest.main()
