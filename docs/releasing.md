# Release process

Releases are built and published by GitHub Actions
([`.github/workflows/release.yml`](../.github/workflows/release.yml)) whenever a
version tag is pushed.

1. Bump `__version__` in `src/sieve/__init__.py` following
   [Semantic Versioning](https://semver.org/):
   - **patch** (`0.1.1`) — bug fixes only
   - **minor** (`0.2.0`) — new tools or features
   - **major** (`1.0.0`) — breaking changes to settings or behaviour
2. In `CHANGELOG.md`, move the `[Unreleased]` entries into a new
   `## [x.y.z] - YYYY-MM-DD` section and update the links at the bottom.
3. Commit: `chore(release): vX.Y.Z`.
4. Tag and push:

   ```bash
   git tag -a vX.Y.Z -m "Sieve X.Y.Z"
   git push origin main vX.Y.Z
   ```

The workflow then:

1. verifies that the tag matches `__version__`,
2. runs lint and tests,
3. builds `Sieve.exe` with PyInstaller and runs it with `--smoke-test`,
4. builds `Sieve-Setup-X.Y.Z.exe` with Inno Setup,
5. creates the GitHub release with the CHANGELOG section as release notes.

Installed copies of Sieve pick the new release up on their next start.

## Installer details

- The installer `AppId` in `installer/sieve.iss` identifies the installation for
  upgrades and must never change.
- Updates run the installer with `/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS`;
  the running app is closed, files are replaced and the new version starts automatically.
