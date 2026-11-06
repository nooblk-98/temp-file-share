# Development deployment automation

[Publish development image](../.github/workflows/publish-development.yml) builds every successful development commit regardless of whether a development stack is configured.

Automatic development deployment is opt-in:

1. Create a separate Portainer Git stack tracking `refs/heads/development`, using `docker-compose.dev.yaml`, and enable re-pulling its GHCR image on redeploy.
2. Verify its project/container/storage/port are separate from the live stack. Preserve any required private bind and exact proxy-trust settings as stack environment variables.
3. Put that stack's webhook in repository Actions secret `PORTAINER_DEVELOPMENT_WEBHOOK_URL`.
4. Set repository Actions variable `PORTAINER_DEVELOPMENT_ENABLED=true` only after verifying the webhook targets that separate stack.

Until then, images still publish, but the development deploy job is skipped. Do not reuse the live stack's webhook: branch-triggered publication must not redeploy production.

Stable deployment is called by the release image workflow after `live` is promoted, using `DEPLOY_WEBHOOK_URL`. The stable Portainer Git stack tracks `main`, uses `docker-compose.yaml`, and re-pulls the image. A push to main alone does not publish or deploy a stable image.

The [reusable deployment workflow](../.github/workflows/deploy-development.yml) accepts its webhook only as a secret, never commits/prints it, and suppresses the response body. HTTP success is acceptance, not proof the stack or public hostname is healthy.
