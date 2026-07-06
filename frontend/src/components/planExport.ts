// PNG export of the live 2D plan svg. The exporter is registered by
// PlanView2D while it is mounted (2D view active); the Export tab calls it
// through this module so the two components stay decoupled.

type Exporter = () => void;
let handler: Exporter | null = null;

export function registerPlanPngExporter(h: Exporter | null): void {
  handler = h;
}

export function exportPlanPng(): void {
  handler?.();
}

const PX_PER_M = 60; // world metres → bitmap pixels (×2 canvas = crisp on phones)

export function downloadSvgAsPng(
  svgEl: SVGSVGElement,
  fit: { x: number; y: number; w: number; h: number },
  fileBase: string
): void {
  const clone = svgEl.cloneNode(true) as SVGSVGElement;
  // Export the whole fitted plan regardless of the current pan/zoom.
  clone.setAttribute("viewBox", `${fit.x} ${fit.y} ${fit.w} ${fit.h}`);
  const w = Math.round(fit.w * PX_PER_M);
  const h = Math.round(fit.h * PX_PER_M);
  clone.setAttribute("width", String(w));
  clone.setAttribute("height", String(h));
  // SVG rendered inside an <img> can't reach the page stylesheet, so the
  // Tailwind font classes must become inline font-family chains.
  clone.style.fontFamily = "Inter, Arial, sans-serif";
  clone.querySelectorAll<SVGElement>(".font-mono").forEach((el) => {
    el.style.fontFamily = "'JetBrains Mono', Consolas, monospace";
  });

  const xml = new XMLSerializer().serializeToString(clone);
  const url = URL.createObjectURL(new Blob([xml], { type: "image/svg+xml;charset=utf-8" }));
  const img = new Image();
  img.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = w * 2;
    canvas.height = h * 2;
    const ctx = canvas.getContext("2d");
    if (!ctx) return URL.revokeObjectURL(url);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(url);
    canvas.toBlob((png) => {
      if (!png) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(png);
      a.download = `${fileBase}.png`;
      a.click();
      URL.revokeObjectURL(a.href);
    }, "image/png");
  };
  img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
}
