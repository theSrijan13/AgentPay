# AgentPay

An AI-assisted shopping agent prototype for the PayPal AI Hackathon. This is a hackathon/demo project, not a production payment platform.

## Current MVP flow
1. User describes a shopping goal.
2. AgentPay searches Channel3 live product and retailer-offer data when configured, with a clearly labelled local demo fallback.
3. User reviews products, price, availability, and retailer offer links, then selects products.
4. FastAPI refreshes selected Channel3 product details, then validates product IDs, quantities, availability, prices, USD currency, and the parsed budget.
5. PayPal Sandbox order is created from server-side validated prices.
6. Buyer approves through the PayPal Checkout buttons.
7. Backend captures the order and shows success only after PayPal returns a completed capture.

> Payments are never executed by the LLM. Explicit buyer approval is required. Seeded demo-catalog prices are illustrative USD prices; Channel3 retailer offers are live discovery data and can change between searches.

## Stack
- Frontend: React + TypeScript + Vite + `@paypal/react-paypal-js` + AG Grid Community
- Backend: Python + FastAPI + HTTPX
- Product discovery and shopping conversation: Channel3 Agentic Search + Conversational Agent, with a seeded catalog fallback
- Payments: PayPal Orders v2 API (Sandbox)
- Observability: optional Elastic / Elasticsearch indexing and searchable audit events, with bounded in-memory fallback
- Delivery and testing: Render Blueprint, Postman collection, and APIMatic PayPal Context Plugin for developer-assistant workflows

## Prerequisites
- Python 3.11+
- Node.js 20+
- A PayPal Developer account with a Sandbox REST app
- A Sandbox buyer account for checkout testing

## Run locally

### Backend (Terminal 1)
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in backend/.env
uvicorn app.main:app --reload --port 8000
```

### Frontend (Terminal 2)
```bash
cd frontend
npm install
cp .env.example .env
# Set VITE_PAYPAL_CLIENT_ID to the same Sandbox Client ID (not the secret)
npm run dev
```

Open http://localhost:5173. API docs: http://localhost:8000/docs.

## PayPal Sandbox setup
1. Open the [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/).
2. Under **Apps & Credentials**, choose **Sandbox** and create or select a REST app.
3. Copy the Sandbox **Client ID** and **Secret** into `backend/.env`:
   ```dotenv
   PAYPAL_CLIENT_ID=your_sandbox_client_id
   PAYPAL_CLIENT_SECRET=your_sandbox_secret
   PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
   ```
4. Put the same Sandbox Client ID only (never the secret) in `frontend/.env`:
   ```dotenv
   VITE_PAYPAL_CLIENT_ID=your_sandbox_client_id
   VITE_API_BASE_URL=http://localhost:8000
   ```
   The frontend also reads the public Client ID from `GET /api/public-config` at runtime. This is a fallback when Vite was launched from a directory that did not load `frontend/.env`. The Client ID is public; the Secret must remain backend-only.
5. Restart FastAPI and Vite after modifying `.env` files. Use a Sandbox buyer account to approve the test payment.
6. Do not commit `.env` files or share the Client Secret in chat, screenshots, or source control.

The demo catalog uses USD because INR is not listed among PayPal's standard Checkout currencies. Do not treat the illustrative demo prices as currency-converted real-world prices.

## Important prototype limitations
- Orders and events are held in server memory and are lost when the backend restarts. Add database persistence before final hackathon submission.
- The catalog is illustrative, not live inventory or sourced marketplace data.
- Channel3 agentic search can interpret multi-constraint shopping queries when a valid API key is configured. The local fallback planner is deterministic. AgentPay's own multi-step tool-calling orchestrator remains a planned milestone.
- Add automated tests, robust concurrency/idempotency handling, inventory reservation and production security review before any live deployment. This project is intended for PayPal Sandbox only.

## Project status
- [x] React shopping workspace
- [x] Seeded USD demo catalog and basket validation
- [x] Channel3 agentic search integration with current response schema, cleaned images, offer comparisons, retailer links, and price/availability refresh before validation
- [x] PayPal Sandbox create-order / buyer approval / capture flow implemented
- [x] AG Grid Community retailer offer comparison with sorting/filtering and add-selected-offer workflow
- [x] Channel3 Conversational Agent endpoint for contextual follow-ups
- [x] Optional Elastic event indexing/search with in-memory fallback
- [x] Render Blueprint and Postman API collection
- [x] APIMatic Context Plugin setup guidance
- [ ] Persistent order storage and production-grade concurrency safety
- [ ] Live end-to-end Channel3 + PayPal test with developer credentials
- [ ] Final deployment validation and demo video

## Channel3 live product discovery (recommended for the hackathon)
Channel3 is integrated as the live catalog/search provider. It supplies structured product results, images, retailer offer links, prices, and offer availability. AgentPay uses Channel3 search defaults for locale (the raw REST body omits unsupported top-level locale fields) and only places an offer in the demo basket when the chosen retailer offer is in stock and priced in USD. Verify the returned offer currency before display or checkout.

1. Create a free Channel3 API key at https://trychannel3.com/developers (the hackathon resource notes the promo code `PAYPAL-HACKATHON-2026` provides 20,000 searches for participants; confirm the current terms in the Channel3 dashboard).
2. Add the key to `backend/.env`:
   ```dotenv
   CHANNEL3_API_KEY=your_channel3_api_key
   CHANNEL3_BASE_URL=https://api.trychannel3.com/v1
   CHANNEL3_SEARCH_MODE=agentic
   ```
3. Restart FastAPI and click **Build my plan**. The backend passes `config.mode="agentic"` to Channel3, so its search planner can extract filters from multi-constraint requests. The dashboard should show `CHANNEL3 LIVE`, product images, retailer links, and offer comparisons when Channel3 returns eligible USD offers.
4. If the key is absent or the API is unavailable, AgentPay clearly falls back to the local demo catalog.

Official docs: https://docs.trychannel3.com/api-reference/v1/search, https://docs.trychannel3.com/guides/agentic-search, https://docs.trychannel3.com/guides/localization, https://docs.trychannel3.com/guides/images.

**Payment/fulfilment limitation:** Channel3 supplies discovery and retailer offer URLs; the current PayPal flow is a separate Sandbox payment demonstration. It does not place an order with or cause fulfilment by the retailer. AgentPay displays this limitation in the checkout UI and links users to the retailer offer.


## Channel3 HTTP 422 troubleshooting

The live REST search request uses Channel3's default locale (English / US / USD), which matches the PayPal Sandbox demo. Do not add `country`, `language`, or `currency` as top-level fields in the search JSON body unless the active API schema accepts them; the current API returned HTTP 422 for those fields in testing. Search mode remains in `config.mode`. If a Channel3 request fails, the UI reports the API error separately from a missing API key.


## AG Grid offer comparison
The shopping page includes an AG Grid Community table containing retailer offers for current search results. Users can sort/filter by product, retailer, price, availability, and condition, then add a specific merchant offer to the basket. The backend resolves the requested merchant from its server-side Channel3 cache and does not accept client-supplied price or buy URL fields. Community Grid is used so the project does not require an Enterprise license.

Official docs: https://www.ag-grid.com/react-data-grid/installation/

## Channel3 Conversational Agent
`POST /api/agent/chat` sends a turn to Channel3's non-streaming Conversational Agent, optionally continues a `conversation_id`, applies in-stock and budget filters, returns structured product cards, and passes a stable, non-identifying demo user ID using `x-user-id`. The main "Build my plan" button now starts this conversation first and saves the returned conversation ID so follow-up requests can reuse context. The vendor API key stays on the backend. If the conversation endpoint fails, the UI may show search results as a fallback, but it also tells you contextual follow-ups are not active.

## Elastic observability
Set `ELASTICSEARCH_URL`, `ELASTIC_API_KEY`, and optionally `ELASTIC_INDEX_PREFIX` on the backend. Use the Elasticsearch endpoint from the Elastic deployment (not the Kibana URL) and an API key with permissions for the target index. Restart FastAPI after changing `.env`. AgentPay indexes safe events to `<prefix>-events` and supports `/api/observability/status`, `/api/observability/events`, and `POST /api/observability/reconnect`. The status response gives a sanitized diagnostic hint for authentication, endpoint, and connection failures. If Elastic is unconfigured or fails, the app continues with bounded in-memory history. The event stream does not include raw prompts, API credentials, access tokens, or raw PayPal payloads. See `docs/ELASTIC.md`.

## APIMatic, Postman, and Render
- APIMatic PayPal Context Plugin install guide and review prompts: `docs/APIMATIC_CONTEXT_PLUGIN.md`. The plugin is for developer coding assistants; it is not a runtime dependency.
- Import `postman/AgentPay.postman_collection.json`; instructions: `docs/POSTMAN.md`.
- `render.yaml` defines a FastAPI service and a static Vite frontend. Edit the API/front-end Render URLs if your service slugs differ, and set all `sync: false` environment values in the Render dashboard. Use PayPal Sandbox credentials only.
