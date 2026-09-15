const { createServer } = require('http');
const { parse } = require('url');
const next = require('next');
const fs = require('fs');
const path = require('path');

const dev = process.env.NODE_ENV !== 'production';
const hostname = '0.0.0.0';
const port = parseInt(process.env.PORT, 10) || 3000;

const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

// Resolve the virtual CSS path to the actual hashed file
function resolveCssPath(virtualPath) {
  try {
    const cssDir = path.join(__dirname, '.next', 'static', 'css');
    if (!fs.existsSync(cssDir)) return null;

    // If the requested file already exists on disk, serve it
    const directPath = path.join(__dirname, '.next', virtualPath);
    if (fs.existsSync(directPath)) return directPath;

    // Map "app/layout.css" or "app/*.css" to the largest CSS file in .next/static/css/
    const files = fs.readdirSync(cssDir).filter(f => f.endsWith('.css') && !f.includes('/'));
    if (files.length === 0) return null;

    // Use the largest CSS file (the main bundle)
    const mainCss = files.sort((a, b) => {
      const sa = fs.statSync(path.join(cssDir, a)).size;
      const sb = fs.statSync(path.join(cssDir, b)).size;
      return sb - sa;
    })[0];
    return path.join(cssDir, mainCss);
  } catch {
    return null;
  }
}

app.prepare().then(() => {
  createServer(async (req, res) => {
    try {
      const parsedUrl = parse(req.url, true);

      // Intercept virtual CSS paths: /_next/static/css/app/*.css
      if (parsedUrl.pathname && parsedUrl.pathname.match(/^\/_next\/static\/css\/app\/.+\.css$/)) {
        const resolved = resolveCssPath(parsedUrl.pathname.replace(/^\/_next\//, '.next/'));
        if (resolved) {
          const cssContent = fs.readFileSync(resolved);
          res.setHeader('Content-Type', 'text/css');
          res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
          res.end(cssContent);
          return;
        }
      }

      await handle(req, res, parsedUrl);
    } catch (err) {
      console.error('Error handling', req.url, err);
      res.statusCode = 500;
      res.end('Internal Server Error');
    }
  }).listen(port, hostname, () => {
    console.log(`> Ready on http://${hostname}:${port}`);
  });
});
