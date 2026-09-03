// saradigitalstudios.com  →  Hugging Face Space  (reverse proxy, URL bar me domain hi rehta hai)
//
// Cloudflare dashboard → Workers & Pages → Create → Worker → is file ka content paste → Deploy.
// Worker → Settings → Variables and Secrets:
//   SPACE_HOST  (text)   = <hf-username>-arch-brain-storming.hf.space
//   HF_TOKEN    (secret) = hf_xxx  (sirf tab jab Space Private ho; Read token kaafi hai)
// Worker → Settings → Domains & Routes → Add → Custom domain → saradigitalstudios.com (aur www).
export default {
  async fetch(req, env) {
    const inUrl = new URL(req.url);
    const url = new URL(req.url);
    url.protocol = 'https:';
    url.hostname = env.SPACE_HOST;
    url.port = '';

    const h = new Headers(req.headers);
    h.set('Host', env.SPACE_HOST);
    h.set('Origin', 'https://' + env.SPACE_HOST);
    if (env.HF_TOKEN) h.set('Authorization', 'Bearer ' + env.HF_TOKEN);

    const upstream = await fetch(url.toString(), {
      method: req.method,
      headers: h,
      body: (req.method === 'GET' || req.method === 'HEAD') ? undefined : req.body,
      redirect: 'manual',
    });

    const out = new Headers(upstream.headers);
    const loc = out.get('location');
    if (loc && loc.includes(env.SPACE_HOST)) {
      out.set('location', loc.replace('https://' + env.SPACE_HOST, 'https://' + inUrl.hostname));
    }
    // app ki login cookie hamare domain par lagni chahiye, Space ke nahi
    const cookies = out.getAll ? out.getAll('set-cookie') : [];
    if (cookies.length) {
      out.delete('set-cookie');
      for (const c of cookies) out.append('set-cookie', c.replace(/;\s*Domain=[^;]*/i, ''));
    }
    return new Response(upstream.body, { status: upstream.status, headers: out });
  },
};
