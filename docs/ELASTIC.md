# Elastic telemetry and trace search

AgentPay uses the official asynchronous Elasticsearch Python client for optional event indexing and search. This integration is best-effort: shopping and checkout continue to work if Elastic is unavailable, and a bounded in-memory event list is used as a fallback.

## Configure Elastic Cloud or Elasticsearch

Set these backend environment variables (never put them in the frontend):

```dotenv
ELASTICSEARCH_URL=https://your-deployment-endpoint:443
ELASTIC_API_KEY=your_elastic_api_key
ELASTIC_INDEX_PREFIX=agentpay
```

The service writes safe application events into `<prefix>-events`, e.g. `agentpay-events`. Copy the **Elasticsearch endpoint** from your Elastic deployment, not the Kibana URL. The API key should have privileges to index and search documents in the target index. Confirm the installed client version is compatible with your deployment; this project pins the Python client to the 8.x line.

After editing `backend/.env`, restart FastAPI because settings are loaded when the process starts. If the dashboard says `OFFLINE`, read the sanitized status message: authentication/authorization failures usually indicate the API key or index privileges; HTTP 404 usually indicates the wrong endpoint URL; connection/TLS failures usually indicate an incorrect host, network, or TLS configuration. The dashboard's **Retry Elastic connection** button retries the current process configuration; it does not reload `.env` values.

## API endpoints

- `GET /api/observability/status` — configuration, connection state, and sanitized diagnostics (never returns the key).
- `POST /api/observability/reconnect` — retries connectivity using settings loaded at process startup.
- `GET /api/observability/events?limit=25` — newest events.
- `GET /api/observability/events?q=paypal&limit=25` — search event type, message, and selected safe metadata.

## Privacy boundary

AgentPay records event type, message, timestamps, product IDs, merchant, amount/currency, result count, HTTP status, and order/capture IDs where useful. It deliberately does not index raw shopping prompts, API credentials, PayPal access tokens, or raw PayPal request/response bodies. Keep Elasticsearch access restricted and set a retention policy appropriate for your demo.
