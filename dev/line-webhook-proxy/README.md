# Development-only LINE webhook proxy

Stock nginx is the reviewable boundary between Quick Tunnel and Nara. It permits
only `POST /line/webhook`, using the **raw URI**, including arguments, so query
strings, percent encoding and normalized equivalents are denied. Non-POST
methods get 404 (TRACE gets nginx's native 405). Bodies larger than 1 MiB get
413, including chunked requests. Body bytes and `x-line-signature` stay unchanged.

Config, tests and instructions have no secrets and belong in the repo for team
review. LINE secrets and machine-specific secret files do not. Neither this
proxy nor cloudflared belongs in the main Compose file or AWS deployment.

## 1. Test the config before exposing it

From the repo root, with Docker running:

```sh
python3 dev/line-webhook-proxy/test_proxy.py
```

This is also run by CI. It starts isolated test containers (real nginx with the
committed config and a fake echo upstream), publishes random loopback ports,
and removes those containers/network on completion. No Nara container, database,
actual LINE credential or public tunnel is used. The fake backend is only a
fixture, not a production proxy.

## 2. Start only the opt-in proxy

Start Nara's local backend on port 8000 first, then:

```sh
docker compose -f dev/line-webhook-proxy/compose.yml up -d
python3 dev/line-webhook-proxy/check_gate.py http://127.0.0.1:18080
```

The check prompts for the Channel secret without echoing, logging or storing
it. It sends only an empty signed verification body, an invalid signature and
denied requests. Backend must be configured in real LINE mode. It does not send
candidate answers. On Linux, port 8000 must be reachable from the proxy container
via the host gateway; on Docker Desktop the host gateway is provided as well.

## 3. Start the tunnel only after local checks pass

```sh
cloudflared tunnel --url http://127.0.0.1:18080
```

**Never point it directly at port 8000.** Keep this process running. The URL
changes on restart. Set `https://<random>.trycloudflare.com/line/webhook` in LINE
Developers (no `/api`), Verify, and enable Use webhook and Webhook redelivery.
Then repeat the same gate check through the public base URL:

```sh
python3 dev/line-webhook-proxy/check_gate.py https://<random>.trycloudflare.com
```

The check does not normalize paths. Both runs cover signed/invalid-signature
POSTs, `/line/webhooks`, query strings, percent encoding, repeated slashes,
dot segments, case differences, non-POST methods, `/demo/reset`, the internal
job route, and known-length/chunked oversized bodies. CI additionally verifies
that rejected traffic never reaches its fake upstream.

Record the commit, local/public results and subsequent real LINE offer tests.
If the tunnel drops mid-test, record what remains incomplete and fall back to
fake LINE/simulator; do not claim a complete live run. Quick Tunnels are for
short-term development/testing and offer no uptime guarantee. Use only if
permitted by the organisers.

## Stop and deploy

Stop cloudflared with Ctrl+C and stop the optional proxy:

```sh
docker compose -f dev/line-webhook-proxy/compose.yml down
```

For round 6 deploy, set LINE's webhook to AWS HTTPS and leave these development
tools stopped and excluded from the AWS Compose set.

References: [nginx original URI](https://nginx.org/en/docs/http/ngx_http_core_module.html#var_request_uri),
[case-sensitive map](https://nginx.org/en/docs/http/ngx_http_map_module.html),
[body limit](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size),
[Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
