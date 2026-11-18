# Deployment

`pages.yml` builds the complete MyST site and runs formula, heading, desktop/mobile HTML and reader interaction checks before publishing to GitHub Pages.

The source is `main`; the destination path is derived from the repository name. GitHub Pages must use GitHub Actions as its publishing source. A failed build or validation never uploads a deployment artifact.
