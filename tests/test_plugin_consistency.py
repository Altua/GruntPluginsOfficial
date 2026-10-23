"""Checks that the plugin manifests agree and the skills stay host-neutral.

Run from the repository root:
    python -m unittest discover -s tests -p "test_*.py"
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "grunt"
SKILLS = sorted(p for p in (PLUGIN / "skills").iterdir() if p.is_dir())
CONNECTION_HEADING = "## Before you start: check the Grunt connection"

# Host-specific wording allowed only in CONNECT.md, which lists steps per app.
HOST_SPECIFIC = [
    "${CLAUDE_",
    "`/mcp`",
    "/reload-plugins",
    "plugin:grunt:Grunt",
    "Write tool",
]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def connection_section(skill_md):
    text = skill_md.read_text(encoding="utf-8")
    start = text.index(CONNECTION_HEADING)
    end = text.find("\n## ", start + len(CONNECTION_HEADING))
    return text[start:end if end != -1 else len(text)]


class ManifestTests(unittest.TestCase):
    def test_claude_and_codex_manifests_agree(self):
        claude = read_json(PLUGIN / ".claude-plugin" / "plugin.json")
        codex = read_json(PLUGIN / ".codex-plugin" / "plugin.json")
        for key in ("name", "version", "description"):
            self.assertEqual(claude[key], codex[key], key)

    def test_codex_manifest_paths_exist(self):
        codex = read_json(PLUGIN / ".codex-plugin" / "plugin.json")
        self.assertTrue((PLUGIN / codex["skills"]).is_dir())
        mcp = read_json(PLUGIN / codex["mcpServers"])
        self.assertIn("Grunt", mcp["mcpServers"])

    def test_marketplaces_list_the_same_plugins(self):
        claude = read_json(ROOT / ".claude-plugin" / "marketplace.json")
        codex = read_json(ROOT / ".agents" / "plugins" / "marketplace.json")
        self.assertEqual(claude["name"], codex["name"])
        claude_paths = {p["name"]: p["source"] for p in claude["plugins"]}
        codex_paths = {p["name"]: p["source"]["path"] for p in codex["plugins"]}
        self.assertEqual(claude_paths, codex_paths)
        for path in claude_paths.values():
            self.assertTrue((ROOT / path).is_dir(), path)


class SkillTests(unittest.TestCase):
    def test_skill_names_match_folders(self):
        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            match = re.search(r"^name: (\S+)$", text, re.MULTILINE)
            self.assertIsNotNone(match, skill.name)
            self.assertEqual(match.group(1), skill.name)

    def test_connection_check_is_identical(self):
        sections = {s.name: connection_section(s / "SKILL.md") for s in SKILLS}
        first = next(iter(sections.values()))
        for name, section in sections.items():
            self.assertEqual(section, first, name)

    def test_connect_md_is_identical(self):
        texts = {s.name: (s / "CONNECT.md").read_text(encoding="utf-8") for s in SKILLS}
        first = next(iter(texts.values()))
        for name, text in texts.items():
            self.assertEqual(text, first, name)

    def test_skill_docs_are_host_neutral(self):
        for skill in SKILLS:
            for doc in skill.glob("*.md"):
                if doc.name == "CONNECT.md":
                    continue
                text = doc.read_text(encoding="utf-8")
                for phrase in HOST_SPECIFIC:
                    self.assertNotIn(phrase, text, f"{skill.name}/{doc.name}")


if __name__ == "__main__":
    unittest.main()
