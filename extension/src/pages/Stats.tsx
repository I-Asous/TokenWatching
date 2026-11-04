import "chart.js/auto";
import { Chart, type Plugin } from "chart.js";
import { useEffect, useState } from "react";
import { Bar } from "react-chartjs-2";
import { useApi } from "../api";
import type { PromptActivity } from "../types";

type StatsRange = "today" | "week" | "month";

Chart.defaults.font.family = "Inter, Arial, sans-serif";

const beforeBarColor = "#A7C7E7";
const afterBarColor = "#B7E4C7";

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
      ctx.fillStyle = datasetIndex === 1 ? "#2E7D32" : "#171717";
      meta.data.forEach((bar, index) => {
        const { x, y } = bar.getProps(["x", "y"], true);
        ctx.fillText(Number(dataset.data[index]).toLocaleString(undefined, { maximumFractionDigits: 0 }), x, y - 7);
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
  const [selectedRange, setSelectedRange] = useState<StatsRange>("week");
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
  const weekStart = new Date();
  weekStart.setHours(0, 0, 0, 0);
  weekStart.setDate(weekStart.getDate() - weekStart.getDay());
  const weekStartKey = dateKey(weekStart);
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekEnd.getDate() + 7);
  const weekEndKey = dateKey(weekEnd);
  const weekRecords = records.filter((record) => {
    const key = dateKey(record.org_prompt_input_time);
    return key >= weekStartKey && key < weekEndKey;
  });
  const periodRecords = selectedRange === "today"
    ? todayRecords
    : selectedRange === "week"
      ? weekRecords
      : monthRecords;
  const periodName = selectedRange === "today"
    ? "Today"
    : selectedRange === "week"
      ? "This Week"
      : new Date(Number(selectedMonth.slice(0, 4)), Number(selectedMonth.slice(5, 7)) - 1, 1)
          .toLocaleString(undefined, { month: "long", year: "numeric" });
  const chartHeading = selectedRange === "today"
    ? "Amount Saved Today"
    : selectedRange === "week"
      ? "Amount Saved This Week"
      : `Amount Saved in ${periodName}`;
  const periodTokensSaved = sumSaved(periodRecords);
  const periodOriginalTokens = periodRecords.reduce((sum, item) => sum + (item.org_prompt_tokens ?? 0), 0);
  const periodReductionPercent = periodOriginalTokens > 0 ? (periodTokensSaved / periodOriginalTokens) * 100 : 0;
  const totalTokensSaved = sumSaved(records);
  const totalOriginalTokens = records.reduce((sum, item) => sum + (item.org_prompt_tokens ?? 0), 0);
  const overallReductionPercent = totalOriginalTokens > 0
    ? (totalTokensSaved / totalOriginalTokens) * 100
    : 0;
  const promptsWithTokensSaved = periodRecords.filter((record) => (record.tokens_saved ?? 0) > 0).length;
  const promptsWithoutTokensSaved = periodRecords.length - promptsWithTokensSaved;

  const [year, month] = selectedMonth.split("-").map(Number);
  const daysInMonth = new Date(year, month, 0).getDate();
  const weekCount = Math.ceil(daysInMonth / 7);
  const monthChartLabels = Array.from({ length: weekCount }, (_, index) => {
    const startDay = index * 7 + 1;
    const endDay = Math.min(startDay + 6, daysInMonth);
    const monthName = new Date(year, month - 1, 1).toLocaleString(undefined, { month: "short" });
    return `${monthName} ${startDay}–${endDay}`;
  });
  const chartLabels = selectedRange === "today"
    ? ["Today"]
    : selectedRange === "week"
      ? Array.from({ length: 7 }, (_, index) => {
          const day = new Date(weekStart);
          day.setDate(day.getDate() + index);
          return day.toLocaleDateString(undefined, { weekday: "short", day: "numeric" });
        })
      : monthChartLabels;
  const chartWeeks = selectedRange === "today"
    ? [todayRecords]
    : selectedRange === "week"
      ? Array.from({ length: 7 }, (_, index) => {
          const day = new Date(weekStart);
          day.setDate(day.getDate() + index);
          const key = dateKey(day);
          return weekRecords.filter((record) => dateKey(record.org_prompt_input_time) === key);
        })
      : monthChartLabels.map((_, index) => {
          const startDay = index * 7 + 1;
          const endDay = Math.min(startDay + 6, daysInMonth);
          return monthRecords.filter((record) => {
            const day = new Date(record.org_prompt_input_time).getDate();
            return day >= startDay && day <= endDay;
          });
        });
  const originalTokenValues = chartWeeks.map((week) =>
    week.reduce((sum, record) => sum + (record.org_prompt_tokens ?? 0), 0),
  );
  const afterTokenValues = chartWeeks.map((week) =>
    week.reduce((sum, record) => sum + (record.optimized_prompt_tokens ?? record.org_prompt_tokens ?? 0), 0),
  );

  return (
    <div className="Board1 stats-page">
      <h4 className="activity-section-title">Prompt Activity</h4>
      <div className="stats-range-tabs" role="group" aria-label="Choose stats time period">
        {(["today", "week", "month"] as const).map((range) => (
          <button
            key={range}
            type="button"
            aria-pressed={selectedRange === range}
            className={selectedRange === range ? "stats-range-tab active" : "stats-range-tab"}
            onClick={() => setSelectedRange(range)}
          >
            {range === "today" ? "Today" : range === "week" ? "Week" : "Month"}
          </button>
        ))}
      </div>
      <div className="activity-grid">
        <section className="activity-card" aria-label={`${periodName} prompt count`}>
          <h5>{`${periodName} Prompts`}</h5>
          <strong className="activity-total">{periodRecords.length}</strong>
          <span className="activity-caption">prompts</span>
        </section>
        <section className="activity-card activity-card-saved" aria-label={`Tokens saved ${periodName.toLowerCase()}`}>
          <h5>Tokens Saved</h5>
          <strong className="activity-total">{periodTokensSaved}</strong>
          <span className="activity-caption">tokens</span>
        </section>
        <section className="activity-card" aria-label={`Token reduction ${periodName.toLowerCase()}`}>
          <h5>Reduction</h5>
          <strong className="activity-total">{periodReductionPercent.toFixed(1)}%</strong>
          <span className="activity-caption">of original tokens</span>
        </section>
        <section className="activity-card activity-card-overall" aria-label="All-time token reduction across all prompts">
          <h5>All-Time Reduction</h5>
          <strong className="activity-total">{overallReductionPercent.toFixed(1)}%</strong>
          <span className="activity-caption">
            {totalTokensSaved.toLocaleString()} of {totalOriginalTokens.toLocaleString()} original tokens saved
          </span>
        </section>
      </div>

      <div className="stats-outcome-grid" aria-label="Prompt token savings counts">
        <section className="stats-outcome-card stats-outcome-card-saved" aria-label="Prompts that saved tokens">
          <h5>Optimized</h5>
          <strong>{promptsWithTokensSaved}</strong>
        </section>
        <section className="stats-outcome-card" aria-label="Prompts that did not save tokens">
          <h5>Original Kept</h5>
          <strong>{promptsWithoutTokensSaved}</strong>
        </section>
      </div>

      {selectedRange !== "today" && (
        <div className="stats-heading">
          <h4>{chartHeading}</h4>
          {selectedRange === "month" && (
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
          )}
        </div>
      )}

      {isLoading && <p role="status">Loading stats…</p>}
      {loadError && <p role="alert">Could not load stats: {loadError}</p>}
      {!isLoading && !loadError && records.length === 0 && <p>No prompt data yet.</p>}

      {selectedRange !== "today" && (
        <div className="stats-bar-chart" aria-label={`Original and optimized tokens for ${periodName.toLowerCase()}`}>
          <Bar
            data={{
              labels: chartLabels,
              datasets: [
                {
                  label: "Original tokens",
                  data: originalTokenValues,
                  backgroundColor: beforeBarColor,
                  borderRadius: 5,
                },
                {
                  label: "After optimization",
                  data: afterTokenValues,
                  backgroundColor: afterBarColor,
                  borderRadius: 5,
                },
              ],
            }}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              layout: { padding: { top: 18 } },
              plugins: { legend: { display: true, position: "top" } },
              scales: {
                y: {
                  beginAtZero: true,
                  ticks: {
                    precision: 0,
                    callback: (value) => Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 }),
                  },
                  title: { display: true, text: "Tokens" },
                },
              },
            }}
            plugins={[barValueLabels]}
          />
        </div>
      )}
    </div>
  );
}
