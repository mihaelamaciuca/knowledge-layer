---
file: 02-spec-onboarding-flow
area: 2
area-name: Product
type: spec
title: New-user onboarding flow
status: complete
date: 2026-05-26
depends-on:
  - 03-dec-tech-stack
feeds-into:
  - area-3-engineering
also-touches: [3]
---

# New-user onboarding flow

> **Example document.** Bundled with the template to show what a UX-flavoured `spec` looks like (contrast with the API-contract spec at `03-spec-search-api.md`, which specifies an HTTP surface rather than a screen flow). Replace or delete when you write your own.

## Goal, what a successful onboarding produces

A successful onboarding produces an account in `status='active'` with a verified email, a workspace, and at least one resource row (placeholder permitted), in under five screens.

The success metric is the share of users who, within 10 minutes of landing on the signup page, reach the post-onboarding dashboard with at least one resource row attached to their workspace. Pre-launch target: 60%. Below 40% triggers a flow review.

## Flow overview, the five screens in order

Five screens, each with a single primary action: email entry, OTP verification, password setup, workspace creation, first-resource creation. Backward navigation is allowed on every screen except OTP verification.

```
[1 email] -> [2 OTP] -> [3 password] -> [4 workspace] -> [5 first resource] -> dashboard
```

Screens 1 and 2 happen before an account row exists. Screens 3 through 5 happen after the account is created with `status='pending'`. The status flips to `active` on completion of screen 5.

The user-entered email is held in the active session only; it is never written to application logs or APM span tags (aligns with the `customer_email` field-exclusion rule in CLAUDE.md).

## Screen 1, email entry

The user enters an email address; the system either advances to OTP or shows the duplicate-account branch.

**Inputs.** Single email field, submit button.

**Validation.** Client-side: RFC-5322 syntax check. Server-side: lowercase normalisation, MX-record lookup with a 2-second timeout. Invalid syntax shows inline error "Enter a valid email address". MX lookup that returns no record shows "We can't reach that mail server, try a different address". MX lookup that exceeds the 2-second timeout shows "Email check is taking too long, try again" with a retry button (the email is preserved).

**Duplicate-account branch.** If the email matches an existing `status='active'` account, the screen shows "An account already exists for this email" with a "Sign in instead" link to the login flow. No OTP is sent.

**Network failure.** A submission that times out after 5 seconds shows "Connection lost, retry" with a retry button. The email is preserved in the input.

## Screen 2, OTP verification

The user enters the six-digit one-time password sent to their email; the system validates and advances or shows the retry branch.

**OTP delivery.** A six-digit numeric code is sent immediately on screen-1 submit. Code is valid for 10 minutes from generation. The code is cached server-side keyed by email with a 10-minute TTL; the storage mechanism is an engineering decision recorded in area 3.

**Inputs.** Six single-digit fields with auto-advance; paste of a six-digit string fills all fields. Submit on the sixth digit.

**Validation.** Wrong code shows "That code didn't match, check your email" with the fields cleared. Three wrong attempts lock the OTP; the screen then shows "Too many wrong codes, request a new one" and the inputs are disabled until the user clicks "Resend code".

**Resend.** A "Resend code" link is enabled after 30 seconds and at most three times per email per hour. After the third resend in an hour, the link shows "Resend limit reached, try again in an hour" and is disabled. Resends invalidate the previous code.

**Expiry.** After 10 minutes the screen shows "Your code expired, request a new one" and the resend link becomes the primary action.

**No backward navigation.** Returning to screen 1 would orphan the OTP. The only escape is "Use a different email", which invalidates the OTP and returns to screen 1 with the field empty.

## Screen 3, password setup

The user sets a password; the system creates the account row with `status='pending'` and advances.

**Inputs.** Password field, password-confirmation field, submit button.

**Validation.** Minimum 12 characters; at least one letter and one digit; checked against a known-breaches list with no third-party network call (the local-check mechanism is an engineering decision recorded in area 3). Mismatch shows "Passwords don't match" inline. Breached match shows "This password has appeared in a known breach, choose another" inline.

**Side effect.** On submit, the account row is created with `email_verified=true`, `password_hash` set, `status='pending'`, and a freshly allocated `tenant_id`. The user is authenticated (JWT issued via the project's `auth/` module: access token plus refresh token per the project's auth contract) before screen 4 renders.

**Server failure.** A 5xx response shows "Something went wrong, retry" with a retry button. The form values are preserved client-side; no partial account row is left behind (the row insert is the last server-side action and is atomic with the JWT issuance).

## Screen 4, workspace creation

The user names their workspace; the system creates the workspace row and advances.

**Inputs.** Workspace name (1 to 60 characters), submit button. A suggested name is pre-filled (the local-part of the email, title-cased).

**Validation.** Server-side trim and length check. No uniqueness check (workspace names are per-tenant, not global).

**Side effect.** On submit, a `workspaces` row is created with `tenant_id` from the session.

**Server failure.** A 5xx response shows "Something went wrong, retry"; the suggested name remains in the input.

## Screen 5, first resource

The user creates one resource (the project-specific primary object); the system creates it, flips the account to `active`, and advances to the dashboard.

**Inputs.** Resource name and one other required field. The "other required field" is intentionally project-specific and left for the spec author to define when adapting this example.

**Side effect.** On submit, the resource row is created, the account `status` flips from `pending` to `active`, and the user is redirected to the dashboard.

**Skip.** A "Skip for now" link creates a placeholder resource named "Untitled" and flips the account to `active`. The placeholder counts toward the success metric (the metric tolerates placeholders by design; users who never return to fill in the resource are visible in a separate retention metric, not in onboarding).

**Server failure.** A 5xx response shows "Something went wrong, retry"; the account stays at `status='pending'` until the retry succeeds.

## Abandonment, what happens if the user leaves mid-flow

Abandonment behaviour by screen: pre-account screens leave no trace; post-account screens leave a resumable `status='pending'` account.

| Last screen completed | State left behind | Resume behaviour |
|-----------------------|-------------------|------------------|
| 1 (email entered) | None (OTP cached server-side, 10-minute TTL) | Re-entering the email resends an OTP if the previous one expired |
| 2 (OTP verified) | None (verification cached server-side, 30-minute TTL) | Re-entering the email skips OTP if cache hit; otherwise re-verifies |
| 3 (password set) | Account row, `status='pending'`, no workspace | Login lands on screen 4 |
| 4 (workspace created) | Account + workspace, `status='pending'` | Login lands on screen 5 |
| 5 (first resource) | Account active | Login lands on dashboard |

Accounts stuck at `status='pending'` for more than 7 days are notified by email. After 30 days the row is deleted by an abandoned-signup sweep. This is a product-spec retention rule, not the user-initiated deletion path: Rule 1 of `docs/05-pol-data-retention.md` explicitly says "purge inactive accounts after N months belongs in the product spec, not this policy", which is the territory this rule occupies.

## Test criteria

Acceptance tests that any implementation of this flow must pass.

- **T1.** Submitting an invalid email syntax on screen 1 shows the inline syntax error and does not call the MX-lookup endpoint.
- **T2.** Submitting an email already attached to a `status='active'` account shows the duplicate-account branch and does not send an OTP.
- **T3.** Entering three wrong OTP codes locks the OTP, disables the inputs, and shows the "Too many wrong codes" message.
- **T4.** A fourth resend within one hour shows the resend-limit message and disables the resend link.
- **T5.** A breached password (one present in the local check-set) is rejected with the breached-password message; the account row is not created.
- **T6.** A successful screen-3 submit creates exactly one account row with `status='pending'`, sets `email_verified=true`, and issues a JWT before screen 4 renders.
- **T7.** Skipping screen 5 creates a placeholder `Untitled` resource and flips the account to `status='active'`.
- **T8.** An account at `status='pending'` for exactly 30 days is deleted by the abandoned-signup sweep on the 31st day.
- **T9.** Browser refresh during OTP entry preserves the email and the OTP timer; the entered digits are cleared.
- **T10.** No log line or APM span emitted during the flow contains the user's email address (per the `customer_email` field-exclusion rule).

## Out of scope, what this spec does not cover

Single sign-on (Google, Apple, SAML), team invites during onboarding, billing-tier selection, and onboarding analytics dashboards are explicitly out of scope.

- SSO is a separate spec under area 3 (auth).
- Team invites belong in a post-onboarding flow.
- Billing tier is set after onboarding via the settings page; the free tier is the default.
- Onboarding analytics live in area 4 (data), not in this product spec.
