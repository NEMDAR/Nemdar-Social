"""Centralized audit freshness policies. Do not copy these constants elsewhere."""

PUBLIC_SURFACE_MAX_AGE_SECONDS = 7 * 86400
META_INSIGHTS_MAX_AGE_SECONDS = 48 * 3600

POLICIES = {
 'public_surface': {
  'id': 'public_surface',
  'maxAgeSeconds': PUBLIC_SURFACE_MAX_AGE_SECONDS,
  'mode': 'max_age',
  'label': 'Public surface scan',
  'description': 'HTML public collector snapshots expire after 7 days'
 },
 'meta_insights': {
  'id': 'meta_insights',
  'maxAgeSeconds': META_INSIGHTS_MAX_AGE_SECONDS,
  'mode': 'max_age',
  'label': 'Meta Insights',
  'description': 'Graph API insight snapshots expire after 48 hours'
 },
 'verified_identity': {
  'id': 'verified_identity',
  'maxAgeSeconds': None,
  'mode': 'until_disconnect',
  'label': 'Verified identity',
  'description': 'Valid until the connection expires or is disconnected'
 },
 'first_party': {
  'id': 'first_party',
  'maxAgeSeconds': 0,
  'mode': 'generation_time',
  'label': 'NEMDAR first-party operational data',
  'description': 'Current persisted state at audit generation time'
 }
}

ADDITIVE_INSIGHT_METRICS = ('reach', 'impressions', 'engagements', 'profileViews', 'websiteClicks', 'videoViews')
NON_ADDITIVE_INSIGHT_METRICS = ('followers',)
PERIOD_COMPAT_SECONDS = 86400
