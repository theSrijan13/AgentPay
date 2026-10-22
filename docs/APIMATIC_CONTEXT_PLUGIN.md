# APIMatic PayPal Context Plugin

The APIMatic PayPal Context Plugin is a **development-time tool** for coding assistants. It provides PayPal API context and skills to the coding agent; it is not a runtime library required by AgentPay.

## Install on the developer Mac

Prerequisite: Node.js 18 or newer and a supported coding assistant (the installer detects supported assistants).

```bash
npx context-plugins install paypal
npx context-plugins list
```

Official plugin page: https://context.apimatic.io/plugins/paypal/

## Suggested prompts for the coding assistant

- Review `backend/app/paypal.py` against the current PayPal Orders API contract.
- Verify server-side access token handling and idempotency headers for create-order and capture.
- Add tests for API errors, network timeout, repeated capture attempts, and non-completed captures.
- Never move `PAYPAL_CLIENT_SECRET` to the frontend or print it in logs.
- Confirm that a Sandbox capture is marked successful only when PayPal's response confirms `COMPLETED` and contains a completed capture.

After using the plugin, review every generated code change and run the repository tests. Do not add credentials or generated personal configuration files to the public repository.
