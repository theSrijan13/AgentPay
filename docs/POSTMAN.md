# Postman API collection

Import `postman/AgentPay.postman_collection.json` into Postman. The collection defaults to `http://localhost:8000`.

Recommended flow:

1. Run **Health**.
2. Run **Create shopping plan**. The collection saves the first returned product ID and merchant for later requests.
3. Run **Select retailer offer** if Channel3 is enabled.
4. Run **Validate basket**.
5. Run **Create PayPal Sandbox order**. The collection saves the PayPal order ID.
6. Complete buyer approval in the browser-based PayPal Buttons flow. Do not assume order creation alone means paid.
7. Run **Capture order** only for an order that has been approved by the Sandbox buyer.
8. Run **Get order** and **Observability events**.

Do not put API keys or PayPal secrets in the shared collection. Use Postman local/environment variables only for any sensitive development values, and do not export them into the public repository.
