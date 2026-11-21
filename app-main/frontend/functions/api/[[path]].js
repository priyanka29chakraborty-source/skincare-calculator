const API_ORIGIN = "https://skincare-calculator.onrender.com";

/**
 * Keep browser sessions first-party.
 *
 * The frontend and API used to live on unrelated sites: urancal.com and
 * onrender.com. Browsers that block third-party cookies therefore discarded
 * the session after sign-in. Proxying /api through the Pages domain means the
 * HttpOnly session cookie belongs to urancal.com; Render remains the origin
 * that does the work.
 */
export async function onRequest({ request, env }) {
  const incoming = new URL(request.url);
  const upstream = new URL(incoming.pathname + incoming.search, API_ORIGIN);
  const headers = new Headers(request.headers);
  headers.set("X-Forwarded-Host", incoming.host);
  headers.set("X-Forwarded-Proto", incoming.protocol.replace(":", ""));

  // Drop anything the browser sent under these names, then stamp the IP
  // Cloudflare actually saw. The shared secret is what lets Render tell this
  // stamp from a header someone set on the raw onrender.com URL. When the
  // secret is not configured yet, send neither header: the API then applies
  // the email limits and does not invent an IP.
  headers.delete("X-Visitor-IP");
  headers.delete("X-Visitor-Secret");
  const secret = env && env.CF_VISITOR_SECRET;
  const visitorIp = request.headers.get("CF-Connecting-IP");
  if (secret && visitorIp) {
    headers.set("X-Visitor-IP", visitorIp);
    headers.set("X-Visitor-Secret", secret);
  }

  const init = {
    method: request.method,
    headers,
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  const response = await fetch(new Request(upstream, init));
  return new Response(response.body, response);
}
