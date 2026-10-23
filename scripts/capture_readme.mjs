// Capture the actual Next.js UI with browser-local, synthetic API responses.
// Start Next on 127.0.0.1:13123 first; no backend or model is contacted.
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium } = require('@playwright/test');
const origin = 'http://127.0.0.1:13123';
const out = fileURLToPath(new URL('../docs/images/', import.meta.url));
const skus = [
  { sku_code: 'ecoflow-delta2', brand: 'EcoFlow', model: 'DELTA 2', capacity_wh: 1024, capacity_tier: 'mid', is_competitor: false, dashboard_enabled: true },
  { sku_code: 'jackery-explorer-1000', brand: 'Jackery', model: 'Explorer 1000', capacity_wh: 1002, capacity_tier: 'mid', is_competitor: true, dashboard_enabled: true },
];
// Values mirror the existing overview component test, not customer observations.
const aspects = [{ aspect_label: 'battery_capacity', mention_count: 9, positive_rate: 0.78 }, { aspect_label: 'noise', mention_count: 5, positive_rate: 0.2 }];
const weeks = [{ week_id: 202403, week_start: '2024-01-15', week_end: '2024-01-21', doc_count: 12, mention_count: 20, skus_covered: skus.map(s => s.sku_code) }];
const browser = await chromium.launch({ headless: true, args: ['--no-proxy-server'] });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
  await context.addInitScript(() => localStorage.setItem('voc.access-token', 'screenshot-fixture-only'));
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith('/api/')) {
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'access-control-allow-origin': origin, 'access-control-allow-headers': 'authorization,content-type', 'access-control-allow-methods': 'GET,OPTIONS' } });
      let data;
      if (url.pathname === '/api/auth/me') data = { subject: 'demo' };
      else if (url.pathname === '/api/weeks') data = weeks;
      else if (url.pathname === '/api/skus') data = skus;
      else if (url.pathname === '/api/overview') data = {
        week_id: 202403, summary: { total_mentions: 20, sentiment_breakdown: { positive: 10, negative: 4, neutral: 6 } },
        top_aspects: aspects,
        sku_rankings: skus.map((s, i) => ({ sku_code: s.sku_code, sku_name: `${s.brand} ${s.model}`, mention_count: i ? 9 : 11, sentiment_score: i ? 0.2 : 0.5 })),
      };
      else if (url.pathname === '/api/compare') data = { week_id: 202403, capacity_tier: 'mid', skus: skus.map(s => ({ sku_code: s.sku_code, review_count: 10, mention_count: 12, positive_count: 7, negative_count: 3, neutral_count: 2, positive_rate: 7/12, negative_rate: 3/12, neutral_rate: 2/12, sentiment_score: 4/12 })), warnings: [] };
      else if (url.pathname.endsWith('/evidence')) data = [];
      else if (url.pathname.endsWith('/trends')) data = { trends: [] };
      else if (url.pathname.startsWith('/api/skus/')) data = { ...skus.find(s => url.pathname.endsWith(s.sku_code)), week_id: 202403, review_count: 10, mention_count: 12, sentiment_breakdown: { positive: 7, negative: 3, neutral: 2 }, top_aspects: [{ aspect_label: 'battery_capacity', mention_count: 8, positive_rate: 0.75 }] };
      else throw new Error(`Unexpected API request: ${url.pathname}`);
      return route.fulfill({ json: data, headers: { 'access-control-allow-origin': origin } });
    }
    if (url.origin === origin) return route.continue();
    return route.abort();
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await mkdir(out, { recursive: true });
  for (const [path, ready, name] of [
    ['/overview', 'Covered products', 'overview-fixture.png'],
    ['/compare', 'Representative evidence', 'compare-fixture.png'],
  ]) {
    await page.goto(origin + path);
    try { await page.getByText(ready, { exact: true }).waitFor(); }
    catch (error) { console.error(await page.locator('body').innerText()); throw error; }
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: out + name, fullPage: true, animations: 'disabled' });
    console.log(`Captured ${name}`);
  }
  if (errors.length) throw new Error(errors.join('\n'));
} finally {
  await browser.close();
}
