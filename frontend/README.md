# SLAI Miner SN67 frontend

This directory contains the read-only, single-page observability UI for the SLAI-powered Harnyx SN67 Miner engineering environment.

## Architecture

The browser does not parse Harnyx reports or read SQLite directly. `app/api/dashboard/route.ts` invokes the repository-root `dashboard_api.py` bridge, which reads already-normalized `BenchmarkStore` state, artifact manifests, and pinned dependency status. Missing benchmark evidence is rendered as an explicit empty state; no benchmark values are synthesized.

The UI intentionally mirrors BIMAP's product-family conventions: fixed blurred header, restrained black/off-white/yellow palette, Segoe UI/Cascadia Mono typography, thin separators, numbered side navigation, 980px/680px responsive breakpoints, compact dark footer, and the same persistent system-aware light/dark theme pattern.

## Development

From `frontend/`:

```powershell
npm install
npm run dev
```

The API route expects the Miner repository one directory above `frontend/`. By default it uses the existing Miner uv environment through `uv run --project .. --no-sync python`; run the normal Miner `uv sync` first. Set `MINER_PYTHON` to an explicit interpreter path if a different Python environment should execute `dashboard_api.py`.

Validation:

```powershell
npm run typecheck
npm run lint
npm run build
```

The frontend is observability-only. It contains no wallet management, subnet registration, TAO transfer, or artifact submission controls.
