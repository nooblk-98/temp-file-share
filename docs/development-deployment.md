# Development deployment

[Deploy development to Portainer](../.github/workflows/deploy-development.yml) runs on pushes to `development`, or manually when that branch is selected. It first calls the reusable [CI workflow](../.github/workflows/ci.yml); only successful checks trigger the stack webhook. Feature-branch pushes and PRs do not deploy.

Configure the GitHub repository secret **`PORTAINER_DEVELOPMENT_WEBHOOK_URL`** with the development stack's webhook. Configure that Portainer Git stack to track **`refs/heads/development`**, use `docker-compose.yaml`, and rebuild the source when redeploying. The webhook requests a redeploy; it does not change the stack's Git ref or configuration. The existing `main` deployment workflow and its `DEPLOY_WEBHOOK_URL` secret are separate and unchanged.

No webhook URL is committed or printed. A successful webhook request means Portainer accepted it; confirm container health in Portainer after deployment.
