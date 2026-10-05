import { Chart as ChartJS } from "chart.js/auto";
import {Bar, Doughnut, Line} from "react-chartjs-2";

export default function Stats() {
  return (
    <div className="Board1">
      <h4>My Summary</h4>
      <div>
        <Bar
        data={{
          labels:["Jan", "Feb", "Mar","Apr","May", "Jun","Jul", "Aug", "Sep","Oct", "Nov", "Dec"],
          datasets:[
            {
              // data can later be implemented from database this is just a test sample
              label:"Tokens Saved",
              data:[20,10,40,23 ,43,21,31,21,16,18,29,15,43],

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