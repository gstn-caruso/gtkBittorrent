import {legacyHistoryEnd} from './scripts/release-history.mjs';

export default {
  branches: ['main'],
  tagFormat: 'v${version}',
  plugins: [
    ['./scripts/release-analyzer.mjs', {excludeHistory: legacyHistoryEnd}],
    ['./scripts/release-notes.mjs', {excludeHistory: legacyHistoryEnd}],
    ['@semantic-release/exec', {prepareCmd: 'sh scripts/prepare-release.sh ${nextRelease.version}'}],
    ['@semantic-release/github', {
      assets: [{path: 'dist/*.tar.gz'}, {path: 'dist/SHA256SUMS'}],
      successComment: false, failComment: false, labels: false, releasedLabels: false,
    }],
  ],
};
