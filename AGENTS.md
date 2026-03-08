# Repository Guidelines

## Project Structure & Module Organization
- `tpconf_bin_xml.py` converts TP-Link backup files between `.bin` and `.xml`.
- `router_policy_route.py` is the main live-router tool for host-specific policy routing over the router telnet shell.
- `route_pc_auto.ps1` and `*_pc_route.cmd` are thin Windows wrappers around the Python routing workflow.
- `README.md` and the other root `*.md` files hold design notes and research.
- `TD-W9960*.bin` / `TD-W9960*.xml` plus `sshd*` are device artifacts; sanitize them before committing.
- `.venv/` and `__pycache__/` are local-only and should stay untracked.

## Build, Test, and Development Commands
```powershell
python tpconf_bin_xml.py -h
python -m py_compile tpconf_bin_xml.py router_policy_route.py
python router_policy_route.py ensure --target-ip 192.168.0.60 --ppp-if auto --dry-run
pwsh -NoLogo -ExecutionPolicy Bypass -File .\route_pc_auto.ps1 status
```
- Use `py_compile` as the minimum syntax gate for Python edits.
- Prefer `--dry-run` for routing changes; it prints commands without touching the router.
- `route_pc_auto.ps1 status` is read-only but still needs the router shell to be reachable.

## Coding Style & Naming Conventions
- Python uses 4-space indentation, snake_case names, small helper functions, and explicit type hints for new code.
- Prefer stdlib-first implementations; keep third-party dependencies narrow and justified.
- PowerShell wrappers should stay minimal: validated parameters, `$ErrorActionPreference = "Stop"`, then delegate to Python.
- Preserve exported backup filenames exactly; use descriptive snake_case for new scripts.

## Testing Guidelines
- There is no formal test suite yet.
- For Python changes, run `python -m py_compile ...` and at least one safe CLI verification step.
- For router-affecting changes, validate with `--dry-run` first, then `status`; avoid committing raw live output with public IPs or credentials.
- Put any future automated tests in a top-level `tests/` folder, not inside `.venv/`.

## Commit & Pull Request Guidelines
- Current history only contains `Initial commit`; use short, imperative subjects such as `router: add ensure dry-run`.
- Keep commits scoped to one concern: router logic, wrapper scripts, docs, or fixture updates.
- PRs should list changed files, validation commands run, impacted router model/firmware, and rollback notes.
- Include redacted before/after snippets for routing changes; use screenshots only for docs or diagrams.

## Security & Configuration Tips
- Never commit PPPoE credentials, public IPs, OAuth tokens, telnet host keys, or unsanitized router backups.
- Treat `TD-W9960*.xml` as sensitive config dumps and redact shell payloads or account data before sharing.
- Prefer dry runs before any live `apply` or `ensure` execution on the router.
