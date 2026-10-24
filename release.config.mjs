export default {
  branches: ['main'],
  tagFormat: 'v${version}',
  plugins: [
    './scripts/release-analyzer.mjs',
    './scripts/release-notes.mjs',
    ['@semantic-release/exec', {prepareCmd: 'python3 scripts/package.py ${nextRelease.version}'}],
    ['@semantic-release/github', {
      assets: [{path: 'dist/*.tar.gz'}, {path: 'dist/SHA256SUMS'}],
      successComment: false, failComment: false, labels: false, releasedLabels: false,
    }],
  ],
};
