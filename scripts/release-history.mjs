import {execFileSync} from 'node:child_process';

export const legacyHistoryEnd = '890da1136657284c3c76d52a6fb3ff6b463f94b7';

export function releaseContext(config, context)
{
    if (!config.excludeHistory) return context;
    const history = execFileSync('git', ['rev-list', config.excludeHistory, '--'], {
        cwd: context.cwd,
        encoding: 'utf8',
        maxBuffer: 16 * 1024 * 1024,
    });
    const excluded = new Set(history.trim().split('\n'));
    return {...context, commits: context.commits.filter(commit => !excluded.has(commit.hash))};
}
