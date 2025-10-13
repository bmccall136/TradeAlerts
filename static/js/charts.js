// static/js/charts.js
// Provides chart rendering utilities

export function renderSparkline(canvas, data) {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    // TODO: implement sparkline rendering, e.g., with line chart
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.beginPath();
    data.forEach((point, idx) => {
        const x = (canvas.width / (data.length - 1)) * idx;
        const y = canvas.height - (canvas.height * (point - Math.min(...data)) / (Math.max(...data) - Math.min(...data)));
        if (idx === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    ctx.stroke();
}
