# SLAI Miner SN67 frontend

This directory contains the read-only, single-page observability UI for the
SLAI-powered Harnyx SN67 Miner engineering environment.

## Architecture

The browser does not parse Harnyx reports or read SQLite directly.
`app/api/dashboard/route.ts` invokes the repository-root `dashboard_api.py`
bridge once per dashboard request. The route validates the
`slai-miner-dashboard-v1` envelope before forwarding it. The Python bridge reads
already-normalized `BenchmarkStore` state through its read-only public API,
artifact manifests, and pinned dependency status.

Missing benchmark evidence is an explicit empty state; no benchmark values are
synthesized. Backend failures return a sanitized 503 response to the browser
while the detailed failure remains server-side.

The UI intentionally mirrors BIMAP's product-family conventions: fixed blurred
header, restrained black/off-white/yellow palette, Segoe UI/Cascadia Mono
typography, thin separators, numbered side navigation, 980px/680px responsive
breakpoints, compact dark footer, and the same persistent system-aware
light/dark theme pattern.

## Development

From `frontend/`:

```powershell
npm install
npm run dev
```

By default the API route treats the parent directory as the Miner repository
and executes:

```text
uv run --project <miner-root> --no-sync python dashboard_api.py --json
```

Set `MINER_ROOT` to an explicit Miner checkout when the frontend is launched
from another working directory. Set `MINER_PYTHON` to an explicit interpreter
when a different Python environment should execute `dashboard_api.py`.

Validation:

```powershell
npm run typecheck
npm run lint
npm run build
```

The frontend is observability-only. It contains no wallet management, subnet
registration, TAO transfer, or artifact submission controls.
