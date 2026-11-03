# Plugin index

`index.json` is a DSH plugin index in format 1. It lets DSH discover this plugin without knowing
the npm name in advance.

Public URL:

```text
https://raw.githubusercontent.com/zzzgydi/verge-browser/main/packages/dsh-plugin/market/index.json
```

## Use it in DSH

1. Open **Plugins** and switch on **Custom plugin indexes** under **Experimental plugins**.
2. Open **Discover** and choose **Add index source**.
3. Paste the public URL above.

DSH lists `0.1.0` only while npm serves that version and the running DSH satisfies
`engines.dsh`. A malformed index shows its error, with the JSON path, under the source in
**Manage index sources…**.

## Update it after a release

1. Publish the package first. The index must never list a version that npm does not serve.
2. Add the new version to `versions` with the npm publish time in Unix seconds, for example
   `npm view dsh-plugin-verge-browser time.0.1.1`.
3. Point `dist-tags.latest` at the new version.
4. Copy the manifest's `engines.dsh` unchanged. A version without a valid range is dropped.
5. Keep `title`, `description`, and `icon` in step with the highest listed version.

The icon is the package's own `../icon.svg`, referenced relative to the index URL. One artwork
serves the npm package, the project README, and this index, so there is no copy to keep in step.

## Fields that differ from the package manifest

Each version's `engines.dsh` must match that published version's manifest, not the current
development manifest. The index is not generated. Leave `0.1.0` at `0.2.1-rc.2`.
After publishing `0.1.1`, add its version with `engines.dsh: "^0.2.0"` and its actual npm timestamp,
then update `dist-tags.latest`. Do not list the unreleased version in advance.
