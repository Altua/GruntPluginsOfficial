# Agent instructions

## Commits and pull requests

- Never add AI attribution. No `Co-Authored-By` trailers in commit messages, and
  no "Generated with Claude Code" or similar lines in commit messages, pull
  request titles or descriptions, or review comments.

## Changing the plugin

Follow the **Maintainers** checklist in [README.md](README.md): bump `version` in
both plugin manifests, keep the connection check and `CONNECT.md` identical in
both skills, and run the validation and tests listed there before pushing.
