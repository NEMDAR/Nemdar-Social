// Provider-independent workflow foundation. No live platform calls.
export function qualify(criteria) {
  const keys = ['budget', 'authority', 'need', 'timeline'];
  if (keys.some(key => criteria[key] === false)) return 'unqualified';
  return keys.every(key => criteria[key] === true) ? 'qualified' : 'incomplete';
}
export function schedule(post, when, now = new Date()) {
  if (post.status !== 'approved') throw new Error('Approval required');
  if (!post.accountIds?.length) throw new Error('Select at least one account');
  const date = new Date(when);
  if (!Number.isFinite(date.getTime()) || date <= now) throw new Error('Choose a future date');
  return {...post, status: 'scheduled', scheduledAt: date.toISOString()};
}
export function failedTargets(job) {
  return job.targets.filter(target => target.status === 'failed');
}
export function addAccount(accounts, account) {
  if (!account.clientId || !account.platform || !account.externalId) throw new Error('Missing account identity');
  if (accounts.some(a => a.clientId === account.clientId && a.platform === account.platform && a.externalId === account.externalId)) throw new Error('Account already assigned');
  return [...accounts, {...account, connectionStatus: 'not_connected'}];
}
