# Release process

Releases are built and published by GitHub Actions
([`.github/workflows/release.yml`](../.github/workflows/release.yml)) whenever
`main` contains a version that has not been released yet. There is no manual
tagging: the workflow creates the `vX.Y.Z` tag together with the release.

1. Bump `__version__` in `src/sieve/__init__.py` following
   [Semantic Versioning](https://semver.org/):
   - **patch** (`0.1.1`) — bug fixes only
   - **minor** (`0.2.0`) — new tools or features
   - **major** (`1.0.0`) — breaking changes to settings or behaviour
2. In `CHANGELOG.md`, move the `[Unreleased]` entries into a new
   `## [x.y.z] - YYYY-MM-DD` section and update the links at the bottom.
3. Commit `chore(release): vX.Y.Z` and push to `main`.

Pushes that do not change the version are ignored by the release workflow.
For a new version it:

1. runs lint and tests,
2. builds `Sieve.exe` with PyInstaller and runs it with `--smoke-test`,
3. builds `Sieve-Setup-X.Y.Z.exe` with Inno Setup,
4. creates the `vX.Y.Z` tag and the GitHub release, using the CHANGELOG section as release notes.

Installed copies of Sieve pick the new release up on their next start.

## Installer details

- The installer `AppId` in `installer/sieve.iss` identifies the installation for
  upgrades and must never change.
- Updates run the installer with `/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS`;
  the running app is closed, files are replaced and the new version starts automatically.
