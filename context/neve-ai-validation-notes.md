- 2026-05-02: `npm run check` fails on pre-existing unrelated Svelte/TS issues in `src/routes/auth/+page.svelte` and `src/routes/(app)/workspace/tools/edit/+page.svelte`; source file `get_errors` checks and `npm run build` are better signal for scoped frontend changes until those are fixed.
- 2026-05-04: Windows installer pip exit 3 can come from user/global pip env/config; installer should log `$INSTALLER_REVISION`, remove `PIP_REQUIRE_VIRTUALENV`, set `PIP_CONFIG_FILE=NUL`, use `python -I -m pip --isolated`, try venv `pip.exe`, and repair with official `get-pip.py` before failing. Logs without the revision line mean the target PC ran an old copy.
- 2026-05-04: Installer runtime is intentionally minimal; optional web/audio/OCR deps like `ddgs`, `black`, `pydub`, `rapidocr`, `onnxruntime` are excluded from `requirements-runtime.txt`. Requirements failures are logged to `logs/python-dependencies-pending.txt` and later runs preserve venv/skip installed packages.
- 2026-05-04: Frontend install must use Node 18-22 because `.npmrc` has `engine-strict=true`; Node 24 + npm 11 fails. Installer revision `2026-05-04-node22-frontend-v5` downloads/uses portable Node 22 under `tools/nodejs` and rejects Node >22 for frontend npm steps.
- 2026-05-04: Root `.gitignore` pattern `models/` ignored every directory named models/Models, including `backend/neveai/models`, retrieval models, and frontend Models folders. This caused releases to miss code and startup to fail with `ModuleNotFoundError: neveai.models`. Use `/models/` for the downloaded model folder, ignore venvs explicitly, and ensure code models folders are tracked.

- 2026-05-07: `buildar.ps1` should resolve `tools/nodejs/node.exe` + `npm.cmd` first, download Node 22 portable if missing, use `npm install --no-audit --no-fund` when frontend deps are absent, then clean `build/`, run `npm run build`, and sync to `backend/neveai/frontend`.




