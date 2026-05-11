// Cross-platform vendor script. Copies React + ReactDOM UMD builds from
// node_modules into static/vendor/react/ so the landing page can load
// them as plain <script> tags without a CDN. Works on Windows, macOS,
// and Linux without shell-syntax differences.

const fs = require('fs');
const path = require('path');

const TARGET_DIR = path.join('static', 'vendor', 'react');
const FILES = [
  ['react', 'umd/react.production.min.js'],
  ['react-dom', 'umd/react-dom.production.min.js'],
];

fs.mkdirSync(TARGET_DIR, { recursive: true });

for (const [pkg, rel] of FILES) {
  const src = path.join('node_modules', pkg, rel);
  const dst = path.join(TARGET_DIR, path.basename(rel));
  if (!fs.existsSync(src)) {
    console.error(`Source missing: ${src}`);
    console.error(`Run "npm install" first.`);
    process.exit(1);
  }
  fs.copyFileSync(src, dst);
  console.log(`vendored: ${dst}`);
}

console.log('React vendored successfully.');