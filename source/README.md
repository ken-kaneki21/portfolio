# Reproducible UI source

Run `npm ci --no-audit --no-fund`, `npm run build`, and
`node scripts/preview.mjs`. The last command creates dist/preview.html for a
native-file preview. Keep dist together for evidence and PDF links.

The root repository serves the static site under /portfolio/. Rebuild and test
before copying dist files to the root in a review branch. The local browser
harness accepts dist, an output folder and an installed Chromium executable.
It records whether it used real loopback HTTP or static interception.

No model/API/backend is required for the UI. Install dependencies from the lock;
do not commit node_modules or private application documents.
