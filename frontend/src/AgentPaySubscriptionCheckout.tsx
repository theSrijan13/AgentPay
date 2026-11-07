
// import { useState } from "react";
// import {
//     PayPalProvider,
//     PayPalSubscriptionButton,
//     type OnApproveDataSubscriptions,
// } from "@paypal/react-paypal-js/sdk-v6";

// const API_BASE =
//     import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

// const CLIENT_ID =
//     import.meta.env.VITE_PAYPAL_SUBSCRIPTIONS_CLIENT_ID;

// function SubscriptionButton() {
//     const [message, setMessage] = useState("");
//     const [busy, setBusy] = useState(false);

//     const createSubscription = async () => {
//         setBusy(true);
//         setMessage("Preparing your subscription...");

//         try {
//             const response = await fetch(
//                 `${API_BASE}/api/subscriptions/checkout`,
//                 { method: "POST" }
//             );

//             const result = await response.json();

//             if (!response.ok || !result.id) {
//                 throw new Error(result.detail || "Could not create subscription.");
//             }

//             return { subscriptionId: result.id };
//         } catch (error) {
//             setBusy(false);
//             setMessage(
//                 error instanceof Error ? error.message : "Subscription creation failed."
//             );
//             throw error;
//         }
//     };

//     const handleApprove = async (
//         data: OnApproveDataSubscriptions
//     ) => {
//         setMessage("Verifying your subscription with PayPal...");

//         const response = await fetch(
//             `${API_BASE}/api/subscriptions/${encodeURIComponent(
//                 data.subscriptionId
//             )}/verify`,
//             { method: "POST" }
//         );

//         const result = await response.json();

//         if (!response.ok) {
//             throw new Error(result.detail || "Subscription verification failed.");
//         }

//         setBusy(false);
//         setMessage(
//             `Subscription ${result.status}. Reference: ${result.id}`
//         );
//     };

//     return (
//         <section className="agentpay-subscription-checkout">
//             <h2>AgentPay Premium</h2>
//             <p>$9.99 USD / month</p>

//             <PayPalSubscriptionButton
//                 createSubscription={createSubscription}
//                 onApprove={handleApprove}
//                 onCancel={() => {
//                     setBusy(false);
//                     setMessage("Subscription checkout cancelled.");
//                 }}
//                 onError={(error) => {
//                     setBusy(false);
//                     setMessage(error.message || "PayPal checkout failed.");
//                 }}
//                 presentationMode="auto"
//                 type="subscribe"
//                 disabled={busy}
//             />

//             {message && <p role="status">{message}</p>}
//         </section>
//     );
// }

// export default function AgentPaySubscriptionCheckout() {
//     if (!CLIENT_ID) {
//         return <p>Subscription PayPal Client ID is not configured.</p>;
//     }

//     return (
//         <PayPalProvider
//             clientId={CLIENT_ID}
//             environment="sandbox"
//             components={["paypal-subscriptions"]}
//             pageType="checkout"
//         >
//             <SubscriptionButton />
//         </PayPalProvider>
//     );
// }

import { useState } from "react";

import {
    PayPalProvider,
    PayPalSubscriptionButton,
    type OnApproveDataSubscriptions,
} from "@paypal/react-paypal-js/sdk-v6";

const API_BASE_URL = (
    import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const PAYPAL_CLIENT_ID =
    import.meta.env.VITE_PAYPAL_SUBSCRIPTIONS_CLIENT_ID;

function SubscriptionCheckoutButton() {
    const [message, setMessage] = useState(
        "Ready to start your AgentPay Premium subscription."
    );

    const [busy, setBusy] = useState(false);
    const [subscriptionId, setSubscriptionId] = useState("");

    const createSubscription = async (): Promise<{
        subscriptionId: string;
    }> => {
        setBusy(true);
        setMessage("Creating your subscription with PayPal...");

        try {
            const response = await fetch(
                `${API_BASE_URL}/api/subscriptions/checkout`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                }
            );

            const result = await response.json().catch(() => ({}));

            if (!response.ok) {
                throw new Error(
                    result.detail || "Unable to create your subscription."
                );
            }

            if (!result.subscriptionId) {
                throw new Error(
                    "PayPal did not return a subscription ID."
                );
            }

            setSubscriptionId(result.subscriptionId);

            return {
                subscriptionId: result.subscriptionId,
            };
        } catch (error: unknown) {
            setBusy(false);

            setMessage(
                error instanceof Error
                    ? error.message
                    : "Subscription creation failed."
            );

            throw error;
        }
    };

    const handleApproval = async (
        data: OnApproveDataSubscriptions
    ): Promise<void> => {
        setBusy(true);
        setMessage("Verifying your subscription with PayPal...");

        try {
            const response = await fetch(
                `${API_BASE_URL}/api/subscriptions/${encodeURIComponent(
                    data.subscriptionId
                )}/verify`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                }
            );

            const result = await response.json().catch(() => ({}));

            if (!response.ok) {
                throw new Error(
                    result.detail || "Subscription verification failed."
                );
            }

            setSubscriptionId(result.id);
            setMessage(
                `Your subscription is ${result.status}. PayPal has verified it successfully.`
            );
        } catch (error: unknown) {
            setMessage(
                error instanceof Error
                    ? error.message
                    : "Could not verify the subscription."
            );

            throw error;
        } finally {
            setBusy(false);
        }
    };

    return (
        <section className="agentpay-subscription-card">
            <div className="agentpay-subscription-header">
                <span className="agentpay-subscription-label">
                    AGENTPAY PREMIUM
                </span>

                <span className="agentpay-subscription-badge">
                    SANDBOX
                </span>
            </div>

            <h2>Unlock AgentPay Premium</h2>

            <div className="agentpay-subscription-price">
                $9.99
                <span>/ month</span>
            </div>

            <p className="agentpay-subscription-description">
                Get access to your AgentPay Premium subscription.
                Manage your billing and payments through PayPal.
            </p>

            <ul className="agentpay-subscription-features">
                <li>AI-powered shopping experience</li>
                <li>Subscription monitoring</li>
                <li>Payment tracking</li>
                <li>Intelligent billing insights</li>
                <li>Automated notifications</li>
            </ul>

            <PayPalSubscriptionButton
                createSubscription={createSubscription}
                onApprove={handleApproval}
                onCancel={() => {
                    setBusy(false);
                    setMessage("You cancelled the subscription checkout.");
                }}
                onError={(error) => {
                    console.error("PayPal subscription error:", error);

                    setBusy(false);
                    setMessage(
                        "PayPal checkout encountered an error. Please retry."
                    );
                }}
                presentationMode="auto"
                type="subscribe"
                disabled={busy}
            />

            <p className="agentpay-subscription-status" role="status">
                {message}
            </p>

            {subscriptionId && (
                <div className="agentpay-subscription-reference">
                    <span>Subscription reference</span>
                    <code>{subscriptionId}</code>
                </div>
            )}

            <p className="agentpay-subscription-footer">
                Secure recurring billing powered by PayPal Sandbox.
            </p>
        </section>
    );
}

export default function AgentPaySubscriptionCheckout() {
    if (!PAYPAL_CLIENT_ID) {
        return (
            <div className="agentpay-subscription-error">
                PayPal subscription Client ID is missing.
                Configure VITE_PAYPAL_SUBSCRIPTIONS_CLIENT_ID in frontend/.env.
            </div>
        );
    }

    return (
        <PayPalProvider
            clientId={PAYPAL_CLIENT_ID}
            environment="sandbox"
            components={["paypal-subscriptions"]}
            pageType="checkout"
        >
            <SubscriptionCheckoutButton />
        </PayPalProvider>
    );
}