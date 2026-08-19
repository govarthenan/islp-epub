/*
 * Render LaTeX to standalone SVG files with MathJax.
 *
 * Usage: node src/render_math.cjs <jobs.json> <out-dir> <manifest.json>
 *
 * jobs.json is [{ "id": "m00001", "tex": "\\hat{f}", "display": false }, ...]
 *
 * Each SVG is self-contained (fontCache "local") and sized in em, so it scales with the
 * reader's font size instead of being pinned to pixels.
 *
 * MathJax draws in currentColor, but these files are referenced with <img>, and an <img>
 * is a separate document: currentColor there resolves against the SVG's own root, not
 * against the page, so it always came out black. Each file therefore carries the two rules
 * below. A reader that declares a dark colour scheme passes that scheme down to the image,
 * and the mathematics turns white with the rest of the text. A reader that instead inverts
 * the whole screen, which is what e-ink devices do, matches neither rule, keeps the black,
 * and inverts it itself.
 */
const COLOUR_SCHEME_STYLE =
  '<style>svg{color:#000}@media (prefers-color-scheme:dark){svg{color:#fff}}</style>';

const fs = require('fs');
const path = require('path');

const { mathjax } = require('mathjax-full/js/mathjax.js');
const { TeX } = require('mathjax-full/js/input/tex.js');
const { SVG } = require('mathjax-full/js/output/svg.js');
const { liteAdaptor } = require('mathjax-full/js/adaptors/liteAdaptor.js');
const { RegisterHTMLHandler } = require('mathjax-full/js/handlers/html.js');
const { AllPackages } = require('mathjax-full/js/input/tex/AllPackages.js');

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);

const tex = new TeX({ packages: AllPackages });
const svg = new SVG({ fontCache: 'local' });
const html = mathjax.document('', { InputJax: tex, OutputJax: svg });

const EX_PER_EM = 0.5; // MathJax's default metric relationship

function sizeOf(node) {
  const style = adaptor.getAttribute(node, 'style') || '';
  const width = adaptor.getAttribute(node, 'width') || '';
  const height = adaptor.getAttribute(node, 'height') || '';
  const alignMatch = style.match(/vertical-align:\s*(-?[\d.]+)ex/);
  const toEm = (value) => {
    const match = String(value).match(/(-?[\d.]+)ex/);
    return match ? parseFloat(match[1]) * EX_PER_EM : null;
  };
  return {
    widthEm: toEm(width),
    heightEm: toEm(height),
    valignEm: alignMatch ? parseFloat(alignMatch[1]) * EX_PER_EM : 0,
  };
}

function main() {
  const [jobsPath, outDir, manifestPath] = process.argv.slice(2);
  const jobs = JSON.parse(fs.readFileSync(jobsPath, 'utf8'));
  fs.mkdirSync(outDir, { recursive: true });

  const manifest = {};
  const failures = [];

  for (const job of jobs) {
    let node;
    try {
      node = html.convert(job.tex, {
        display: Boolean(job.display),
        em: 16,
        ex: 8,
        containerWidth: 80 * 16,
      });
    } catch (error) {
      failures.push({ id: job.id, tex: job.tex, error: String(error.message || error) });
      continue;
    }
    const inner = adaptor.innerHTML(node);
    // MathJax reports a TeX error by drawing the source in red rather than by throwing.
    const errorMatch = inner.match(/data-mjx-error="([^"]*)"/);
    if (errorMatch || inner.includes('fill="red"')) {
      failures.push({
        id: job.id,
        tex: job.tex,
        error: errorMatch ? errorMatch[1] : 'rendered as a TeX error',
      });
      continue;
    }
    const svgNode = adaptor.firstChild(node);
    const size = sizeOf(svgNode);
    let markup = inner;
    if (!markup.startsWith('<svg')) {
      const at = markup.indexOf('<svg');
      markup = at >= 0 ? markup.slice(at) : markup;
    }
    if (!markup.includes('xmlns="http://www.w3.org/2000/svg"')) {
      markup = markup.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ');
    }
    // MathJax repeats the namespace declarations; XHTML parsers reject duplicate attributes.
    markup = markup.replace(
      /<svg((?:\s+[^>]*?)?)>/,
      (whole, attrs) => {
        const seen = new Set();
        const kept = [];
        const attrRe = /([\w:-]+)="([^"]*)"/g;
        let match;
        while ((match = attrRe.exec(attrs)) !== null) {
          if (seen.has(match[1])) continue;
          seen.add(match[1]);
          kept.push(`${match[1]}="${match[2]}"`);
        }
        return `<svg ${kept.join(' ')}>`;
      },
    );
    const title = job.tex.replace(/[&<>]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]));
    markup = markup.replace('>', `>${COLOUR_SCHEME_STYLE}<title>${title}</title>`);
    const file = path.join(outDir, `${job.id}.svg`);
    fs.writeFileSync(file, `<?xml version="1.0" encoding="UTF-8"?>\n${markup}\n`);
    manifest[job.id] = {
      file: `${job.id}.svg`,
      widthEm: size.widthEm,
      heightEm: size.heightEm,
      valignEm: size.valignEm,
      display: Boolean(job.display),
      tex: job.tex,
    };
  }

  fs.writeFileSync(manifestPath, JSON.stringify({ manifest, failures }, null, 1));
  console.log(`rendered ${Object.keys(manifest).length} / ${jobs.length}, ${failures.length} failures`);
  if (failures.length) {
    for (const failure of failures.slice(0, 20)) {
      console.log(`  FAIL ${failure.id}: ${failure.error} :: ${failure.tex}`);
    }
  }
}

main();
