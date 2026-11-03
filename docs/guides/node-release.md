# Release the Node package with GitHub Actions

The npm package lives in `packages/node`. Publishing it does not deploy the API or browser runtime.
The current source version is **0.4.0**. It adds engine selection and managed Camoufox commands to the 0.3.0 package.

All releases run in GitHub Actions. Maintainers do not publish from a local machine.
Commit the reviewed source and workflow changes before using the workflow on that ref.

## Iterate through CI

Pushes and pull requests run the `CI` workflow.
Its `node-package` matrix checks Node 18, 20, 22, and 24 on Linux.
Each job installs locked dependencies, checks types, runs tests, and verifies the installed tarball.
Successful jobs upload one artifact per Node major version: `verge-browser-node-18`, `verge-browser-node-20`, `verge-browser-node-22`, and `verge-browser-node-24`.
Each artifact contains the tested tarball and its integrity metadata. The suffix is not the npm package version.
These jobs do not publish to npm and need no npm publishing credential.

`pack:check` runs `npm pack`, installs the tarball in a temporary consumer, and checks:

- SDK and CLI exports, plus TypeScript declarations under NodeNext resolution.
- Installed CLI version and help text.
- All three engine selectors and all eleven managed Camoufox commands.
- A failed command's nonzero exit code and absence of retries.

It uses an HTTP fixture inside the CI runner, not a real browser.
The `prepack` hook builds current source so a normal `npm pack` cannot silently reuse an old build.
After verification, `VERGE_PACKAGE_OUTPUT_DIR` receives `verge-browser.tgz` and `package-metadata.json`.
The release job publishes this exact tarball without rebuilding it.

## Validate the release workflow without publishing

1. Open **Actions > Release Node Package > Run workflow** in GitHub.
2. Select the reviewed branch in the **Branch** dropdown and enter its package version, currently `0.4.0`.
3. Leave **publish** unchecked and start the workflow.
4. Confirm that version checks, type checks, tests, and installed-package checks pass.
5. Download the `verge-browser-release` artifact if inspection is needed.

The default manual run stops after artifact upload. It does not call npm publish or require `NPM_TOKEN`.
This mode does not verify npm publishing permission or provenance generation. Those remain unverified until an authorized publish runs in Actions.
The workflow must exist on the default branch before GitHub exposes its manual trigger.
These steps describe the GitHub web interface. To publish a tag, use the tag-push trigger described below.

## Publish through GitHub

The workflow uses Node 24 and the repository's `NPM_TOKEN` secret.
Configure a valid npm token with write access to `verge-browser` and permission for non-interactive publishing.
If the npm account requires 2FA, the token must support CI publishing without an OTP prompt.
The `id-token: write` permission enables provenance; it does not replace npm authentication in this token-based workflow.

1. Confirm that CI passes on the reviewed commit and its package version is unused on npm.
2. Choose one trigger: run **Release Node Package** with the matching version and **publish** checked, or push the matching `verge-browser-v0.4.0` tag.
3. Confirm that package checks and artifact upload pass before the publish step.
4. Confirm that **Verify published package** passes and the job summary reports matching registry integrity.
5. Replace the pending-publication notes in the root READMEs, Node README, CLI guide, and Camoufox guide with the verified release status.

Tag pushes publish automatically after package checks. The manual `publish` switch applies only to manual runs.
A normal push to `main` never publishes the package.
The workflow rejects mismatched versions, mismatched tags, and prerelease versions. It publishes stable versions to `latest`.

If registry verification fails after npm publish succeeds, check the exact version on npm before doing anything else.
Keep the workflow artifact and its integrity metadata for comparison. Do not blindly rerun the publishing job or reuse the published version.
If the failure is limited to the registry check, verify the registry again; publishing is not a retry mechanism for that check.
The registry check makes at most six read requests, with a 10-second timeout per request and 10 seconds between retries.
It retries network failures, HTTP 404, HTTP 429, and HTTP 5xx. Other HTTP errors and integrity mismatches fail immediately.
Retries never repeat `npm publish`. Exhaustion fails the job and preserves the uploaded artifact for inspection.

## Separate runtime acceptance

The default CI does not download the Camoufox browser or run its real-runtime test.
Run the [Camoufox acceptance test](camoufox.md#acceptance-tests) in an environment with the optional runtime and separately installed browser.
Set `VERGE_TEST_NODE_CLI` to the absolute `node_modules/verge-browser/dist/src/cli.js` path in an independently installed consumer to test the packed Node client.
With that override, the Camoufox test uses Node for all CLI actions instead of its default Python/Node mix.
If a host proxy intercepts runtime traffic, exclude loopback and container hosts with `NO_PROXY` in the test process.
For this isolated test's local-only traffic, `NO_PROXY='*'` bypasses the proxy without changing system settings.

## Optional local diagnostics

Local checks are only for reproducing a CI failure. They do not publish:

Install Node.js 18 or newer, npm, and pnpm 9.5.0 on `PATH` before running these commands.
Install the package's development dependencies; do not use a production-only install for source builds.
Even `npm pack` calls pnpm through `prepack` and needs the local TypeScript compiler.
`pack:check` uses npm to install the tarball's dependencies, including `cac`, into a temporary consumer.
That install requires access to the configured npm registry; do not assume it works offline just because the repository has `node_modules`.

```bash
pnpm --dir packages/node install --frozen-lockfile
pnpm --dir packages/node check
pnpm --dir packages/node test
pnpm --dir packages/node pack:check
```

Failed package checks preserve the temporary consumer path printed in the log.
Local checks do not verify GitHub's npm credential, provenance, or remote publishing permission.
The registry verification script can also run outside Actions with `PACKAGE_DIR` set to the verified artifact directory.
Outside Actions, `GITHUB_STEP_SUMMARY` is optional. If absent or empty, only the summary write is skipped; registry and integrity checks still run.
