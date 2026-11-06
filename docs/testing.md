# Testing and CI

```bash
python -m pip install -r app/requirements.txt ruff==0.17.4
ruff check app tests
python -m unittest discover -s tests -v

cd tests/browser
npm ci
npx playwright install chromium
PYTHON=python npm test
```

CI runs regression tests on Python **3.11–3.14**, a hardened Docker upload/download smoke test plus isolated round trips through all three Compose configurations, and Chromium workflow/responsive checks at **320, 390, 768, 1024, and 1440 px**, in light and dark themes. Image publishing is documented in [GHCR publishing](image-publishing.md). Images include provenance and SBOM attestations; cryptographic signing and automatic GitHub release creation are not configured.
