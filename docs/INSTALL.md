# Install the development preview

1. Build with `python tools/build_plugin.py` in an environment with the dev extras.
   Run `python tools/stage_plugin.py <release.zip>` before local installation.
   This creates an allowlisted runtime-only source at `work/local-plugin`; never
   point installation at the entire private development checkout.
2. Extract the ZIP to an empty directory. The archive root is the plugin root:
   it contains `plugin.json`, `skills/`, and the referenced resources.
3. Add it to a local marketplace using the official package guide. This checkout
   includes `.agents/plugins/marketplace.json` pointing to that clean local stage.
4. With a Codex CLI that exposes plugin installation, run:

   ```powershell
   codex plugin marketplace add <absolute-path-to-this-checkout>
   codex plugin add bc-application-assistant@bc-application-dev
   codex plugin list --marketplace bc-application-dev --json
   ```

   Alternatively install from the local source in the desktop Plugins Directory.
   The desktop app may need a refresh/restart and a new chat to discover changes.
5. Invoke `bc-application` in a local desktop Work/Codex task. A missing PSR must
   produce a stop, not website access. The preview exposes three-system page planning and the documented
   host-tool relay; inspect its support limits before attempting a real page.
6. With Windows x64 Python 3.12, run the installed skill's `scripts/bootstrap.py
   --runtime-dir <chosen-empty-runtime-directory>` for offline PDF dependencies.
   Use that runtime's Python to run `scripts/run.py preflight` and `parse-psr`.

The marketplace catalog is for local testing; it is not required in the release ZIP.
Do not publish private source data or test-account details with the plugin.
