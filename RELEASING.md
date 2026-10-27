# Releasing

`finanzen-zero-mcp` is published to PyPI by
[`.github/workflows/release.yml`](.github/workflows/release.yml). The pipeline is tag-driven, uses
PyPI [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC, no API token secret),
verifies the tag against the package version, and creates a GitHub release with the built artifacts.

## One-time setup

### PyPI

1. Sign in to <https://pypi.org> and open **Publishing** (or, before the first release, add a
   *pending publisher* for the not-yet-created project).
2. Add a GitHub publisher with exactly these values:

   | Field | Value |
   |---|---|
   | PyPI Project Name | `finanzen-zero-mcp` |
   | Owner | `wtfuii` |
   | Repository name | `zero-mcp` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

3. In the GitHub repository, open **Settings → Environments** and create an environment named
   `pypi`. Add required reviewers if you want a manual gate before every upload. Do not create a
   `PYPI_API_TOKEN` secret; the workflow does not use one.

### TestPyPI (recommended for dry runs)

Repeat the same steps at <https://test.pypi.org> with:

| Field | Value |
|---|---|
| PyPI Project Name | `finanzen-zero-mcp` |
| Owner | `wtfuii` |
| Repository name | `zero-mcp` |
| Workflow name | `release.yml` |
| Environment name | `testpypi` |

Create the corresponding `testpypi` environment in GitHub. A dry-run publish requires the project
name to be available on TestPyPI; use a unique pre-release version for each attempt.

## Version locations

The version is intentionally checked in two places and must match:

- `project.version` in [`pyproject.toml`](pyproject.toml) — the version that is uploaded.
- `zero_mcp.__version__` in [`src/zero_mcp/__init__.py`](src/zero_mcp/__init__.py) — the version the
  MCP server reports to clients.

The release workflow fails if these differ, if the project is not named `finanzen-zero-mcp`, or if a
tag push does not equal the version (with the leading `v` removed). Tags must use PEP 440 versions,
for example `v0.1.0`, `v0.2.0rc1`.

## Release checklist

1. Bump the version in both files above and refresh the lockfile:

   ```bash
   uv lock
   ```

2. Verify the tree exactly as the release workflow will:

   ```bash
   uv sync --locked
   uv run mypy .
   uv run pytest
   uv build
   uvx twine check --strict dist/*
   ```

3. Commit and push:

   ```bash
   git add pyproject.toml src/zero_mcp/__init__.py uv.lock
   git commit -m "Release v0.1.0"
   git push origin main
   ```

4. Create and push the annotated tag:

   ```bash
   git tag -a v0.1.0 -m "v0.1.0"
   git push origin v0.1.0
   ```

5. Open **Actions → Release** and watch the run. The `pypi` environment approval (if configured)
   gates the upload. On success the package is on PyPI and the workflow has created a GitHub release
   with the wheel and sdist attached.

## Dry run against TestPyPI

Before a first or risky release, run the same build and publish path manually:

1. Set a unique pre-release version in **both** version locations (for example `0.2.0rc1`) and run
   `uv lock`.
2. Open **Actions → Release → Run workflow**, choose the branch and target `testpypi`, and run it.
3. Install from TestPyPI to check the wheel and metadata:

   ```bash
   python -m venv /tmp/testpypi-smoke
   /tmp/testpypi-smoke/bin/pip install \
     --index-url https://test.pypi.org/simple/ \
     --extra-index-url https://pypi.org/simple/ \
     finanzen-zero-mcp==0.2.0rc1
   /tmp/testpypi-smoke/bin/python -c "import zero_mcp; print(zero_mcp.__version__)"
   ```

4. Restore the intended release version and continue with the checklist above. TestPyPI does not
   allow a version to be uploaded twice, so never reuse a dry-run version.

The manual dispatch also offers a `pypi` target for exceptional recovery. It still requires the
`pypi` environment approval, but normal releases should always go through a tag so the tested commit
and the published version are unambiguous.

## What the workflow does

1. **Verify and build** — checks out the ref, installs from the committed `uv.lock`, validates the
   project name/version/tag, runs `mypy --strict` and the offline test suite, builds the wheel and
   sdist, runs `twine check --strict`, smoke-installs the wheel in an isolated environment, and
   uploads the distributions as a workflow artifact.
2. **Publish** — downloads that exact artifact and uploads it with
   `pypa/gh-action-pypi-publish` using OIDC. No long-lived token is stored in GitHub.
3. **Create GitHub release** — on tag pushes only, attaches the wheel and sdist and generates release
   notes. Re-running the job is safe: an existing release gets the assets re-uploaded with
   `--clobber`.

## Failure handling

- **Before anything is uploaded:** fix the problem, delete the tag locally and remotely, and push it
  again:

  ```bash
  git tag -d v0.1.0
  git push origin :refs/tags/v0.1.0
  ```

- **After PyPI accepted the files:** a release is immutable. Bump to the next version; do **not**
  try to re-upload the same version. A failed GitHub-release step can be retried with
  **Re-run failed jobs**, and an existing release is updated in place.
