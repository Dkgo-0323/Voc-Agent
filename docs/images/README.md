# Screenshot provenance

Captured on 2026-10-23 from the repository's actual Next.js pages using headless
Chromium, at 1440 × 1050 CSS pixels with full-page capture. No generated artwork
or replacement UI was used. The application source was not modified for capture.

| File | Page | Data |
| --- | --- | --- |
| `overview-fixture.png` | `/overview` | Synthetic weekly overview based on `frontend/tests/overview-dashboard.test.tsx`: 12 reviews, 20 mentions, two SKUs. |
| `compare-fixture.png` | `/compare` | Synthetic same-tier pair based on comparison component test shapes; no evidence quotes or trend points. |

All `/api/*` calls, including session identity, are intercepted in the browser.
The local-storage marker is a dummy fixture string, not a real JWT. No database,
customer review corpus, provider credential, or model service is used. External
browser requests are blocked; the capture does not click Generate summary.
Comparison metrics are illustrative fixture values independent of the overview.
These pictures demonstrate the UI, not business conclusions or integration success.

## Reproduce

From the repository root after installing frontend dependencies and Chromium:

```powershell
Push-Location frontend
npm ci
npx playwright install chromium
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:18999"
$env:NEXT_TELEMETRY_DISABLED = "1"
npm run dev -- --webpack --hostname 127.0.0.1 --port 13123
```

In another repository-root terminal:

```powershell
node scripts/capture_readme.mjs
```

If Chromium is installed in a shared cache, set `PLAYWRIGHT_BROWSERS_PATH` to
that cache in the capture terminal. Webpack mode avoids a local Turbopack
PostCSS subprocess failure encountered during this capture. Stop the temporary
frontend after capture. The script fails on missing page content or browser
JavaScript errors and closes its browser on failure.
