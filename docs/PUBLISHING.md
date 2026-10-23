# Publishing the website with GitHub Pages

The archive includes a complete static website and a [GitHub Actions deployment workflow](../.github/workflows/pages.yml). No external map service, build framework, API key or paid hosting plan is required for this public repository.

**The site is live at [ding-ding-projects.github.io/go-bus-history-maps](https://ding-ding-projects.github.io/go-bus-history-maps/).** The [first deployment](https://github.com/Ding-Ding-Projects/go-bus-history-maps/actions/runs/40028694022) succeeded on 23 October 2026. The live homepage, search, route 52 historical map and representative PDF/CSV downloads were verified after deployment. The initial-activation instructions below are for setting up a new copy or restoring a disabled Pages configuration.

## Initial activation

A repository administrator or maintainer needs to select **Settings → Pages → Build and deployment → Source → GitHub Actions** once. The normal workflow token can deploy an enabled site; it cannot create the initial Pages configuration.

If a workflow ran before activation and stopped at **Configure Pages**, rerun that workflow after selecting GitHub Actions. Otherwise, the next push to `main` starts deployment. The workflow also supports **Actions → Deploy GO Bus History Maps → Run workflow**.

The project URL is:

**https://ding-ding-projects.github.io/go-bus-history-maps/**

For subsequent updates, a successful deployment requires both a successful workflow and the expected content at the public URL.

## What gets published

The workflow copies the homepage, `.nojekyll`, `assets/`, `data/`, `routes/`, `legacy/`, `pdfs/` and `docs/`, plus available top-level documentation and the custom error page, into a temporary `_site/` directory. It uploads that directory with GitHub's Pages artifact action and deploys it to the `github-pages` environment. Git history, working files and generation scripts are excluded from the website artifact; the scripts remain available in the repository.

All route pages and downloads retain their repository paths. The complete set of route PDFs is published with the website. The workflow's permissions are limited to `contents: read`, `pages: write` and `id-token: write`.

## Updating the site

Edit the website or archive files and commit to `main`. GitHub Actions deploys the new version automatically after initial activation. For research or generator changes, follow [the contribution guide](CONTRIBUTING.md) and preserve source attribution.

Run locally with:

```sh
python -m http.server 8000
```

Then visit `http://localhost:8000`. Opening `index.html` directly with a `file://` URL can prevent JSON loading.

## Official references

- [Configure a GitHub Pages publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
- [Create a custom GitHub Actions workflow for Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [Official static-site workflow template](https://github.com/actions/starter-workflows/blob/main/pages/static.yml)
- [Configure Pages action and its enablement requirements](https://github.com/actions/configure-pages)
