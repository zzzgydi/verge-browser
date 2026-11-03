import assert from 'node:assert/strict';
import { readFileSync, appendFileSync } from 'node:fs';

const expected = JSON.parse(readFileSync(`${process.env.PACKAGE_DIR}/package-metadata.json`, 'utf8'));
const url = `https://registry.npmjs.org/${expected.name}/${expected.version}`;

for (let attempt = 1; attempt <= 6; attempt++) {
  let response;
  let actual;
  let failure;
  try {
    response = await fetch(`${url}?write=true&t=${Date.now()}-${attempt}`, { signal: AbortSignal.timeout(10_000) });
    if (response.ok) actual = await response.json();
  } catch (error) {
    if (error instanceof SyntaxError) throw error;
    response = undefined;
    failure = `Registry request failed: ${error.message}`;
  }
  if (response?.ok) {
    assert.equal(actual.dist.integrity, expected.integrity, 'Published tarball differs from the verified artifact; do not republish this version');
    if (process.env.GITHUB_STEP_SUMMARY) {
      appendFileSync(process.env.GITHUB_STEP_SUMMARY, `Published **${expected.name}@${expected.version}**. Registry integrity matches the CI artifact.\n`);
    }
    break;
  }
  if (response) {
    const { status } = response;
    await response.body?.cancel();
    assert.ok(status === 404 || status === 429 || (status >= 500 && status < 600), `Registry verification failed: HTTP ${status}. Do not republish this version.`);
    failure = `Registry verification failed: HTTP ${status}`;
  }
  if (attempt === 6) {
    throw new Error(`${failure} after 6 attempts. Publish already finished; inspect the registry and CI artifact. Do not republish this version.`);
  }
  console.warn(`${failure} (attempt ${attempt}/6); retrying the registry read in 10 seconds`);
  await new Promise(resolve => setTimeout(resolve, 10_000));
}
