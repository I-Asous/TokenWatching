import "chart.js/auto";
import { Chart, type ArcElement, type Plugin } from "chart.js";
import { useState } from "react";
import { Bar, Doughnut } from "react-chartjs-2";

Chart.defaults.font.family = "Inter, Arial, sans-serif";

const doughnutLabels: Plugin<"doughnut"> = {
  id: "doughnutLeaderLabels",
  afterDatasetsDraw(chart) {
    const dataset = chart.data.datasets[0];
    const meta = chart.getDatasetMeta(0);
    if (!dataset || meta.data.length === 0) return;

    const ctx = chart.ctx;
    ctx.save();
    ctx.font = "600 10px Inter, Arial, sans-serif";
    ctx.lineWidth = 1;

    meta.data.forEach((element, index) => {
      const arc = element as ArcElement;
      const angle = (arc.startAngle + arc.endAngle) / 2;
      const side = Math.cos(angle) >= 0 ? 1 : -1;
      const startX = arc.x + Math.cos(angle) * (arc.outerRadius + 2);
      const startY = arc.y + Math.sin(angle) * (arc.outerRadius + 2);
      const elbowX = arc.x + side * (arc.outerRadius + 16);
      const labelY = arc.y + Math.sin(angle) * (arc.outerRadius + 17);
      const labelX = elbowX + side * 4;
      const value = dataset.data[index];
      const name = String(chart.data.labels?.[index] ?? "Value").toLowerCase();
      const color = index === 0 ? "#3B82F6" : "#EF4444";

      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.lineTo(elbowX, labelY);
      ctx.stroke();
      ctx.textAlign = side > 0 ? "left" : "right";
      ctx.fillText(`Tokens ${name}: ${value}`, labelX, labelY + 4, 100);
    });

    ctx.restore();
  },
};

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

const doughnutOptions = {
  responsive: true,
  maintainAspectRatio: false,
  layout: { padding: 4 },
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
              plugins={[doughnutLabels]}
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
              plugins={[doughnutLabels]}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
