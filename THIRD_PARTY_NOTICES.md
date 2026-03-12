# Third-Party Notices

This repository's original source code is licensed under the MIT License unless a subdirectory or file states otherwise.

Distributed artifacts built from this repository, especially container images, may include third-party software under separate open-source licenses. Those components are not relicensed under MIT and remain subject to their original license terms.

## Xpra

- Component: Xpra
- Upstream: https://github.com/Xpra-org/xpra
- License: GPL v2 or later
- Repository usage: the `runtime-xpra` image installs and runs Xpra to provide the HTML5 remote session stack for `kind="xpra"` sandboxes
- Image definition: `docker/runtime-xpra.Dockerfile`

The source code for Xpra is available from its upstream project. If you distribute binaries or container images that include Xpra, you are responsible for complying with the GPL for the included Xpra version, including providing corresponding source code for that distributed version and any modifications to Xpra, if applicable.

## Other Runtime Dependencies

The runtime images also install additional third-party packages from the base distribution package repositories, such as Chromium, Openbox, Supervisor, ImageMagick, and related system libraries and utilities. Each component remains licensed under its own terms.

Before distributing built images externally, review the image contents and confirm that your distribution process satisfies the notice, attribution, and source-code obligations for all included components.
