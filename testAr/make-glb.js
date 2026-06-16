#!/usr/bin/env node
/**
 * Генератор GLB для килима: тонкий прямокутник (площина) з накладеною текстурою.
 * Без залежностей — вручну збирає бінарний GLB (glTF 2.0). Байти зображення
 * вшиваються в bufferView (image/jpeg|png), декодувати не потрібно.
 *
 * PNG з прозорістю (alpha) → автоматично вмикається прозорість матеріалу,
 * тож килим може бути будь-якої форми (круг/овал/фігурний) і мати бахрому по краях:
 * форму й торочку задає сам PNG (прозорий фон + напівпрозорі волосинки).
 *
 * Використання:
 *   node make-glb.js <texture> <width_m> <length_m> <output.glb> [alphaMode]
 *
 *   alphaMode (необов'язково):
 *     auto    — (за замовч.) PNG з alpha → BLEND, без alpha / JPEG → OPAQUE
 *     opaque  — без прозорості (повний прямокутник)
 *     mask    — різкий виріз по контуру (alphaCutoff 0.5); добре для чітких форм
 *     blend   — м'яка прозорість; добре для бахроми/торочки з плавним краєм
 *
 * Приклади:
 *   node make-glb.js test.jpg 1 2 ar/carpet.glb
 *   node make-glb.js rug-round.png 1.6 1.6 ar/rug-round.glb        # форма з PNG
 *   node make-glb.js rug-fringe.png 1.2 1.8 ar/rug.glb blend       # бахрома
 */
import fs from 'fs';
import path from 'path';

const [, , texArg = 'test.jpg', wArg = '1', lArg = '2', outArg = 'ar/carpet.glb', modeArg = 'auto'] = process.argv;

const W = parseFloat(wArg);      // ширина (вісь X), м — включно з бахромою
const L = parseFloat(lArg);      // довжина (вісь Z), м — включно з бахромою
const LIFT = 0.005;              // підняти на 5 мм над підлогою (проти z-fighting)
const texPath = path.resolve(texArg);
const outPath = path.resolve(outArg);

const texBytes = fs.readFileSync(texPath);

// --- Визначення формату й наявності alpha ---
function detectImage(buf, ext) {
  const PNG_SIG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  const isPng = PNG_SIG.every((b, i) => buf[i] === b);
  if (isPng) {
    // IHDR: байт colorType — на зміщенні 25 (8 sig + 4 len + 4 "IHDR" + 9)
    const colorType = buf[25];
    let hasAlpha = colorType === 4 || colorType === 6; // 4=GA, 6=RGBA
    if (colorType === 3) {
      // палітра: прозорість задається чанком tRNS — шукаємо його
      let o = 8;
      while (o + 12 <= buf.length) {
        const len = buf.readUInt32BE(o);
        const type = buf.toString('ascii', o + 4, o + 8);
        if (type === 'tRNS') { hasAlpha = true; break; }
        if (type === 'IDAT' || type === 'IEND') break;
        o += 12 + len;
      }
    }
    return { mimeType: 'image/png', hasAlpha };
  }
  if (buf[0] === 0xff && buf[1] === 0xd8) return { mimeType: 'image/jpeg', hasAlpha: false };
  // фолбек за розширенням
  return { mimeType: ext === '.png' ? 'image/png' : 'image/jpeg', hasAlpha: ext === '.png' };
}

const { mimeType, hasAlpha } = detectImage(texBytes, path.extname(texPath).toLowerCase());

// --- Визначення режиму прозорості ---
let alphaMode;
const m = modeArg.toLowerCase();
if (m === 'auto') alphaMode = hasAlpha ? 'BLEND' : 'OPAQUE';
else if (['opaque', 'mask', 'blend'].includes(m)) alphaMode = m.toUpperCase();
else { console.error(`Невідомий alphaMode "${modeArg}". Дозволено: auto|opaque|mask|blend`); process.exit(1); }

// --- Геометрія: 4 вершини площини на XZ, нормаль +Y ---
const hx = W / 2, hz = L / 2, y = LIFT;
const positions = [-hx, y, -hz, hx, y, -hz, hx, y, hz, -hx, y, hz];
const normals = [0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0];
const uvs = [0, 1, 1, 1, 1, 0, 0, 0];
const indices = [0, 2, 1, 0, 3, 2];
const posMin = [-hx, y, -hz];
const posMax = [hx, y, hz];

// --- Бінарні буфери (little-endian) ---
function f32(arr) {
  const b = Buffer.alloc(arr.length * 4);
  arr.forEach((v, i) => b.writeFloatLE(v, i * 4));
  return b;
}
function u16(arr) {
  const b = Buffer.alloc(arr.length * 2);
  arr.forEach((v, i) => b.writeUInt16LE(v, i * 2));
  return b;
}
function pad4(buf, fill = 0x00) {
  const rem = buf.length % 4;
  return rem === 0 ? buf : Buffer.concat([buf, Buffer.alloc(4 - rem, fill)]);
}

const posBuf = f32(positions);
const normBuf = f32(normals);
const uvBuf = f32(uvs);
const idxBuf = pad4(u16(indices));
const imgBuf = texBytes;

let off = 0;
const posOff = off; off += posBuf.length;
const normOff = off; off += normBuf.length;
const uvOff = off; off += uvBuf.length;
const idxOff = off; off += idxBuf.length;
const imgOff = off; off += imgBuf.length;
const binLengthActual = off;
const bin = Buffer.concat([posBuf, normBuf, uvBuf, idxBuf, imgBuf]);

// --- Матеріал ---
const material = {
  name: 'carpet',
  pbrMetallicRoughness: { baseColorTexture: { index: 0 }, metallicFactor: 0, roughnessFactor: 0.9 },
  doubleSided: true,
};
if (alphaMode === 'MASK') { material.alphaMode = 'MASK'; material.alphaCutoff = 0.5; }
else if (alphaMode === 'BLEND') { material.alphaMode = 'BLEND'; }
// OPAQUE — типове значення glTF, поле не додаємо

const gltf = {
  asset: { version: '2.0', generator: 'mrCarpet make-glb' },
  scene: 0,
  scenes: [{ nodes: [0] }],
  nodes: [{ mesh: 0, name: 'carpet' }],
  meshes: [{ primitives: [{ attributes: { POSITION: 0, NORMAL: 1, TEXCOORD_0: 2 }, indices: 3, material: 0 }] }],
  materials: [material],
  textures: [{ sampler: 0, source: 0 }],
  images: [{ bufferView: 4, mimeType }],
  samplers: [{ magFilter: 9729, minFilter: 9987, wrapS: 10497, wrapT: 10497 }],
  accessors: [
    { bufferView: 0, componentType: 5126, count: 4, type: 'VEC3', min: posMin, max: posMax },
    { bufferView: 1, componentType: 5126, count: 4, type: 'VEC3' },
    { bufferView: 2, componentType: 5126, count: 4, type: 'VEC2' },
    { bufferView: 3, componentType: 5123, count: 6, type: 'SCALAR' },
  ],
  bufferViews: [
    { buffer: 0, byteOffset: posOff, byteLength: posBuf.length, target: 34962 },
    { buffer: 0, byteOffset: normOff, byteLength: normBuf.length, target: 34962 },
    { buffer: 0, byteOffset: uvOff, byteLength: uvBuf.length, target: 34962 },
    { buffer: 0, byteOffset: idxOff, byteLength: idxBuf.length, target: 34963 },
    { buffer: 0, byteOffset: imgOff, byteLength: imgBuf.length },
  ],
  buffers: [{ byteLength: binLengthActual }],
};

// --- Збірка GLB ---
function chunk(typeAscii, data) {
  const h = Buffer.alloc(8);
  h.writeUInt32LE(data.length, 0);
  h.write(typeAscii, 4, 'ascii');
  return Buffer.concat([h, data]);
}
const jsonChunk = pad4(Buffer.from(JSON.stringify(gltf), 'utf8'), 0x20);
const binChunkData = pad4(bin, 0x00);
const binHeader = Buffer.alloc(8);
binHeader.writeUInt32LE(binChunkData.length, 0);
binHeader.set([0x42, 0x49, 0x4e, 0x00], 4); // "BIN\0"
const binChunkFull = Buffer.concat([binHeader, binChunkData]);
const jsonChunkFull = chunk('JSON', jsonChunk);

const header = Buffer.alloc(12);
header.write('glTF', 0, 'ascii');
header.writeUInt32LE(2, 4);
header.writeUInt32LE(12 + jsonChunkFull.length + binChunkFull.length, 8);

const glb = Buffer.concat([header, jsonChunkFull, binChunkFull]);

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, glb);

console.log(`✅ GLB створено: ${outPath}`);
console.log(`   килим: ${W}м × ${L}м | текстура: ${path.basename(texPath)} (${mimeType}, alpha=${hasAlpha})`);
console.log(`   прозорість: ${alphaMode}${alphaMode === 'MASK' ? ' (cutoff 0.5)' : ''}`);
console.log(`   файл: ${(glb.length / 1024).toFixed(1)} KB`);
