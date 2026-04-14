import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

const SalesChart = ({ data }) => {
  if (!data || Object.keys(data).length === 0)
    return <p>No sales data</p>;

  const chartData = {
    labels: Object.keys(data),
    datasets: [
      {
        label: "Sales (Last 7 Days)",
        data: Object.values(data),
        borderColor: '#0d6efd',
        backgroundColor: 'rgba(13, 110, 253, 0.2)',
        borderWidth: 2,
        tension: 0.3
      }
    ]
  };

  const options = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
          legend: { display: false }
      },
      scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } }
      }
  };

  return <div style={{ height: '150px', marginTop: '1rem' }}><Line data={chartData} options={options} /></div>;
};

export default SalesChart;
