const fs = require("node:fs");
const path = require("node:path");

// Next.js adds .next/dev/types to tsconfig. A dev server can leave validator
// files for routes that have since been moved, so remove only that generated
// cache before a production build. The production .next output is preserved.
const devCache = path.resolve(__dirname, "..", ".next", "dev");
fs.rmSync(devCache, { recursive: true, force: true });
