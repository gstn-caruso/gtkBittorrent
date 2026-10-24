import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzeCommits} from '../scripts/release-analyzer.mjs';
import {generateNotes} from '../scripts/release-notes.mjs';
import {expectedAssets, missingAssets, isCurrent} from '../scripts/release.mjs';
import {execFileSync} from 'node:child_process';

const logger = {log() {}};
const commits = messages => messages.map((message, index) => ({message, hash: String(index).padStart(40, 'a')}));
for (const [messages, version] of [
  [[], null], [['docs: instalación'], 'patch'], [['chore: dependencias'], 'patch'],
  [['fix: destino'], 'patch'], [['feat: magnets'], 'minor'], [['feat!: nuevo protocolo'], 'major'],
  [['fix: compatibilidad\n\nBREAKING CHANGE: cambia el formato'], 'major'],
  [['Merge pull request #1'], 'patch'], [['docs: ayuda', 'feat: categorías', 'fix: cierre'], 'minor'],
]) test(`analyze ${JSON.stringify(messages)}`, async () => {
  assert.equal(await analyzeCommits({}, {commits: commits(messages), logger}), version);
});

test('notes contain documentation, maintenance and unclassified commits', async () => {
  const notes = await generateNotes({}, {commits: commits(['docs: ayuda', 'chore: dependencias', 'ci: publicación', 'custom: otro cambio']), logger,
    options: {repositoryUrl: 'https://github.com/example/gtkbittorrent'},
    lastRelease: {version: '1.0.0', gitTag: 'v1.0.0'}, nextRelease: {version: '1.0.1', gitTag: 'v1.0.1'}});
  for (const text of ['ayuda', 'dependencias', 'publicación', 'otro cambio']) assert.ok(notes.includes(text));
});
test('stale heads skip and current heads run', () => {
  assert.equal(isCurrent('a', 'b'), false);
  assert.equal(isCurrent('b', 'b'), true);
});
test('retry detects missing or empty artifacts without allocating a new version', () => {
  const assets = expectedAssets('1.0.0').map(name => ({name, size: 10}));
  assert.deepEqual(missingAssets('1.0.0', assets), []);
  assert.deepEqual(missingAssets('1.0.0', assets.slice(1)), [assets[0].name]);
  assets[2].size = 0;
  assert.deepEqual(missingAssets('1.0.0', assets), ['SHA256SUMS']);
});

for (const defaultBranch of ['master', 'main'])
{
    test(`semantic-release with Git default branch ${defaultBranch}`, () =>
    {
        const env = {...process.env};
        delete env.NODE_TEST_CONTEXT;
        env.GIT_CONFIG_COUNT = '1';
        env.GIT_CONFIG_KEY_0 = 'init.defaultBranch';
        env.GIT_CONFIG_VALUE_0 = defaultBranch;
        const output = execFileSync(process.execPath, ['test/semantic_fixture.mjs'], {encoding: 'utf8', env});
        assert.ok(output.includes('semantic-release integration: OK'));
    });
}
