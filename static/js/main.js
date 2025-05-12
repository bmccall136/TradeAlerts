// static/js/main.js
import { postAlert, resetSimulation } from './api-client.js';
import { initUIControls } from './ui-controls.js';
import { renderSparkline } from './charts.js';

document.addEventListener('DOMContentLoaded', () => {
    initUIControls({ resetSimulation });

    // TODO: fetch initial data, bind Buy/Sell, render sparklines
});
