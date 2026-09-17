# Website-only deployment

Verified 2026-09-17. The current production scope is the public website only.

## Ownership

- `skatelab.ru` routes to the standalone `skatelab-site` Dokploy application in
  the SkateLab production environment, with HTTPS and internal port 3000.
- Git source is `master`, using [frontend/Containerfile](../frontend/Containerfile)
  with `frontend` as the Docker build context. Deploy manually through Dokploy;
  application AutoDeploy is currently disabled.
- The retired SkateLab Compose resource (backend, fast worker, heavy worker) was
  deleted through Dokploy with volume deletion explicitly disabled.
- Shared databases, storage, networks, and other projects remain outside this
  deployment's ownership. Do not remove them when changing the website.
- [The legacy full-stack workflow](../.github/workflows/deploy.yml) is now
  manual-only. Do not run it for website releases.

## Release evidence

- Deployed source: `8195a1ddeb8f4279d4d2e88a461b3b2a85912f08`.
- Runtime image: `sha256:5c1c96afc28da5f6307fe14322faf4517c937a9418565ecd5f8965416246d02c`.
- Dokploy deployment completed; Swarm has 1/1 replicas, a healthy container,
  and zero restarts at verification.
- Strict HTTPS returned 200 for `/`, `/how-it-works`, `/equipment`, `/contact`,
  `/blog`, `/privacy`, and `/terms`. All 28 homepage assets checked returned 200.
- All 31 unrelated containers retained their IDs, images, and start times.
  Every pre-existing Docker volume remained present.

## Recovery

For a failed future website release, restore the last verified frontend source
in Git and deploy only the existing website application through Dokploy.
Verify the new deployment record, source revision, image, container health,
HTTPS pages, and static assets. Do not enqueue duplicate deployments.

Do not resurrect the old backend or workers as a website rollback. Restoring
that stack requires separate authorization and a new Dokploy resource from
its tracked infrastructure Compose source; credentials must come from the
existing secret store, never this document. Preserve shared volumes throughout.
