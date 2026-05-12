/**
 * Cloudflare Email Worker — forwards inbound emails to viciniti.deals webhook.
 *
 * Deploy:
 *   1. Set EMAIL_INGEST_WEBHOOK_SECRET in Cloudflare Worker environment variables.
 *   2. wrangler deploy (or paste into Cloudflare dashboard > Workers > this worker)
 *   3. In Cloudflare Email Routing, create a rule:
 *      "Send to Worker" → select this worker for deals@viciniti.deals
 *
 * The worker reads the raw MIME stream, base64-encodes it, and POSTs to
 * POST https://viciniti.deals/api/email-ingest with the shared secret header.
 * Cloudflare requires the email handler to return within ~30s — we fire-and-forget
 * the fetch so the ACK is immediate.
 */

export default {
  async email(message, env, ctx) {
    // Collect raw MIME bytes from the ReadableStream
    const chunks = [];
    const reader = message.raw.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }

    // Concatenate and base64-encode
    const totalLength = chunks.reduce((sum, c) => sum + c.length, 0);
    const merged = new Uint8Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
      merged.set(chunk, offset);
      offset += chunk.length;
    }
    const rawMime = btoa(String.fromCharCode(...merged));

    const payload = JSON.stringify({
      from: message.from,
      subject: message.headers.get("subject") || "",
      rawMime,
    });

    // Fire-and-forget: ctx.waitUntil keeps the worker alive until fetch completes
    ctx.waitUntil(
      fetch("https://viciniti.deals/api/email-ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Email-Ingest-Secret": env.EMAIL_INGEST_WEBHOOK_SECRET,
        },
        body: payload,
      }).catch((err) => console.error("Webhook delivery failed:", err))
    );
  },
};
