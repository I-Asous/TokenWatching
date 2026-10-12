import "chart.js/auto";
import { useState } from "react";
import { Bar, Doughnut } from "react-chartjs-2";

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
    <div className="Board1">
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
      <div>
        <Bar
        data={{
          labels: chartLabels,
          datasets:[
            {
              label:"Tokens Saved",
              data: chartValues,

            }
          ],
        }}
        />
        <h4>Tokens Today</h4>
        <div className="boardContainer">
          <div className="board2">
        <Doughnut 
         data={{
          labels:["Tokens Used", "Tokens Left"],
          datasets:[
            {
              // data can later be implemented from database this is just a test sample
              label:"Tokens saved",
              data:[20,10],

            }
          ],
        }}
        
        />
        </div>
         <div className="board2">
                <Doughnut
         data={{
          labels:["Tokens Saved","Tokens Left"],
          datasets:[
            {
              // data can later be implemented from database this is just a test sample
              label:"Tokens",
              data:[30,10],

            }
          ],
        }}
        
        />
        </div>
        </div>

  </div>
    </div>
  );
}
