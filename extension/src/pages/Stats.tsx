import "chart.js/auto";
import { Chart, type Plugin } from "chart.js";
import { useEffect, useState } from "react";
import { Bar } from "react-chartjs-2";
import { useApi } from "../api";
import type { PromptActivity } from "../types";

Chart.defaults.font.family = "Inter, Arial, sans-serif";

const pastelBarColors = ["#A7C7E7", "#B7E4C7", "#FFD6A5", "#FFC8DD", "#CDB4DB"];

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

function dateKey(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function thisMonth(): string {
  return dateKey(new Date()).slice(0, 7);
}

export default function Stats() {
  const api = useApi();
  const [records, setRecords] = useState<PromptActivity[]>([]);
  const [selectedMonth, setSelectedMonth] = useState(thisMonth);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let active = true;
    api("/prompt-w-optimized")
      .then((data: PromptActivity[]) => {
        if (active) setRecords(data);
      })
      .catch((error: unknown) => {
        if (active) setLoadError(error instanceof Error ? error.message : "Could not load stats.");
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [api]);

  const today = dateKey(new Date());
  const todayRecords = records.filter((record) => dateKey(record.org_prompt_input_time) === today);
  const monthRecords = records.filter((record) => dateKey(record.org_prompt_input_time).slice(0, 7) === selectedMonth);
  const sumSaved = (items: PromptActivity[]) => items.reduce((sum, item) => sum + (item.tokens_saved ?? 0), 0);
  const tokensSavedToday = sumSaved(todayRecords);
  const tokensSavedThisMonth = sumSaved(monthRecords);

  const [year, month] = selectedMonth.split("-").map(Number);
  const daysInMonth = new Date(year, month, 0).getDate();
  const weekCount = Math.ceil(daysInMonth / 7);
  const chartLabels = Array.from({ length: weekCount }, (_, index) => `Week ${index + 1}`);
  const chartValues = chartLabels.map((_, index) => {
    const startDay = index * 7 + 1;
    const endDay = Math.min(startDay + 6, daysInMonth);
    return sumSaved(monthRecords.filter((record) => {
      const day = new Date(record.org_prompt_input_time).getDate();
      return day >= startDay && day <= endDay;
    }));
  });

  return (
    <div className="Board1 stats-page">
      <h4 className="activity-section-title">Prompt Activity</h4>
      <div className="activity-grid">
        <section className="activity-card" aria-label="Today's submitted prompt count">
          <h5>Submitted Today</h5>
          <strong className="activity-total">{todayRecords.length}</strong>
          <span className="activity-caption">prompts</span>
        </section>
        <section className="activity-card" aria-label="Tokens saved today">
          <h5>Tokens Saved Today</h5>
          <strong className="activity-total">{tokensSavedToday}</strong>
          <span className="activity-caption">tokens</span>
        </section>
        <section className="activity-card" aria-label="Tokens saved this month">
          <h5>Tokens Saved This Month</h5>
          <strong className="activity-total">{tokensSavedThisMonth}</strong>
          <span className="activity-caption">tokens</span>
        </section>
      </div>

      <div className="stats-heading">
        <h4>Tokens Saved by Week</h4>
        <label className="stats-filter">
          Month
          <input
            type="month"
            value={selectedMonth}
            max={thisMonth()}
            onChange={(event) => {
              if (event.target.value) setSelectedMonth(event.target.value);
            }}
            aria-label="Choose stats month"
          />
        </label>
      </div>

      {isLoading && <p role="status">Loading stats…</p>}
      {loadError && <p role="alert">Could not load stats: {loadError}</p>}
      {!isLoading && !loadError && records.length === 0 && <p>No prompt data yet.</p>}

      <div className="stats-bar-chart" aria-label="Tokens saved by week chart">
        <Bar
          data={{
            labels: chartLabels,
            datasets: [{
              label: "Tokens saved",
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
              y: { beginAtZero: true, title: { display: true, text: "Tokens saved" } },
            },
          }}
          plugins={[barValueLabels]}
        />
      </div>
    </div>
  );
}
