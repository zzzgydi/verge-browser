import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const { name, version } = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
assert.equal(name, 'verge-browser');
assert.match(version, /^\d+\.\d+\.\d+$/, 'This workflow publishes stable versions to latest');
const { GITHUB_EVENT_NAME: event, GITHUB_REF_TYPE: refType, GITHUB_REF_NAME: refName, REQUESTED_VERSION: requested } = process.env;
assert.ok(event === 'push' || event === 'workflow_dispatch', 'Unsupported release event');
if (event === 'push') assert.equal(refType, 'tag', 'Publishing on push requires a release tag');
if (refType === 'tag') assert.equal(refName, `verge-browser-v${version}`, 'Release tag must match package.json');
if (event === 'workflow_dispatch') assert.equal(requested, version, 'Requested version must match package.json');
console.log(`${name}@${version}: release version matches`);
