// static/js/api-client.js
// Handles API calls for alerts and simulation

export async function postAlert(data) {
    const resp = await fetch('/alerts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    return resp;
}

export async function resetSimulation() {
    const resp = await fetch('/simulation/reset', {
        method: 'POST'
    });
    return resp;
}

// Additional API methods can go here
