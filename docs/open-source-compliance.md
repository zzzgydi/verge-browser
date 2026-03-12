# Open Source Compliance Notes

This document defines the intended license boundary for this repository and the minimum compliance steps for distributing runtime images that contain third-party open-source software.

## License Boundary

- The repository's original source code is licensed under MIT unless a file or directory states otherwise.
- Third-party software installed into runtime images is not relicensed under MIT.
- Container images are combined distributions that may contain software under GPL, LGPL, Apache, BSD, MIT, and other licenses at the same time.

## Xpra-Specific Impact

The `runtime-xpra` image installs Xpra from the distribution package repository in [`docker/runtime-xpra.Dockerfile`](../docker/runtime-xpra.Dockerfile).

Xpra is licensed under GPL v2 or later. If you distribute an image containing Xpra outside your organization, treat that image as a GPL-relevant distribution and make sure the recipient can obtain the corresponding source code for the included Xpra version and any modifications to Xpra that you made.

## Distribution Checklist

Use the following checklist before publishing `runtime-xpra` images to customers, partners, or public registries:

1. Keep the repository MIT license notice for original project code.
2. Include [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) with the distributed source tree or release materials.
3. State clearly that the `runtime-xpra` image contains Xpra and that Xpra remains licensed under GPL v2 or later.
4. Preserve upstream copyright and license notices for included third-party components.
5. Provide access to the corresponding source code for the exact Xpra version included in the distributed image, plus any modifications you made to Xpra, if any.
6. Re-check other image packages for additional notice or source obligations before external distribution.

## Operational Guidance

- If you only distribute repository source code and do not distribute built images, the repository-level MIT license notice is still correct, but third-party notices should remain in place so downstream users understand the image composition.
- If you publish prebuilt `runtime-xpra` images, keep a repeatable process to identify the exact Xpra package version in the image and retain the matching source package or an equivalent compliant source distribution path.
- Do not describe the entire shipped image as "MIT licensed". Only the repository's original code is MIT licensed.

## Not Legal Advice

These notes are engineering compliance guidance for this repository, not legal advice. For commercial external distribution, have counsel review your release process.
