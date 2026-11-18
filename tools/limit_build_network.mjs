// The upstream theme prerenders every route and asset with an unbounded
// Promise.all. On a large standards book that overwhelms the local content
// server. Bound both of its HTTP clients without modifying installed code.
import http from 'node:http';
import https from 'node:https';
for (const agent of [http.globalAgent, https.globalAgent]) {
  agent.maxSockets = 12;
  agent.maxTotalSockets = 24;
}
const originalFetch = globalThis.fetch;
let active = 0;
const queue = [];
async function acquire() {
  if (active < 8) { active++; return; }
  await new Promise(resolve => queue.push(resolve));
}
function release() {
  const next = queue.shift();
  if (next) next(); else active--;
}
globalThis.fetch = async (...args) => {
  await acquire();
  try {
    const response = await originalFetch(...args);
    const bytes = await response.arrayBuffer();
    const buffered = new Response([204,205,304].includes(response.status) ? null : bytes, {
      status:response.status, statusText:response.statusText, headers:response.headers,
    });
    Object.defineProperty(buffered, 'url', { value:response.url });
    return buffered;
  } catch(error) {
    const raw=args[0] instanceof Request?args[0].url:String(args[0]);
    let target=raw;try{const url=new URL(raw);target=url.origin+url.pathname;}catch{}
    console.error('Build resource fetch failed: '+target);
    throw error;
  } finally { release(); }
};
