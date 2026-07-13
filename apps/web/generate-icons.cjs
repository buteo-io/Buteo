const sharp = require("sharp");
const fs = require("fs");
const path = require("path");

const svgPath = path.join(__dirname, "public/icon.svg");
const outputDir = path.join(__dirname, "public");

const sizes = [
  { name: "buteo-pwa-16.png", size: 16 },
  { name: "buteo-pwa-192.png", size: 192 },
  { name: "buteo-pwa-512.png", size: 512 },
];

const svg = fs.readFileSync(svgPath);

Promise.all(
  sizes.map(({ name, size }) =>
    sharp(svg).resize(size, size).png().toFile(path.join(outputDir, name)),
  ),
).then(() => console.log("Icons generated!"));
