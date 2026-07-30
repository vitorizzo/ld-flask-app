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

  function escapeHtml(value) {
    const node = document.createElement("span");
    node.textContent = String(value);
    return node.innerHTML;
  }
})();
