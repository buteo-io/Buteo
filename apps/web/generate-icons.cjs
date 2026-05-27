const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

const svgPath = path.join(__dirname, 'public/icon.svg');
const outputDir = path.join(__dirname, 'public');

const sizes = [
  { name: 'icon-180.png', size: 180 },
  { name: 'icon-167.png', size: 167 },
  { name: 'icon-152.png', size: 152 },
  { name: 'icon-120.png', size: 120 },
  { name: 'icon-128.png', size: 128 },
  { name: 'icon-192.png', size: 192 },
  { name: 'icon-512.png', size: 512 },
];

const svg = fs.readFileSync(svgPath);

Promise.all(sizes.map(({ name, size }) =>
  sharp(svg)
    .resize(size, size)
    .png()
    .toFile(path.join(outputDir, name))
)).then(() => console.log('Icons generated!'));
