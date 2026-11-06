# GHCR publishing and release flow

Repository image: `ghcr.io/nooblk-98/temp-file-share`. Docker Hub is not used.

## Development commits

[Publish development image](../.github/workflows/publish-development.yml) runs on every push to `development`, with no workflow-wide cancellation/coalescing. Each successful commit passes reusable CI, builds linux/amd64 + linux/arm64, publishes `development-sha-<full SHA>`, and smoke-tests the published digest before channel promotion.

Only the current development branch head can move the `development` tag. Promotion is serialized; superseded builds keep their SHA tag and skip channel movement. A failed verification/build does not replace the last tested channel image.

## Stable releases from main

[Publish release image](../.github/workflows/publish-release.yml) runs when a stable GitHub release is published. Ordinary `main` pushes run CI but do not publish a stable image or trigger deployment.

1. Validate a published non-draft, non-prerelease `vX.Y.Z` tag and prove its commit is an ancestor of `main`.
2. Check out and test that exact release commit, not whatever main happens to contain later.
3. Publish version tags (`vX.Y.Z`, `X.Y.Z`) and smoke-test the published image digest.
4. Promote `live` and `latest` only if the release is still GitHub's latest stable release. A backfill of an older release cannot roll back the live channel.
5. Call the main Portainer webhook only after promotion succeeds.

Manual dispatch with an existing stable release tag can retry/backfill a release. It does not create, edit, or move Git tags. Digest pinning is the immutable reference; names such as version tags are registry tags and remain subject to repository-owner permissions.

## Authentication and metadata

Workflows use `GITHUB_TOKEN` with `contents: read` and `packages: write`. No Docker Hub PAT or new long-lived GHCR secret is required. The existing public package is linked to this repository through the OCI source label. If publishing is moved to a new package, configure its Actions access and public visibility before promising anonymous pulls.

The shared [image build workflow](../.github/workflows/build-image.yml) uses official Docker Actions pinned to full commit SHAs, Buildx/QEMU, channel-scoped build caches, OCI version/revision/source labels, provenance, and SBOM attestations. It does not claim cryptographic image signing.

## Release procedure

- Send focused work through a PR into `development` and let its image publish.
- Promote reviewed changes through a PR from `development` into `main` and wait for CI.
- Bump `app/pyproject.toml` and update `RELEASE_NOTES.md` for the chosen version before tagging.
- Publish a GitHub release from the resulting main commit with a matching `vX.Y.Z` tag.
- Verify publishing, channel tags/digests, registry access, and the intended Portainer stack/public route.

Portainer webhook credentials remain repository Actions secrets. Image publication and container-health checks are separate outcomes; a successful webhook only acknowledges deployment acceptance.
