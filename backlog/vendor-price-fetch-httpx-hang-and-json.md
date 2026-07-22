# Vendor price fetch: httpx hangs where curl succeeds; price lives in embedded JSON

## Evidence (diagnosed 2026-07-22)
`curl` from the same machine/IP fetched the Beelink product page in **0.5s with HTTP 200** and full content:
`curl -s -o NUL -w "HTTP %{http_code} time %{time_total}s" "https://www.bee-link.com/products/beelink-gtr9-pro-amd-ryzen-ai-max-395"` → `HTTP 200 time 0.53s`

The agent's httpx fetch of the SAME url hangs to the 60s ceiling (FETCH TIMEOUT). So this is NOT an IP blacklist and NOT the site blocking us — curl proves the page is reachable and fast. The bug is in the agent's fetch/parse path.

The correct current price is present in the fetched page, inside an embedded `<script>` JSON blob:
`"price":{"amount":4349.0,"currencyCode":"USD"}` (compare_at_price 4699.00) for the 128GB/2TB config.
This is $4,349 — the real official price, matching the figure that appeared in several earlier runs and the >$4,000 the operator confirmed.

## Two separable problems
1. **httpx hangs where curl doesn't.** Same reachable server, half-second for curl, 60s hang for httpx. Suspects: httpx HTTP/2 negotiation vs curl's HTTP/1.1 default; OR the markitdown conversion step (not the download) is what hangs on this huge image-heavy page, and the 60s ceiling is catching the CONVERSION not the fetch. The page has hundreds of image tags — markitdown choking is plausible.
2. **Even when fetched, the price is in embedded JSON, not rendered text.** The $4,349 lives in a `<script>` product JSON (meta.product.variants[].price), which markitdown strips. So even a successful HTML fetch would not surface the price to the Analyzer's grep. This explains why runs that DID reach the page still didn't report $4,349 from it.

## Fix directions (to attempt)
- **Diagnose the hang:** run the agent's fetch with HTTP/1.1 forced (httpx `http2=False` / explicit), and separately time the markitdown step alone, to determine which half hangs.
- **Shopify JSON endpoint (strong candidate):** these vendor stores are Shopify. Shopify exposes clean structured product data at `<product-url>.json` and `/products/<handle>.js`, returning exact price/variants without scraping HTML or fighting bot challenges. Fetching that for Shopify product URLs would give the correct price reliably and fast.

## Priority
High — this is the root cause of the recurring wrong-price problem. Vendor is the authoritative source; it is fetchable; we are failing to fetch/parse it.
