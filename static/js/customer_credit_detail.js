(() => {
  "use strict";
  const ns = "http://www.w3.org/2000/svg";
  const money = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
  const compact = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 1 });

  const readData = (id) => {
    const node = document.getElementById(id);
    if (!node) return [];
    try { return JSON.parse(node.textContent || "[]"); } catch (_error) { return []; }
  };
  const svgNode = (name, attributes = {}) => {
    const node = document.createElementNS(ns, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  };
  const text = (svg, value, x, y, anchor = "middle") => {
    const node = svgNode("text", { x, y, "text-anchor": anchor, class: "credit-detail-axis" });
    node.textContent = value;
    svg.appendChild(node);
  };
  const chartFrame = (svg, values) => {
    const frame = { width: 900, height: 310, left: 92, right: 28, top: 22, bottom: 58 };
    frame.plotWidth = frame.width - frame.left - frame.right;
    frame.plotHeight = frame.height - frame.top - frame.bottom;
    const rawMax = Math.max(...values, 1);
    const magnitude = 10 ** Math.floor(Math.log10(rawMax));
    frame.maximum = Math.ceil(rawMax / magnitude) * magnitude;
    frame.y = (value) => frame.top + frame.plotHeight - Number(value) / frame.maximum * frame.plotHeight;
    for (let index = 0; index <= 4; index += 1) {
      const value = frame.maximum * index / 4;
      const y = frame.y(value);
      svg.appendChild(svgNode("line", { x1: frame.left, x2: frame.width - frame.right, y1: y, y2: y, class: "credit-detail-grid" }));
      text(svg, compact.format(value), frame.left - 12, y + 4, "end");
    }
    return frame;
  };

  const history = readData("customerExposureHistoryData");
  const trendSvg = document.getElementById("customerExposureTrend");
  if (trendSvg && history.length) {
    const frame = chartFrame(trendSvg, history.map((item) => Number(item.value)));
    const x = (index) => frame.left + (history.length === 1 ? frame.plotWidth / 2 : index / (history.length - 1) * frame.plotWidth);
    const coordinates = history.map((item, index) => `${x(index)},${frame.y(item.value)}`);
    if (history.length > 1) trendSvg.appendChild(svgNode("polyline", { points: coordinates.join(" "), class: "credit-detail-line" }));
    const labelStep = Math.max(1, Math.ceil(history.length / 8));
    history.forEach((item, index) => {
      const point = svgNode("circle", { cx: x(index), cy: frame.y(item.value), r: 5.5, class: "credit-detail-point" });
      const title = svgNode("title"); title.textContent = `${item.label}: ${money.format(item.value)}`; point.appendChild(title); trendSvg.appendChild(point);
      if (index % labelStep === 0 || index === history.length - 1) text(trendSvg, item.label, x(index), frame.height - 22);
    });
  }

  const aging = readData("customerAgingData");
  const agingSvg = document.getElementById("customerAgingChart");
  if (agingSvg && aging.length) {
    const frame = chartFrame(agingSvg, aging.map((item) => Number(item.value)));
    const slot = frame.plotWidth / aging.length;
    aging.forEach((item, index) => {
      const x = frame.left + index * slot + slot * 0.18;
      const y = frame.y(item.value);
      const bar = svgNode("rect", { x, y, width: slot * 0.64, height: frame.top + frame.plotHeight - y, rx: 5, class: "credit-detail-bar" });
      const title = svgNode("title"); title.textContent = `${item.label}: ${money.format(item.value)}`; bar.appendChild(title); agingSvg.appendChild(bar);
      text(agingSvg, item.label, x + slot * 0.32, frame.height - 22);
      text(agingSvg, compact.format(item.value), x + slot * 0.32, Math.max(frame.top + 14, y - 8));
    });
  }
})();
