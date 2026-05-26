---
file: after-authentication
area: 3
area-name: Engineering
type: spec
title: Authentication middleware
status: complete
date: 2026-04-08
depends-on:
  - 03-dec-tech-stack
feeds-into: []
---

# Authentication middleware

## JWT validation, how tokens are checked on every request

The auth middleware validates JWT tokens on every incoming request before
the route handler runs. It checks three things: the token signature
matches the current signing key, the token has not expired, and the
token claims include a valid user ID. If any check fails, the middleware
returns a 401 with no further processing. Implementation uses PyJWT.

Signing keys are rotated monthly. The rotation uses a 24-hour overlap
window where both the old and new keys are accepted, so in-flight
tokens issued against the old key validate cleanly during the
transition.

## Token lifetimes, 30-day access, 90-day refresh

Access tokens expire after 30 days. Refresh tokens expire after 90 days.
When an access token expires, the client sends the refresh token to
`POST /auth/refresh` to get a new access token. If the refresh token
is also expired, the user must log in again.

These durations were chosen to balance security (shorter is better)
against user experience (longer means fewer re-logins). The 30/90
split means most active users never see a login screen after initial
setup.

## Rate limiting, 10 refresh requests per minute per user

The `POST /auth/refresh` endpoint is rate-limited to 10 requests per
minute per user. This was added after an incident in March 2026 where
a mobile client bug caused a refresh loop that generated thousands of
requests per user.

Rate-limit responses return 429 with a `Retry-After` header.

## Failed auth logging, security monitoring integration

All failed authentication attempts (expired tokens, invalid signatures,
malformed tokens) are logged with timestamp, user ID (if extractable),
IP address, and failure reason. These logs feed into a security
monitoring dashboard. Alert thresholds: more than 50 failures per
minute from a single IP triggers a warning; more than 200 triggers
an automatic temporary block.
