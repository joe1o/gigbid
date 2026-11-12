"""
build_report.py - turn docs/REPORT.md into docs/REPORT.pdf (the R&D report the brief asks for).

    python scripts/build_report.py

Step 1: Markdown -> HTML with a plain, print-friendly style (black and grey only).
Step 2: Chromium (installed with Playwright for the browser tests) prints the HTML to an A4 PDF.
Needs: `pip install markdown` and `cd apps/web && npm ci && npx playwright install chromium`.
"""

import subprocess
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SRC, HTML, PDF = ROOT / "docs/REPORT.md", ROOT / "docs/REPORT.html", ROOT / "docs/REPORT.pdf"

CSS = """
@page { size: A4; margin: 15mm 15mm 16mm 15mm; }
body { font-family: Georgia, 'Times New Roman', serif; font-size: 9.6pt; line-height: 1.38; color: #111; }
h1 { font-size: 17pt; margin: 0 0 4pt; }
h2 { font-size: 12pt; margin: 13pt 0 4pt; border-bottom: 0.6pt solid #888; padding-bottom: 2pt;
     break-after: avoid; }
p, li { margin: 3pt 0; }
ul { padding-left: 15pt; margin: 3pt 0; }
table { border-collapse: collapse; width: 100%; margin: 5pt 0; font-size: 8.2pt; break-inside: avoid; }
th, td { border: 0.5pt solid #999; padding: 2.2pt 4pt; text-align: left; vertical-align: top; }
th { background: #eee; }
code { font-family: Consolas, 'Courier New', monospace; font-size: 8.4pt; }
pre { background: #f4f4f4; border: 0.5pt solid #ccc; padding: 5pt; font-size: 7.8pt;
      line-height: 1.25; white-space: pre-wrap; break-inside: avoid; }
pre code { font-size: 7.8pt; }
a { color: #111; text-decoration: none; }
"""

# Node + Playwright print the page; run from apps/web so `require("playwright")` resolves.
PRINT_JS = f"""
const {{ chromium }} = require("playwright");
(async () => {{
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto("file:///{HTML.as_posix()}");
  await p.pdf({{ path: "{PDF.as_posix()}", format: "A4", printBackground: true,
                displayHeaderFooter: true, headerTemplate: "<span></span>",
                footerTemplate: '<div style="font-size:7pt;width:100%;text-align:center;color:#555">' +
                  'GigBid R&amp;D report, page <span class="pageNumber"></span> of <span class="totalPages"></span></div>',
                margin: {{ top: "15mm", bottom: "16mm", left: "15mm", right: "15mm" }} }});
  await b.close();
}})();
"""

body = markdown.markdown(SRC.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
HTML.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>GigBid R&D Report</title>"
                f"<style>{CSS}</style></head><body>{body}</body></html>", encoding="utf-8")
subprocess.run(["node", "-e", PRINT_JS], cwd=ROOT / "apps/web", check=True, shell=False)
HTML.unlink()
print(f"wrote {PDF.relative_to(ROOT)}")
