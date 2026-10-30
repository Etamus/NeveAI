import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const browser = await chromium.connectOverCDP('http://127.0.0.1:9229');
const file = 'logs/webview2-native-test/original-prefs.json';
try {
  const expected = JSON.parse(await fs.readFile(file, 'utf8'));
  const page = browser.contexts()[0].pages()[0];
  const actual = await page.evaluate(() => Object.fromEntries(Object.keys(localStorage).map(key => [key, localStorage.getItem(key)])));
  const volatile = new Set(['token', 'chat-scroll-positions', 'neveai.unifiedModels.preload', 'neveai.unifiedModels.vramInfo']);
  const stableKeys = Object.keys(expected).filter(key => !volatile.has(key) && !key.includes('window'));
  const differences = stableKeys.filter(key => actual[key] !== expected[key]);
  const result = { comparedKeys: stableKeys.length, matchingKeys: stableKeys.length - differences.length, differingKeys: differences, persistedToken: Boolean(actual.token), nativeHost: await page.evaluate(() => window.__NEVE_WEBVIEW2__ === true) };
  assert.equal(result.nativeHost, true);
  assert.equal(result.persistedToken, true);
  assert.deepEqual(differences, []);
  await fs.writeFile('logs/webview2-native-test/migration-results.json', JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} finally {
  await fs.rm(file, { force: true });
}
// Exiting the diagnostic client disconnects CDP without sending Browser.close.
process.exit(0);
