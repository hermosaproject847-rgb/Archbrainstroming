// Keep-alive: Render free service 15 min idle par so jata hai — ye Worker har 10 min
// site ko ping karta hai taaki kabhi na soye (Cloudflare Workers free, card nahi).
//
// Cloudflare dashboard → Workers & Pages → Create Worker → naam `keepalive` →
// Edit code → ye paste → Deploy → Settings → Triggers → Cron Triggers →
// Add:  */10 * * * *
export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(fetch('https://saradigitalstudios.com/', { cf: { cacheTtl: 0 } }));
  },
  async fetch() {
    return new Response('keepalive ok');
  },
};
