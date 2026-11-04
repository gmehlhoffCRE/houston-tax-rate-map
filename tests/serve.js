// Static file server with HTTP Range support (PMTiles needs 206 responses) and CORS, for local testing.
//   node serve.js <root> [port]
const http = require('http'), fs = require('fs'), path = require('path');
const root = path.resolve(process.argv[2] || '.'), port = +(process.argv[3] || 8080);
const types = { '.html': 'text/html; charset=utf-8', '.js': 'application/javascript', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.pmtiles': 'application/octet-stream', '.css': 'text/css' };
http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0]));
  if (!p.startsWith(root)) { res.writeHead(403); return res.end(); }
  fs.stat(p, (err, st) => {
    if (err || !st.isFile()) { res.writeHead(404, { 'Access-Control-Allow-Origin': '*' }); return res.end('not found'); }
    const h = { 'Content-Type': types[path.extname(p)] || 'application/octet-stream', 'Accept-Ranges': 'bytes',
      'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'ETag, Content-Range, Content-Length',
      'ETag': `"${st.size}-${st.mtimeMs}"` };
    const m = /bytes=(\d+)-(\d*)/.exec(req.headers.range || '');
    if (m) {
      const start = +m[1], end = m[2] ? Math.min(+m[2], st.size - 1) : st.size - 1;
      res.writeHead(206, { ...h, 'Content-Range': `bytes ${start}-${end}/${st.size}`, 'Content-Length': end - start + 1 });
      return fs.createReadStream(p, { start, end }).pipe(res);
    }
    res.writeHead(200, { ...h, 'Content-Length': st.size });
    fs.createReadStream(p).pipe(res);
  });
}).listen(port, () => console.log(`serving ${root} on http://localhost:${port}`));
