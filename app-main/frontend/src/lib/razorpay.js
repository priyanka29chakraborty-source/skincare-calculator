/**
 * Loading and opening Razorpay Checkout.
 *
 * The script is fetched on demand rather than in index.html: most visits never
 * reach the paywall, and a third-party script on every page load is both a
 * performance cost and a privacy one for people who never pay.
 */

const CHECKOUT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

let loader = null;

export function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve(window.Razorpay);
  if (loader) return loader;

  loader = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = CHECKOUT_SRC;
    script.async = true;
    script.onload = () => {
      if (window.Razorpay) resolve(window.Razorpay);
      else reject(new Error("Razorpay loaded but did not register"));
    };
    script.onerror = () => {
      // Let a later attempt retry rather than caching the failure forever -
      // this is usually a flaky network or a blocker, not a permanent state.
      loader = null;
      reject(new Error("Could not load the payment window"));
    };
    document.body.appendChild(script);
  });
  return loader;
}

/**
 * Open checkout for an order the server created.
 *
 * Resolves with the three fields the server needs to verify the payment, or
 * rejects. A dismissed window rejects with `dismissed: true` so the caller can
 * tell "changed their mind" from "something broke" - the first deserves no
 * error message at all.
 *
 * Nothing here is trusted: the handler's response goes straight to the server,
 * which verifies the signature before granting anything. This path exists only
 * so the balance updates while the page is still open; the webhook is what
 * guarantees delivery.
 */
export async function openCheckout({ order, name, description, prefillEmail }) {
  const Razorpay = await loadRazorpay();

  return new Promise((resolve, reject) => {
    const checkout = new Razorpay({
      key: order.key_id,
      amount: order.amount,
      currency: order.currency,
      order_id: order.order_id,
      name: name || "Urancal",
      description: description || "Analysis credits",
      prefill: prefillEmail ? { email: prefillEmail } : undefined,
      theme: { color: "#96543F" },
      handler: (response) => resolve(response),
      modal: {
        ondismiss: () => {
          const err = new Error("Payment window closed");
          err.dismissed = true;
          reject(err);
        },
      },
    });

    checkout.on("payment.failed", (event) => {
      const err = new Error(
        event?.error?.description || "The payment did not go through");
      err.failed = true;
      reject(err);
    });

    checkout.open();
  });
}
