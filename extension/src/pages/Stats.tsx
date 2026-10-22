import "chart.js/auto";
import { Chart, type ArcElement, type Plugin } from "chart.js";
import { useState } from "react";
import { Bar, Doughnut } from "react-chartjs-2";

Chart.defaults.font.family = "Inter, Arial, sans-serif";

const barValueLabels: Plugin<"bar"> = {
  id: "barValueLabels",
  afterDatasetsDraw(chart) {
    const ctx = chart.ctx;
    ctx.save();
    ctx.font = "600 10px Inter, Arial, sans-serif";
    ctx.fillStyle = "#171717";
    ctx.textAlign = "center";

    chart.data.datasets.forEach((dataset, datasetIndex) => {
      const meta = chart.getDatasetMeta(datasetIndex);
      meta.data.forEach((bar, index) => {
        const { x, y } = bar.getProps(["x", "y"], true);
        ctx.fillText(String(dataset.data[index]), x, y - 7);
      });
    });

    ctx.restore();
  },
};

const doughnutCallouts: Plugin<"doughnut"> = {
  id: "doughnutCallouts",
  afterDatasetsDraw(chart) {
    const dataset = chart.data.datasets[0];
    const meta = chart.getDatasetMeta(0);
    if (!dataset || meta.data.length === 0) return;

    const { ctx, chartArea } = chart;
    const calloutX = chartArea.right + 8;
    ctx.save();
    ctx.font = "600 9px Inter, Arial, sans-serif";
    ctx.textBaseline = "middle";
    ctx.lineWidth = 1.25;

    const callouts = meta.data.map((element, index) => {
      const arc = element as ArcElement;
      const angle = (arc.startAngle + arc.endAngle) / 2;
      return {
        arc,
        angle,
        index,
        startX: arc.x + Math.cos(angle) * (arc.outerRadius + 1),
        startY: arc.y + Math.sin(angle) * (arc.outerRadius + 1),
      };
    }).sort((a, b) => a.startY - b.startY);

    callouts.forEach(({ arc, angle, index, startX, startY }, order) => {
      const color = index === 0 ? "#3B82F6" : "#EF4444";
      const value = dataset.data[index];
      const label = String(chart.data.labels?.[index] ?? "Value");
      const targetY = chartArea.top + 24 + order * 42;
      const onRight = Math.cos(angle) >= 0;
      const outerX = onRight ? chartArea.right + 3 : chartArea.left - 3;
      const labelStartX = calloutX + 6;

      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.lineTo(outerX, startY);
      if (onRight) {
        ctx.lineTo(outerX, targetY);
      } else {
        const routeY = targetY < arc.y ? chartArea.top + 2 : chartArea.bottom - 2;
        ctx.lineTo(outerX, routeY);
        ctx.lineTo(calloutX, routeY);
        ctx.lineTo(calloutX, targetY);
      }
      ctx.lineTo(labelStartX - 3, targetY);
      ctx.stroke();

      // Keep the arrowhead at the slice so it points to the color being identified.
      const radialX = Math.cos(angle);
      const radialY = Math.sin(angle);
      const baseX = startX + radialX * 6;
      const baseY = startY + radialY * 6;
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.lineTo(baseX - radialY * 3, baseY + radialX * 3);
      ctx.lineTo(baseX + radialY * 3, baseY - radialX * 3);
      ctx.closePath();
      ctx.fill();

      ctx.textAlign = "left";
      ctx.fillText(`${label}: ${value}`, labelStartX, targetY, 64);
    });

    ctx.restore();
  },
};

const doughnutOptions = {
  responsive: true,
  maintainAspectRatio: false,
  cutout: "64%",
  layout: { padding: { left: 4, right: 70, top: 4, bottom: 4 } },
  plugins: {
    legend: { display: false },
    tooltip: { enabled: true },
  },
};

export default function Stats() {
  const [period, setPeriod] = useState<"week" | "month">("week");
  const chartLabels = period === "week"
    ? ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    : ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  // Sample values for the selected period; replace with database data later.
  const chartValues = period === "week"
    ? [20, 10, 40, 23, 43, 21, 31]
    : [20, 10, 40, 23, 43, 21, 31, 21, 16, 18, 29, 15];

  return (
    <div className="Board1 stats-page">
      <div className="stats-heading">
        <h4>Tokens Saved by {period === "week" ? "Week" : "Month"}</h4>
        <label className="stats-filter">
          View
          <select
            value={period}
            onChange={(event) => setPeriod(event.target.value as "week" | "month")}
            aria-label="Choose stats period"
          >
            <option value="week">Week</option>
            <option value="month">Month</option>
          </select>
        </label>
      </div>

      <div className="stats-bar-chart" aria-label="Tokens saved chart">
        <Bar
          data={{
            labels: chartLabels,
            datasets: [{
              label: "Tokens saved",
              data: chartValues,
              backgroundColor: "#3B82F6",
              borderRadius: 5,
            }],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              y: {
                beginAtZero: true,
                title: { display: true, text: "Tokens" },
              },
            },
          }}
          plugins={[barValueLabels]}
        />
      </div>

      <h4 className="donut-section-title">Today</h4>
      <div className="donut-grid">
        <section className="donut-card" aria-label="Today's token usage">
          <h5>Token Usage</h5>
          <div className="donut-chart">
            <Doughnut
              data={{
                labels: ["Used", "Left"],
                datasets: [{
                  label: "Tokens",
                  data: [20, 10],
                  backgroundColor: ["#3B82F6", "#EF4444"],
                  borderWidth: 0,
                }],
              }}
              options={doughnutOptions}
              plugins={[doughnutCallouts]}
            />
          </div>
        </section>

        <section className="donut-card" aria-label="Today's token savings">
          <h5>Token Savings</h5>
          <div className="donut-chart">
            <Doughnut
              data={{
                labels: ["Saved", "Left"],
                datasets: [{
                  label: "Tokens",
                  data: [30, 10],
                  backgroundColor: ["#3B82F6", "#EF4444"],
                  borderWidth: 0,
                }],
              }}
              options={doughnutOptions}
              plugins={[doughnutCallouts]}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
