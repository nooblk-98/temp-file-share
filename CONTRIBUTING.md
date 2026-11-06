# Contributing

Contributions are welcome. Small improvements to documentation, accessibility, reliability, performance, and tests are useful too.

## Before opening a PR

- Search existing issues and pull requests to avoid duplicate work.
- Explain the problem and intended behavior; discuss larger changes in an issue before implementing them.
- Keep the change focused and preserve the existing light/dark design, upload/API behavior, storage compatibility, and container hardening unless the change explicitly addresses them.
- Never commit credentials, webhook URLs, real uploads, or production metadata. Use synthetic test files.

## Local setup

```bash
git clone https://github.com/nooblk-98/temp-file-share.git
cd temp-file-share
git switch development
git switch -c fix/short-description
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r app/requirements.txt ruff==0.17.4
```

Python 3.11+ is required. Docker Compose is needed for deployment-configuration checks. See [testing](docs/testing.md) for full backend/browser commands and [source builds](docs/deployment.md#build-and-run-from-source) for running the app locally.

## Submit a change

1. Add a regression test for a security, data-integrity, or behavioral fix; avoid tests that merely mirror trivial implementation details.
2. Run the relevant checks. For UI work, test narrow/wide layouts and both themes and include real before/after screenshots using synthetic data.
3. Update user-facing docs and release notes when behavior/configuration changes.
4. Open a pull request against `development` with a clear summary, reproduction steps, tests performed, and any migration notes. Maintainers promote tested changes into `main` for a release.

Fork PRs run checks without registry credentials and do not publish images. Image publishing is a maintainer workflow on the trusted branches/releases.

For bug reports, include version/tag, deployment method, expected/actual behavior, and sanitized logs. For security issues, use GitHub private vulnerability reporting when available rather than publishing sensitive details.

## License

By contributing, you agree that your contribution is provided under the repository's [AGPL-3.0 license](LICENSE).
