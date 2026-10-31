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

The Linux amd64 Xvfb image also installs the optional CloakBrowser Python wrapper (MIT) and its locked Python dependencies, including Playwright (Apache-2.0), for the experimental runtime installer. Their package license notices remain in the runtime virtual environment. No CloakBrowser or Playwright browser binary is downloaded during the image build.

CloakBrowser's compiled browser is separately licensed by CloakHQ and is **not** covered by the wrapper's MIT license. The opt-in installer obtains it from official channels into the deployment's private volume, preserving the original distribution files and notices. Do not redistribute that volume or include its contents in public images without the required separate permission. See the [upstream Binary License](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md) and the [experimental runtime guide](./docs/guides/cloak-experimental.md).

The runtime images also install additional third-party packages from the base distribution package repositories, such as Chromium, Openbox, Supervisor, ImageMagick, and related system libraries and utilities. Each component remains licensed under its own terms.

Before distributing built images externally, review the image contents and confirm that your distribution process satisfies the notice, attribution, and source-code obligations for all included components.

## Optional managed Camoufox adapter

The optional runtime installs the MIT-licensed Python [camoufox-cli](https://github.com/Bin-Huang/camoufox-cli) 0.7.6 and [Camoufox](https://github.com/daijro/camoufox) Python wrapper 0.4.11, with Playwright 1.52.0 (Apache-2.0). Installed packages retain their upstream license metadata. Exact Python versions are listed in `docker/camoufox-requirements.txt`; they are not relicensed under Verge's MIT license.

The separately downloaded Camoufox browser is MPL-2.0 with additional third-party components and notices (including LGPL Cursory and separately licensed fonts). It is not bundled by this image. Public redistribution of a browser-containing image is not cleared; see `docs/guides/camoufox.md` before shipping artifacts. No npm camoufox-cli or camoufox-js dependency is added to Verge.
