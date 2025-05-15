document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.sparkline').forEach(td => {
    const vals = JSON.parse(td.getAttribute('data-spark-values') || '[]');
    $(td).sparkline(vals, {
      type: 'line',
      width: '100px',
      height: '40px',
      lineColor: '#0f0',
      fillColor: false,
      spotColor: false,
      minSpotColor: false,
      maxSpotColor: false
    });
  });
});