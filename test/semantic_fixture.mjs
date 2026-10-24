import assert from 'node:assert/strict';
import semanticRelease from 'semantic-release';
import {execFileSync} from 'node:child_process';
import {mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {Writable} from 'node:stream';
import {analyzeCommits} from '../scripts/release-analyzer.mjs';
  const dir = mkdtempSync(join(tmpdir(), 'gtkb-semver-'));
  const repo = join(dir, 'repo');
  const origin = join(dir, 'origin.git');
  const git = (args, cwd = repo) => execFileSync('git', args, {cwd, stdio: 'pipe', encoding: 'utf8'}).trim();
  const sink = new Writable({write(chunk, encoding, callback) { callback(); }});
  let legacyHead;
  const analyze = () => semanticRelease({ci: false, dryRun: true, branches: ['main'], repositoryUrl: `file://${origin}`,
    plugins: [[resolve('scripts/release-analyzer.mjs'), {excludeHistory: legacyHead}],
      [resolve('scripts/release-notes.mjs'), {excludeHistory: legacyHead}]]},
    {cwd: repo, env: {...process.env, CI: 'false'}, stdout: sink, stderr: sink});
  let count = 0;
  const commit = message => {
    writeFileSync(join(repo, 'sample'), String(count++));
    git(['add', '.']); git(['commit', '-m', message]); git(['push', 'origin', 'main']);
  };
  try {
    git(['init', '--bare', origin], dir);
    git(['init', '-b', 'main', repo], dir);
    git(['config', 'user.name', 'Release test']);
    git(['config', 'user.email', 'test@example.invalid']);
    git(['remote', 'add', 'origin', origin]);
    writeFileSync(join(repo, 'legacy'), 'previous implementation');
    git(['add', '.']);
    git(['commit', '-m', 'feat!: legacy implementation']);
    legacyHead = git(['rev-parse', 'HEAD']);
    git(['branch', 'legacy']);
    git(['checkout', '--orphan', 'mvp']);
    git(['rm', '-rf', '.']);
    git(['branch', '-D', 'main']);
    git(['branch', '-m', 'main']);
    commit('feat: cliente inicial');
    git(['merge', '--allow-unrelated-histories', '--strategy=ours', 'legacy', '-m', 'feat: merge Ruby MVP']);
    git(['push', 'origin', 'main']);
    assert.equal(await analyzeCommits({excludeHistory: legacyHead}, {cwd: repo,
      commits: [{hash: legacyHead, message: 'feat!: legacy implementation'}], logger: {log() {}}}), null);
    const first = await analyze();
    assert.equal(first.nextRelease.version, '1.0.0');
    assert.ok(first.nextRelease.notes.includes('cliente inicial'));
    assert.ok(!first.nextRelease.notes.includes('legacy implementation'));
    git(['tag', 'v1.0.0']); git(['push', 'origin', '--tags']);
    assert.equal(await analyze(), false);
    commit('docs: ayuda');
    assert.equal((await analyze()).nextRelease.version, '1.0.1');
    commit('feat: categorías');
    assert.equal((await analyze()).nextRelease.version, '1.1.0');
    commit('fix!: cambia el protocolo');
    assert.equal((await analyze()).nextRelease.version, '2.0.0');
  } finally {
    rmSync(dir, {recursive: true, force: true});
  }
console.log('semantic-release integration: OK');
