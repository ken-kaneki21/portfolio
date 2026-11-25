# Saurabh — data and LLM engineering portfolio

Live: https://ken-kaneki21.github.io/portfolio/

This repository contains the deployed static files at the root and reproducible
React/TypeScript source in `source/`. The root `.nojekyll` and existing branch-based
GitHub Pages source remain unchanged. No backend, API key or paid host is required.

## Rebuild
Use the pinned `source/package-lock.json` and an appropriate current Node runtime.
From `source/`: `npm ci --no-audit --no-fund`, `npm run build`, then
`node scripts/preview.mjs`. Initial dependency acquisition needs internet; the
source release does not contain node_modules. The build outputs `source/dist/`.

After testing, copy the generated dist files to the repository root in a review
branch and commit explicit paths. Preserve old assets/history and `.nojekyll`.
Do not upload private application resumes or raw health/host data.

## Case studies
- [Healthcare Claims Platform](https://github.com/ken-kaneki21/healthcare-claims-platform)
- [Job Intelligence](https://github.com/ken-kaneki21/job-portal)
- [EvidenceWorks](https://github.com/ken-kaneki21/EvidenceWorks)

All project measurements are scoped independent/local or synthetic experiments.
The site and public resume are intentionally contact-free. UI source is MIT;
retained notices cover bundled dependencies. Evidence is provenance, not a claim
of employer adoption, human baseline approval or production capacity.

`CLOSEOUT_RELEASE.json` identifies source revisions and the preceding deployed ref.
To roll back, review and ordinarily revert the promotion commit or re-deploy the
previous exact artifact as a new commit. Never force-push shared history.
