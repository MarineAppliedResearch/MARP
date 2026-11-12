// A local viewer for the habitat datasets: every frame with its labels, by year, split,
// substrate and dive, and each dive's labels as a timeline. See README.md.
// Run: node serve.js <experiment folder> [port]
// Then open the address it prints. Only this machine can reach it.
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');

// The folder the habitat pipeline writes to: its CSVs, and the pictures they name.
const EXPERIMENT = process.argv[2] ? path.resolve(process.argv[2]) : null;
if (!EXPERIMENT || !fs.existsSync(path.join(EXPERIMENT, 'dataset.csv'))) {
    console.error('usage: node serve.js <experiment folder> [port]');
    console.error('  the folder holding dataset.csv, e.g. MARP_API/.marp/habitat/experiment on branch 287-habitat-classification');
    process.exit(2);
}
const PORT = Number(process.argv[3]) || 8287;
const TYPES = { '.html': 'text/html; charset=utf-8', '.csv': 'text/csv; charset=utf-8', '.jpg': 'image/jpeg' };

// A dataset is any CSV here whose first column is a picture; nothing else in the folder is served.
function datasets() {
    return fs.readdirSync(EXPERIMENT).filter((name) => {
        if (!name.endsWith('.csv')) return false;
        const fd = fs.openSync(path.join(EXPERIMENT, name), 'r');
        const head = Buffer.alloc(6);
        fs.readSync(fd, head, 0, 6, 0);
        fs.closeSync(fd);
        return head.toString() === 'image,';
    });
}

function send(res, file) {
    fs.stat(file, (err, stat) => {
        if (err || !stat.isFile()) { res.writeHead(404); return res.end('not found'); }
        res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream', 'Content-Length': stat.size });
        fs.createReadStream(file).pipe(res);
    });
}

http.createServer((req, res) => {
    const url = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    if (url === '/') return send(res, path.join(__dirname, 'index.html'));
    if (url === '/datasets') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify(datasets()));
    }
    if (url.startsWith('/data/') && datasets().includes(url.slice(6))) return send(res, path.join(EXPERIMENT, url.slice(6)));
    // Pictures only, and only from under this folder: a path that climbs out is refused.
    const file = path.resolve(EXPERIMENT, '.' + url);
    if (file.startsWith(EXPERIMENT + path.sep) && file.endsWith('.jpg')) return send(res, file);
    res.writeHead(404);
    res.end('not found');
}).listen(PORT, '127.0.0.1', () => console.log(`habitat dataset viewer: http://localhost:${PORT}/`));
