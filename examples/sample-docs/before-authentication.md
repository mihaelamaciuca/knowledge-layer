---
title: Authentication
type: spec
status: in-progress
date: 2026-04-08
---

# Authentication

## Overview

This document describes how authentication works in the system. We use JWTs for stateless auth. See the architecture doc for more details on the overall approach.

## Implementation

The auth middleware validates tokens on every request. When a token expires, the client uses the refresh token to get a new one. If the refresh token is also expired, the user has to log in again. The session timeout is configurable. We decided to use 30 days for the access token and 90 days for the refresh token based on the discussion in the product meeting. The middleware also handles the case where the token is malformed or the signing key doesn't match. In those cases it returns a 401. There's also rate limiting on the token refresh endpoint to prevent abuse, currently set to 10 requests per minute per user. The rate limit decision was made after the incident in March where a bug in the mobile client caused a refresh loop. We also added logging for failed auth attempts which feeds into the security monitoring dashboard (see the ops runbook for alert thresholds). The middleware sits before the route handlers in the request chain and uses the standard library's JWT package for validation. Keys are rotated monthly using the process described in the security policy.
