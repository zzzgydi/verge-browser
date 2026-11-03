# Open Source Compliance Notes

This document defines the repository's intended license boundary. It lists minimum compliance steps for distributing runtime images with third-party open-source software.

## License Boundary

- The repository's original source code is licensed under MIT unless a file or directory states otherwise.
- Third-party software installed into runtime images is not relicensed under MIT.
- Container images are combined distributions that may contain software under GPL, LGPL, Apache, BSD, MIT, and other licenses at the same time.

## Xpra-Specific Impact

The `runtime-xpra` image installs Xpra from the distribution package repository in [`docker/runtime-xpra.Dockerfile`](../docker/runtime-xpra.Dockerfile).

Xpra uses GPL v2 or later. If you distribute an Xpra image outside your organization, treat it as a GPL-relevant distribution.
Recipients must have access to the corresponding source for the exact included Xpra version. This includes your modifications to Xpra.

## Distribution Checklist

Use the following checklist before publishing `runtime-xpra` images to customers, partners, or public registries:

1. Keep the repository MIT license notice for original project code.
2. Include [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) with the distributed source tree or release materials.
3. State clearly that the `runtime-xpra` image contains Xpra and that Xpra remains licensed under GPL v2 or later.
4. Preserve upstream copyright and license notices for included third-party components.
5. Provide the corresponding source for the exact included Xpra version, including your modifications.
6. Re-check other image packages for additional notice or source obligations before external distribution.

## Operational Guidance

- If you distribute only repository source, retain the MIT license and third-party notices. The notices explain the image components to downstream users.
- If you publish prebuilt `runtime-xpra` images, record the exact Xpra package version. Retain the matching source package or provide an equivalent compliant source distribution path.
- Do not describe the entire shipped image as "MIT licensed". Only the repository's original code is MIT licensed.

## Not Legal Advice

These notes are engineering compliance guidance for this repository, not legal advice. For commercial external distribution, have counsel review your release process.

## Optional Camoufox Runtime

The Camoufox image contains the pinned Python command engine. It does **not** contain the browser artifact.
Operators mount a separately obtained browser read-only.

This arrangement does not authorize redistribution of the browser, bundled fonts, or all dependencies.
Before publishing an image with a browser, review that artifact's notices, source obligations, and font licenses.
See [Camoufox's setup and license boundary](guides/camoufox.md).

Distribution-package obligations also apply to the runtime without a browser binary.
