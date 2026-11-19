# Contributing / Branch Workflow

`main` is always the stable, working version. Nothing is committed to it directly.
Every change gets its own short-lived branch and is merged through a pull request (PR).

## 1. Branch naming

`<type>/<short-description>`, lowercase, hyphen-separated.

| Type | Use for | Example |
|---|---|---|
| `feat/` | new functionality | `feat/dashboard-alert-panel` |
| `fix/` | bug or security fix | `fix/api-authentication` |
| `refactor/` | restructure, no behavior change | `refactor/firmware-single-codebase` |
| `test/` | tests only | `test/api-analyze-endpoint` |
| `ci/` | pipelines, tooling | `ci/github-actions` |
| `docs/` | documentation only | `docs/user-manual-wiring` |
| `chore/` | dependencies, config, cleanup | `chore/split-requirements` |

One branch = one purpose. If a branch touches two unrelated things, split it.

## 2. Day-to-day flow

```bash
git switch main
git pull                          # start from the latest main
git switch -c fix/api-authentication

# ...edit, test...
git add -p                        # stage deliberately, review what goes in
git commit -m "fix(api): require API key on /analyze and /dispatch"

git push -u origin fix/api-authentication
```

Then open a PR into `main` on GitHub. Review your own diff before merging, merge,
and delete the branch (`git branch -d <name>`).

## 3. Commit messages

Follow the style already used in this repo: `type(scope): summary`.

Scopes match the folders: `api`, `ai`, `firmware`, `dashboard`, `clinical`, `hardware`, `docs`, `core`.

Example: `feat(dashboard): add acknowledge button to alert feed`

## 4. PR rules

- Keep PRs small and about one thing.
- Describe what changed and why, and how you tested it.
- Use **squash merge** so each PR becomes one clean commit on `main`.
- Link the issue it closes (`Closes #12`).

## 5. Protect `main` (GitHub → Settings → Branches → Add rule for `main`)

- Require a pull request before merging
- Require status checks to pass (once CI exists)
- Block force pushes and deletion

## 6. Releases

Tag milestones on `main` so they can always be recovered:

```bash
git tag -a v0.1-thesis-defense -m "Version submitted for defense"
git push origin v0.1-thesis-defense
```

## 7. Hotfixes

Same flow, branched from `main`: `fix/<what>`. Merge quickly, then tag if it's a release.

## 8. Never commit

Credentials, `.env*`, `config.h`, datasets, or `firebase_credentials.json`.
They are git-ignored on purpose; only the `*.example` templates are tracked.
