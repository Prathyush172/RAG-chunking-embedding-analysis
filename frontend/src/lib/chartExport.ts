/**
 * frontend/src/lib/chartExport.ts — Shared chart download utility (SVG and PNG).
 */

export function downloadChartSvg(containerId: string, filename: string = "chart"): void {
  const container = document.getElementById(containerId);
  if (!container) {
    console.error(`Chart container with id '${containerId}' not found.`);
    return;
  }

  const svg = container.querySelector("svg");
  if (!svg) {
    console.error(`No SVG element found inside container '${containerId}'.`);
    return;
  }

  const serializer = new XMLSerializer();
  let source = serializer.serializeToString(svg);

  // Add namespaces if not present
  if (!source.match(/^<svg[^>]+xmlns="http:\/\/www\.w3\.org\/2000\/svg"/)) {
    source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
  }
  if (!source.match(/^<svg[^>]+xmlns:xlink="http:\/\/www\.w3\.org\/1999\/xlink"/)) {
    source = source.replace(/^<svg/, '<svg xmlns:xlink="http://www.w3.org/1999/xlink"');
  }

  const blob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const downloadLink = document.createElement("a");
  downloadLink.href = url;
  downloadLink.download = `${filename}.svg`;
  document.body.appendChild(downloadLink);
  downloadLink.click();
  document.body.removeChild(downloadLink);
  URL.revokeObjectURL(url);
}

export function downloadChartPng(containerId: string, filename: string = "chart", scale: number = 2): void {
  const container = document.getElementById(containerId);
  if (!container) {
    console.error(`Chart container with id '${containerId}' not found.`);
    return;
  }

  const svg = container.querySelector("svg");
  if (!svg) {
    console.error(`No SVG element found inside container '${containerId}'.`);
    return;
  }

  const serializer = new XMLSerializer();
  let source = serializer.serializeToString(svg);

  if (!source.match(/^<svg[^>]+xmlns="http:\/\/www\.w3\.org\/2000\/svg"/)) {
    source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
  }

  const svgBlob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);

  const img = new Image();
  img.onload = () => {
    const canvas = document.createElement("canvas");
    const width = svg.clientWidth || 800;
    const height = svg.clientHeight || 500;
    canvas.width = width * scale;
    canvas.height = height * scale;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.scale(scale, scale);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(img, 0, 0, width, height);

    const pngUrl = canvas.toDataURL("image/png");
    const downloadLink = document.createElement("a");
    downloadLink.href = pngUrl;
    downloadLink.download = `${filename}.png`;
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
    URL.revokeObjectURL(url);
  };
  img.src = url;
}
