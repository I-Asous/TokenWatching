import "chart.js/auto";
import { Chart, type Plugin } from "chart.js";
import { useState } from "react";
import { Bar } from "react-chartjs-2";

Chart.defaults.font.family = "Inter, Arial, sans-serif";

const pastelBarColors = [
  "#A7C7E7",
  "#B7E4C7",
  "#FFD6A5",
  "#FFC8DD",
  "#CDB4DB",
  "#BDE0FE",
  "#D8E2DC",
  "#FBC4AB",
  "#CDEAC0",
  "#E4C1F9",
  "#FAEDCB",
  "#C9E4DE",
];

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

export default function Stats() {
  const [period, setPeriod] = useState<"week" | "month">("week");
  const chartLabels = period === "week"
    ? ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    : ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  // Mock prompt counts until this page reads prompt rows from the database.
  const chartValues = period === "week"
    ? [2, 1, 4, 3, 5, 2, 3]
    : [8, 10, 12, 9, 14, 16, 13, 18, 17, 20, 15, 19];

  // Mock values until Stats reads the prompt and optimization data.
  const todayPromptCount = 3;
  const tokensSavedToday = 120; // Mock value until optimization data is available.

  return (
    <div className="Board1 stats-page">
      <h4 className="activity-section-title">Prompt Activity</h4>
      <div className="activity-grid">
        <section className="activity-card" aria-label="Today's submitted prompt count">
          <h5>Submitted Today</h5>
          <strong className="activity-total">{todayPromptCount}</strong>
          <span className="activity-caption">prompts</span>
        </section>

        <section className="activity-card" aria-label="Tokens saved today">
          <h5>Tokens Saved Today</h5>
          <strong className="activity-total">{tokensSavedToday}</strong>
          <span className="activity-caption">tokens</span>
        </section>
      </div>

      <div className="stats-heading">
        <h4>Prompts Submitted by {period === "week" ? "Week" : "Month"}</h4>
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

      <div className="stats-bar-chart" aria-label="Prompt submissions chart">
        <Bar
          data={{
            labels: chartLabels,
            datasets: [{
              label: "Prompts submitted",
              data: chartValues,
              backgroundColor: chartLabels.map((_, index) => pastelBarColors[index % pastelBarColors.length]),
              borderRadius: 5,
            }],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 18 } },
            plugins: { legend: { display: false } },
            scales: {
              y: {
                beginAtZero: true,
                title: { display: true, text: "Prompts" },
              },
            },
          }}
          plugins={[barValueLabels]}
        />
      </div>

    </div>
  );
}
