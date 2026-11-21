# Profile README setup

This package is prepared for the profile repository `greg-dev0/greg-dev0`. Nothing in this package has been pushed to GitHub.

## Files

- `README.md` — refreshed public profile README; no private project names are included.
- `assets/activity.svg` — initial placeholder, replaced by the workflow after setup.
- `scripts/generate_activity.py` — generates the custom baby-blue activity card.
- `.github/workflows/update-activity.yml` — refreshes the SVG daily and on manual workflow dispatch.

## Enable aggregate private contribution counts

1. Open your GitHub profile.
2. Open **Contribution settings** above the contribution calendar.
3. Enable **Private contributions**.

GitHub's GraphQL `ContributionsCollection` includes private/internal contribution counts when the authenticated token has the optional `read:user` scope and private contribution counts are enabled. The query in this package requests only the aggregate calendar, not repository names or contribution details.

## Create a read-only token

Create a **Personal access token (classic)** with only the `read:user` scope. Do not grant repository access. Store the token as a repository Actions secret; never put it in source files.

## Add the Actions secret

In `greg-dev0/greg-dev0`, go to **Settings → Secrets and variables → Actions → New repository secret**.

- Name: `CONTRIBUTIONS_TOKEN`
- Value: the token created above

## Allow the workflow to update the generated SVG

In **Settings → Actions → General → Workflow permissions**, allow the repository's `GITHUB_TOKEN` to have read and write permissions. The workflow itself requests only `contents: write`.

The workflow runs daily and can also be started manually from **Actions → Update activity card → Run workflow**. It commits only `assets/activity.svg` when the generated SVG changes.

## Local preview and validation

Requires Python 3.10+ and no third-party packages:

```bash
python scripts/generate_activity.py --sample --output /tmp/activity-preview.svg
```

The `--sample` mode uses synthetic values strictly for preview. The real workflow does not use sample data.

## Privacy

- The GraphQL query reads only the authenticated user's aggregate contribution calendar, `hasAnyRestrictedContributions`, and `restrictedContributionsCount`.
- It does not query repositories, commit messages, pull request titles, issue titles, or source code.
- The public SVG reveals daily aggregate contribution counts, total contributions, streaks, and the busiest day. It does not identify which repositories generated those contributions.
- Daily activity can still reveal work patterns. Publish the card only if you are comfortable sharing aggregate activity.
- The token is stored in GitHub Actions Secrets and is never written to the generated SVG.
