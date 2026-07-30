(() => {
  "use strict";

  const dataNode = document.getElementById("customerCreditData");
  const svg = document.getElementById("customerCreditPie");
  const legend = document.getElementById("customerCreditLegend");
  if (!dataNode || !svg || !legend) return;

  let items;
  try {
    items = JSON.parse(dataNode.textContent || "[]").filter((item) => Number(item.value) > 0);
  } catch (_error) {
    return;
  }
  if (!items.length) return;

  const namespace = "http://www.w3.org/2000/svg";
  const total = items.reduce((sum, item) => sum + Number(item.value), 0);
  const money = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
  const point = (angle) => {
    const radians = (angle - 90) * Math.PI / 180;
    return { x: 120 + 105 * Math.cos(radians), y: 120 + 105 * Math.sin(radians) };
  };
  const colorFor = (index) => `hsl(${(index * 137.508 + 205) % 360} 62% 52%)`;

  let startAngle = 0;
  items.forEach((item, index) => {
    const sweep = Number(item.value) / total * 360;
    const color = colorFor(index);
    const link = document.createElementNS(namespace, "a");
    link.setAttribute("href", item.url);
    link.setAttribute("aria-label", `${item.label}: ${money.format(item.value)}`);

    let shape;
    if (items.length === 1) {
      shape = document.createElementNS(namespace, "circle");
      shape.setAttribute("cx", "120");
      shape.setAttribute("cy", "120");
      shape.setAttribute("r", "105");
    } else {
      const start = point(startAngle);
      const end = point(startAngle + sweep);
      shape = document.createElementNS(namespace, "path");
      shape.setAttribute(
        "d",
        `M 120 120 L ${start.x} ${start.y} A 105 105 0 ${sweep > 180 ? 1 : 0} 1 ${end.x} ${end.y} Z`
      );
    }
    shape.setAttribute("fill", color);
    shape.setAttribute("class", "credit-pie-slice");
    const title = document.createElementNS(namespace, "title");
    title.textContent = `${item.label}: ${money.format(item.value)} (${(Number(item.value) / total * 100).toFixed(1)}%)`;
    shape.appendChild(title);
    link.appendChild(shape);
    svg.appendChild(link);

    const legendLink = document.createElement("a");
    legendLink.href = item.url;
    legendLink.className = "credit-legend-item";
    legendLink.innerHTML = `
      <span class="credit-legend-color" style="background:${color}"></span>
      <span class="credit-legend-label">${escapeHtml(item.label)}</span>
      <strong>${money.format(item.value)}</strong>
      <small>${(Number(item.value) / total * 100).toFixed(1)}%</small>
    `;
    legend.appendChild(legendLink);
    startAngle += sweep;
  });

  renderTrend();

  function escapeHtml(value) {
    const node = document.createElement("span");
    node.textContent = String(value);
    return node.innerHTML;
  }

  function renderTrend() {
    const historyNode = document.getElementById("customerCreditHistoryData");
    const trendSvg = document.getElementById("customerCreditTrend");
    if (!historyNode || !trendSvg) return;

    let points;
    try {
      points = JSON.parse(historyNode.textContent || "[]");
    } catch (_error) {
      return;
    }
    if (!points.length) return;

    const width = 900;
    const height = 330;
    const margin = { top: 24, right: 28, bottom: 58, left: 92 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const rawMaximum = Math.max(...points.map((item) => Number(item.value) || 0), 1);
    const magnitude = 10 ** Math.floor(Math.log10(rawMaximum));
    const maximum = Math.ceil(rawMaximum / magnitude) * magnitude;
    const compactMoney = new Intl.NumberFormat("it-IT", {
      style: "currency",
      currency: "EUR",
      notation: "compact",
      maximumFractionDigits: 1
    });
    const xAt = (index) => margin.left + (points.length === 1 ? plotWidth / 2 : index / (points.length - 1) * plotWidth);
    const yAt = (value) => margin.top + plotHeight - (Number(value) / maximum * plotHeight);
    const addText = (text, x, y, className, anchor = "middle") => {
      const node = document.createElementNS(namespace, "text");
      node.textContent = text;
      node.setAttribute("x", x);
      node.setAttribute("y", y);
      node.setAttribute("text-anchor", anchor);
      node.setAttribute("class", className);
      trendSvg.appendChild(node);
    };

    for (let index = 0; index <= 4; index += 1) {
      const value = maximum * index / 4;
      const y = yAt(value);
      const line = document.createElementNS(namespace, "line");
      line.setAttribute("x1", margin.left);
      line.setAttribute("x2", width - margin.right);
      line.setAttribute("y1", y);
      line.setAttribute("y2", y);
      line.setAttribute("class", "credit-trend-grid");
      trendSvg.appendChild(line);
      addText(compactMoney.format(value), margin.left - 12, y + 4, "credit-trend-axis", "end");
    }

    const coordinates = points.map((item, index) => `${xAt(index)},${yAt(item.value)}`);
    if (points.length > 1) {
      const line = document.createElementNS(namespace, "polyline");
      line.setAttribute("points", coordinates.join(" "));
      line.setAttribute("class", "credit-trend-line");
      trendSvg.appendChild(line);
    }

    const labelStep = Math.max(1, Math.ceil(points.length / 8));
    points.forEach((item, index) => {
      const x = xAt(index);
      const y = yAt(item.value);
      const circle = document.createElementNS(namespace, "circle");
      circle.setAttribute("cx", x);
      circle.setAttribute("cy", y);
      circle.setAttribute("r", "5.5");
      circle.setAttribute("class", "credit-trend-point");
      const title = document.createElementNS(namespace, "title");
      title.textContent = `${item.label}: ${money.format(item.value)}`;
      circle.appendChild(title);
      trendSvg.appendChild(circle);
      if (index % labelStep === 0 || index === points.length - 1) {
        addText(item.label, x, height - 22, "credit-trend-axis");
      }
    });
  }
})();
