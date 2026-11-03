/**
 * CWMS Dashboard Application
 * Frontend for Cloud Workload Management System
 */

class CWMSDashboard {
    constructor() {
        this.apiBase = '/api';
        this.charts = {};
        this.currentSimulationId = null;
        this.pollInterval = null;
        this.lastStatusCounts = null;
        this.apiToken = sessionStorage.getItem('cwms_api_token') || '';
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.initTabs();
        const tokenInput = document.getElementById('api-token');
        if (tokenInput) tokenInput.value = this.apiToken;
        this.loadInitialData();
    }

    authHeaders(headers = {}) {
        const result = { ...headers };
        if (this.apiToken) result.Authorization = `Bearer ${this.apiToken}`;
        return result;
    }

    updateToken(value) {
        this.apiToken = value.trim();
        if (this.apiToken) {
            sessionStorage.setItem('cwms_api_token', this.apiToken);
        } else {
            sessionStorage.removeItem('cwms_api_token');
        }
    }
    
    bindEvents() {
        // Tab navigation
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
        });
        
        // Scenario buttons
        document.querySelectorAll('.run-scenario').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const scenario = e.target.closest('.scenario-card').dataset.scenario;
                this.runScenario(scenario);
            });
        });
        
        // Custom simulation form
        const form = document.getElementById('custom-simulation-form');
        if (form) {
            form.addEventListener('submit', (e) => this.runCustomSimulation(e));
        }
        
        // Export buttons
        document.getElementById('export-csv')?.addEventListener('click', () => this.exportCSV());
        document.getElementById('export-json')?.addEventListener('click', () => this.exportJSON());

        // Optional bearer token for protected control endpoints
        document.getElementById('api-token')?.addEventListener('input', (e) => {
            this.updateToken(e.target.value);
        });
        
        // Node health toggle (delegated)
        document.getElementById('nodes-table')?.addEventListener('click', (e) => {
            if (e.target.classList.contains('toggle-health')) {
                const nodeName = e.target.dataset.node;
                const healthy = e.target.dataset.healthy === 'true';
                this.toggleNodeHealth(nodeName, !healthy);
            }
        });
    }
    
    initTabs() {
        // Show first tab by default
        const firstTab = document.querySelector('.tab-btn');
        if (firstTab) {
            this.switchTab(firstTab.dataset.tab);
        }
    }
    
    switchTab(tabName) {
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        
        // Update tab panels
        document.querySelectorAll('.tab-panel').forEach(panel => {
            panel.classList.toggle('active', panel.id === tabName);
        });
        
        // Load tab-specific data
        if (tabName === 'metrics') this.loadMetricsCharts();
        if (tabName === 'forecast') this.loadForecastCharts();
        if (tabName === 'nodes') this.loadNodes();
        
        // Resize only charts in the visible tab. Resizing hidden charts can
        // produce unstable dimensions and unnecessary layout work.
        requestAnimationFrame(() => {
            const activePanel = document.getElementById(tabName);
            if (!activePanel) return;
            Object.values(this.charts).forEach(chart => {
                const canvas = chart && chart.canvas;
                if (canvas && activePanel.contains(canvas)) chart.resize();
            });
        });
    }
    
    async loadInitialData() {
        try {
            await this.loadConfig();
            await this.loadNodes();
        } catch (error) {
            console.error('Failed to load initial data:', error);
        }
    }
    
    async loadConfig() {
        try {
            const response = await fetch(`${this.apiBase}/config`);
            const config = await response.json();
            
            // Update form defaults
            document.getElementById('custom-policy').value = config.policy;
            document.getElementById('custom-intervals').value = config.intervals;
            document.getElementById('custom-base-rate').value = config.base_rate;
            document.getElementById('custom-burst-rate').value = config.burst_rate;
            document.getElementById('custom-burst-start').value = config.burst_start;
            document.getElementById('custom-burst-end').value = config.burst_end;
            document.getElementById('custom-surge-threshold').value = config.surge_threshold;
            document.getElementById('custom-load-threshold').value = config.load_threshold;
            document.getElementById('custom-max-load-threshold').value = config.max_load_threshold;
            document.getElementById('custom-fail-node').value = config.fail_node || '';
            document.getElementById('custom-forecast-strategy').value = config.forecast_strategy;
            document.getElementById('custom-admission-control').value = String(config.admission_control);
            document.getElementById('custom-overload-threshold').value = config.overload_threshold;
            document.getElementById('custom-queue-limit').value = config.queue_limit;
            document.getElementById('custom-timeout-ms').value = config.request_timeout_ms;
            document.getElementById('custom-seed').value = config.seed;
        } catch (error) {
            console.error('Failed to load config:', error);
        }
    }
    
    async loadNodes() {
        try {
            const response = await fetch(`${this.apiBase}/nodes`);
            const data = await response.json();
            this.renderNodesTable(data.nodes);
        } catch (error) {
            console.error('Failed to load nodes:', error);
        }
    }
    
    renderNodesTable(nodes) {
        const tbody = document.querySelector('#nodes-table tbody');
        if (!tbody) return;
        
        tbody.innerHTML = nodes.map(node => `
            <tr>
                <td>${node.name}</td>
                <td>
                    <span class="status-badge ${node.healthy ? 'healthy' : 'unhealthy'}">
                        ${node.state}
                    </span>
                </td>
                <td>${node.capacity}</td>
                <td>
                    <div class="progress-bar" style="width: 100px;">
                        <div class="progress-fill" style="width: ${Math.min(node.load, 100)}%"></div>
                    </div>
                    ${node.load.toFixed(1)}%
                </td>
                <td>${node.assigned}</td>
                <td>${node.queued_total ?? 0} / ${node.queue_overflow_total ?? 0}</td>
                <td>${node.available_capacity.toFixed(1)}</td>
                <td>
                    <button class="btn btn-sm toggle-health" 
                            data-node="${node.name}" 
                            data-healthy="${node.healthy}">
                        ${node.healthy ? 'Mark Unhealthy' : 'Mark Healthy'}
                    </button>
                </td>
            </tr>
        `).join('');
    }
    
    async runScenario(scenario) {
        const policy = document.getElementById('node-policy-select')?.value || 'least-loaded';
        this.showLoading(true);
        
        try {
            const response = await fetch(`${this.apiBase}/scenarios/run`, {
                method: 'POST',
                headers: this.authHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ scenario, policy })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start scenario');
            }
            
            this.startPolling();
        } catch (error) {
            this.showError('Failed to run scenario: ' + error.message);
            this.showLoading(false);
        }
    }
    
    async runCustomSimulation(event) {
        event.preventDefault();
        
        const config = {
            policy: document.getElementById('custom-policy').value,
            intervals: parseInt(document.getElementById('custom-intervals').value),
            base_rate: parseInt(document.getElementById('custom-base-rate').value),
            burst_rate: parseInt(document.getElementById('custom-burst-rate').value),
            burst_start: parseInt(document.getElementById('custom-burst-start').value),
            burst_end: parseInt(document.getElementById('custom-burst-end').value),
            surge_threshold: parseInt(document.getElementById('custom-surge-threshold').value),
            load_threshold: parseFloat(document.getElementById('custom-load-threshold').value),
            max_load_threshold: parseFloat(document.getElementById('custom-max-load-threshold').value),
            fail_node: document.getElementById('custom-fail-node').value || null,
            forecast_window: 5,
            forecast_strategy: document.getElementById('custom-forecast-strategy').value,
            admission_control: document.getElementById('custom-admission-control').value === 'true',
            overload_threshold: parseFloat(document.getElementById('custom-overload-threshold').value),
            queue_limit: parseInt(document.getElementById('custom-queue-limit').value),
            request_timeout_ms: parseFloat(document.getElementById('custom-timeout-ms').value),
            seed: parseInt(document.getElementById('custom-seed').value),
        };
        
        // Validate: equal start/end means no burst window
        if (config.burst_start > config.burst_end) {
            this.showError('Burst start cannot be after burst end');
            return;
        }
        
        this.showLoading(true);
        
        try {
            const response = await fetch(`${this.apiBase}/simulation/start`, {
                method: 'POST',
                headers: this.authHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify(config)
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start simulation');
            }
            
            this.startPolling();
        } catch (error) {
            this.showError('Failed to start simulation: ' + error.message);
            this.showLoading(false);
        }
    }
    
    startPolling() {
        this.stopPolling();
        this.lastStatusCounts = null;
        if (this.charts.requestRate) {
            this.charts.requestRate.data.labels = [];
            this.charts.requestRate.data.datasets.forEach(ds => { ds.data = []; });
        }
        if (this.charts.nodeLoad) {
            this.charts.nodeLoad.data.labels = [];
            this.charts.nodeLoad.data.datasets.forEach(ds => { ds.data = []; });
        }
        this.pollInterval = setInterval(() => this.pollStatus(), 1000);
        this.pollStatus(); // Immediate first poll
    }
    
    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }
    
    async pollStatus() {
        try {
            const response = await fetch(`${this.apiBase}/simulation/status`);
            if (!response.ok) {
                throw new Error(`Status request failed (${response.status})`);
            }
            const status = await response.json();
            
            this.updateStatusDisplay(status);
            
            if (!status.running) {
                this.stopPolling();
                this.showLoading(false);
                if (status.error) {
                    this.showError(status.error);
                    return;
                }
                await this.loadResults();
                this.enableExports();
            }
        } catch (error) {
            console.error('Poll error:', error);
            this.showError('Failed to read simulation status: ' + error.message);
            this.stopPolling();
            this.showLoading(false);
        }
    }
    
    updateStatusDisplay(status) {
        // Update overview metrics
        document.getElementById('total-generated').textContent = status.requests_generated.toLocaleString();
        document.getElementById('total-assigned').textContent = status.requests_assigned.toLocaleString();
        document.getElementById('total-rejected').textContent = status.requests_rejected.toLocaleString();
        
        // Update status panel
        document.getElementById('sim-status').textContent = status.running ? 'Running' : 'Completed';
        document.getElementById('sim-status').className = 'status-value ' + (status.running ? 'text-primary' : 'text-success');
        document.getElementById('current-policy').textContent = status.policy || '-';
        
        const progress = status.total_intervals > 0 
            ? (status.interval / status.total_intervals) * 100 
            : 0;
        document.getElementById('progress-bar').style.width = `${progress}%`;
        document.getElementById('progress-text').textContent = `${status.interval} / ${status.total_intervals} intervals`;
        
        document.getElementById('current-forecast').textContent = status.forecast.toFixed(1) + ' req/interval';
        document.getElementById('current-recommendation').textContent = status.recommendation;
        
        // Update surge count
        document.getElementById('surge-count').textContent = status.surge_detected ? '1+' : '0';
        
        // Update nodes table if on nodes tab
        if (document.getElementById('nodes').classList.contains('active')) {
            this.renderNodesTable(status.nodes);
        }
        
        // Update charts if we have interval data
        if (status.running && this.charts.requestRate) {
            this.updateLiveCharts(status);
        }
    }
    
    updateLiveCharts(status) {
        // Status exposes cumulative counters; convert them to per-interval deltas
        // so the live request-rate chart matches the completed-run chart.
        const previous = this.lastStatusCounts || {
            requests_generated: 0,
            requests_assigned: 0,
            requests_rejected: 0,
        };
        const generated = Math.max(0, status.requests_generated - previous.requests_generated);
        const assigned = Math.max(0, status.requests_assigned - previous.requests_assigned);
        const rejected = Math.max(0, status.requests_rejected - previous.requests_rejected);
        const hasNewCounts = generated + assigned + rejected > 0;
        this.lastStatusCounts = {
            requests_generated: status.requests_generated,
            requests_assigned: status.requests_assigned,
            requests_rejected: status.requests_rejected,
        };
        
        // Request Rate Chart
        const rateChart = this.charts.requestRate;
        if (rateChart && hasNewCounts) {
            rateChart.data.labels.push(status.interval);
            rateChart.data.datasets[0].data.push(generated);
            rateChart.data.datasets[1].data.push(assigned);
            rateChart.data.datasets[2].data.push(rejected);
            
            // Keep last 50 points
            if (rateChart.data.labels.length > 50) {
                rateChart.data.labels.shift();
                rateChart.data.datasets.forEach(ds => ds.data.shift());
            }
            rateChart.update('none');
        }
        
        // Node Load Chart
        const loadChart = this.charts.nodeLoad;
        if (loadChart && status.nodes.length > 0 && hasNewCounts) {
            loadChart.data.labels.push(status.interval);
            status.nodes.forEach((node, i) => {
                if (loadChart.data.datasets[i]) {
                    loadChart.data.datasets[i].data.push(node.load);
                    if (loadChart.data.datasets[i].data.length > 50) {
                        loadChart.data.datasets[i].data.shift();
                    }
                }
            });
            loadChart.update('none');
        }
    }
    
    async loadResults() {
        try {
            const [resultsResponse, summaryResponse] = await Promise.all([
                fetch(`${this.apiBase}/simulation/results`),
                fetch(`${this.apiBase}/simulation/summary`)
            ]);
            if (!resultsResponse.ok || !summaryResponse.ok) {
                throw new Error('Results are not available');
            }
            const results = await resultsResponse.json();
            const summary = await summaryResponse.json();
            
            this.renderResults(results);
            this.renderSummary(summary);
            this.renderForecastTable(results);
            this.updateCharts(results, summary);
        } catch (error) {
            console.error('Failed to load results:', error);
            this.showError('Failed to load simulation results: ' + error.message);
        }
    }
    
    renderResults(results) {
        // Update overview cards with final values
        if (results.intervals && results.intervals.length > 0) {
            document.getElementById('surge-count').textContent = 
                results.intervals.filter(i => i.surge_detected).length;
        }
    }
    
    renderSummary(summary) {
        const container = document.getElementById('metrics-summary');
        if (!container) return;
        
        const sys = summary.system_metrics;
        container.innerHTML = `
            <div class="metric-stat">
                <div class="stat-value" id="summary-generated">${sys.total_requests_generated.toLocaleString()}</div>
                <div class="stat-label">Total Generated</div>
            </div>
            <div class="metric-stat">
                <div class="stat-value" id="summary-accepted">${(sys.total_requests_accepted ?? sys.total_requests_assigned).toLocaleString()}</div>
                <div class="stat-label">Total Accepted</div>
            </div>
            <div class="metric-stat">
                <div class="stat-value" id="summary-completed">${sys.total_requests_completed.toLocaleString()}</div>
                <div class="stat-label">Completed</div>
            </div>
            <div class="metric-stat">
                <div class="stat-value" id="summary-failed">${sys.total_requests_failed.toLocaleString()}</div>
                <div class="stat-label">Failed / Timed Out</div>
            </div>
            <div class="metric-stat">
                <div class="stat-value" id="summary-queued">${(sys.total_requests_queued ?? 0).toLocaleString()}</div>
                <div class="stat-label">Queued</div>
            </div>
            <div class="metric-stat">
                <div class="stat-value" id="summary-rejected">${sys.total_requests_rejected.toLocaleString()}</div>
                <div class="stat-label">Total Rejected</div>
            </div>
            <div class="metric-stat">
                <div class="stat-value" id="summary-overload">${sys.total_requests_rejected_overload.toLocaleString()}</div>
                <div class="stat-label">Rejected: Overload</div>
            </div>
            <div class="metric-stat">
                <div class="stat-value" id="summary-no-capacity">${sys.total_requests_rejected_no_capacity.toLocaleString()}</div>
                <div class="stat-label">Rejected: No Capacity</div>
            </div>
            <div class="metric-stat">
                <div class="stat-value" id="summary-acceptance">${sys.assignment_rate.toFixed(1)}%</div>
                <div class="stat-label">Acceptance Rate</div>
            </div>
            <div class="metric-stat">
                <div class="stat-value" id="summary-completion">${sys.completion_rate.toFixed(1)}%</div>
                <div class="stat-label">Completion Rate</div>
            </div>
            <div class="metric-stat">
                <div class="stat-value">${sys.surge_events}</div>
                <div class="stat-label">Surge Events</div>
            </div>
        `;
        
        // Per-node metrics
        if (summary.node_metrics) {
            const nodeHtml = summary.node_metrics.map(node => `
                <div class="metric-stat">
                    <div class="stat-value">${node.requests_assigned}</div>
                    <div class="stat-label">${node.name} Assigned</div>
                </div>
            `).join('');
            container.innerHTML += `<div style="grid-column: 1/-1; border-top: 1px solid var(--border); padding-top: 1rem; margin-top: 1rem;">${nodeHtml}</div>`;
        }
    }
    
    renderForecastTable(results) {
        const tbody = document.querySelector('#forecast-table tbody');
        if (!tbody || !results.intervals) return;
        
        tbody.innerHTML = results.intervals.map(interval => `
            <tr>
                <td>${interval.interval}</td>
                <td>${interval.forecast.predicted.toFixed(1)}</td>
                <td>${interval.forecast.actual !== undefined ? interval.forecast.actual : '-'}</td>
                <td>${interval.forecast.error !== undefined ? interval.forecast.error.toFixed(1) : '-'}</td>
                <td>${interval.forecast.absolute_error !== undefined ? interval.forecast.absolute_error.toFixed(1) : '-'}</td>
                <td>${interval.forecast.method}</td>
            </tr>
        `).join('');
        
        // Accuracy metrics
        const accuracyContainer = document.getElementById('accuracy-metrics');
        if (accuracyContainer && results.intervals) {
            const forecasts = results.intervals.map(i => i.forecast).filter(f => f.actual !== undefined);
            if (forecasts.length > 0) {
                const mae = forecasts.reduce((sum, f) => sum + (f.absolute_error || 0), 0) / forecasts.length;
                const rmse = Math.sqrt(forecasts.reduce((sum, f) => sum + (f.squared_error || 0), 0) / forecasts.length);
                
                accuracyContainer.innerHTML = `
                    <div class="accuracy-item">
                        <div class="accuracy-value">${mae.toFixed(2)}</div>
                        <div class="accuracy-label">MAE</div>
                    </div>
                    <div class="accuracy-item">
                        <div class="accuracy-value">${rmse.toFixed(2)}</div>
                        <div class="accuracy-label">RMSE</div>
                    </div>
                    <div class="accuracy-item">
                        <div class="accuracy-value">${forecasts.length}</div>
                        <div class="accuracy-label">Samples</div>
                    </div>
                `;
            }
        }
    }
    
    updateCharts(results, summary) {
        if (!results.intervals) return;
        
        const intervals = results.intervals;
        const labels = intervals.map(i => i.interval);
        
        // Request Rate Chart
        this.createOrUpdateChart('requestRateChart', 'line', {
            labels,
            datasets: [
                {
                    label: 'Generated',
                    data: intervals.map(i => i.requests_generated),
                    borderColor: '#6c757d',
                    backgroundColor: 'rgba(108, 117, 125, 0.1)',
                    tension: 0.3,
                    fill: true,
                },
                {
                    label: 'Accepted',
                    data: intervals.map(i => i.requests_assigned),
                    borderColor: '#28a745',
                    backgroundColor: 'rgba(40, 167, 69, 0.1)',
                    tension: 0.3,
                    fill: true,
                },
                {
                    label: 'Queued',
                    data: intervals.map(i => i.requests_queued ?? 0),
                    borderColor: '#ffc107',
                    backgroundColor: 'rgba(255, 193, 7, 0.1)',
                    tension: 0.3,
                    fill: true,
                },
                {
                    label: 'Rejected',
                    data: intervals.map(i => i.requests_rejected),
                    borderColor: '#dc3545',
                    backgroundColor: 'rgba(220, 53, 69, 0.1)',
                    tension: 0.3,
                    fill: true,
                },
            ],
        }, {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top' } },
            scales: { y: { beginAtZero: true, title: { display: true, text: 'Requests' } } },
        });
        
        // Node Load Chart
        const nodes = intervals[intervals.length - 1]?.nodes || [];
        const nodeDatasets = nodes.map((node, idx) => ({
            label: node.name,
            data: intervals.map(i => i.nodes[idx]?.load || 0),
            borderColor: this.getNodeColor(idx),
            backgroundColor: this.getNodeColor(idx, 0.1),
            tension: 0.3,
            fill: true,
        }));
        
        this.createOrUpdateChart('nodeLoadChart', 'line', {
            labels,
            datasets: nodeDatasets,
        }, {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top' } },
            scales: { y: { beginAtZero: true, max: 150, title: { display: true, text: 'Load %' } } },
        });
        
        // Assignment Chart
        this.createOrUpdateChart('assignmentChart', 'doughnut', {
            labels: ['Completed', 'Failed', 'Rejected'],
            datasets: [{
                data: [
                    summary.system_metrics?.total_requests_completed || 0,
                    summary.system_metrics?.total_requests_failed || 0,
                    summary.system_metrics?.total_requests_rejected || 0,
                ],
                backgroundColor: ['#28a745', '#ffc107', '#dc3545'],
                borderWidth: 0,
            }],
        }, {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
        });
        
        // Throughput Chart
        this.createOrUpdateChart('throughputChart', 'bar', {
            labels,
            datasets: [{
                label: 'Requests/Interval',
                data: intervals.map(i => i.requests_assigned),
                backgroundColor: intervals.map(i => i.surge_detected ? '#ffc107' : '#0066cc'),
            }],
        }, {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, title: { display: true, text: 'Accepted Requests' } } },
        });
        
        // Node Assignment Chart
        const nodeNames = nodes.map(n => n.name);
        const nodeAssignmentData = nodes.map(n => n.assigned_total || 0);
        
        this.createOrUpdateChart('nodeAssignmentChart', 'pie', {
            labels: nodeNames,
            datasets: [{
                data: nodeAssignmentData,
                backgroundColor: nodeNames.map((_, idx) => this.getNodeColor(idx)),
                borderWidth: 0,
            }],
        }, {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
        });
        
        // Surge Chart
        this.createOrUpdateChart('surgeChart', 'scatter', {
            datasets: [{
                label: 'Surge Events',
                data: intervals
                    .filter(i => i.surge_detected)
                    .map(i => ({ x: i.interval, y: i.requests_generated })),
                backgroundColor: '#dc3545',
                pointStyle: 'triangle',
                pointRadius: 8,
            }],
        }, {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top' } },
            scales: { 
                x: { title: { display: true, text: 'Interval' } },
                y: { beginAtZero: true, title: { display: true, text: 'Requests' } },
            },
        });
        
        // Forecast Chart
        this.createOrUpdateChart('forecastChart', 'line', {
            labels,
            datasets: [
                {
                    label: 'Actual',
                    data: intervals.map(i => i.forecast.actual ?? null),
                    borderColor: '#28a745',
                    backgroundColor: 'rgba(40, 167, 69, 0.1)',
                    tension: 0.3,
                    fill: false,
                },
                {
                    label: 'Forecast',
                    data: intervals.map(i => i.forecast.predicted),
                    borderColor: '#0066cc',
                    backgroundColor: 'rgba(0, 102, 204, 0.1)',
                    borderDash: [5, 5],
                    tension: 0.3,
                    fill: false,
                },
            ],
        }, {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top' } },
            scales: { y: { beginAtZero: true, title: { display: true, text: 'Requests/Interval' } } },
        });
        
        // Accuracy Chart
        const forecasts = intervals.map(i => i.forecast).filter(f => f.actual !== undefined);
        if (forecasts.length > 0) {
            this.createOrUpdateChart('accuracyChart', 'bar', {
                labels: forecasts.map((_, i) => `Sample ${i + 1}`),
                datasets: [
                    {
                        label: 'Absolute Error',
                        data: forecasts.map(f => f.absolute_error),
                        backgroundColor: '#ffc107',
                    },
                    {
                        label: 'Error',
                        data: forecasts.map(f => f.error),
                        backgroundColor: forecasts.map(f => f.error >= 0 ? '#28a745' : '#dc3545'),
                    },
                ],
            }, {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top' } },
                scales: { y: { title: { display: true, text: 'Error' } } },
            });
        }
    }
    
    createOrUpdateChart(canvasId, type, data, options) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;
        if (typeof Chart === 'undefined') {
            // Chart.js is loaded from a CDN; keep the numeric UI usable offline.
            if (!this.chartWarningShown) {
                this.chartWarningShown = true;
                this.showError('Chart library unavailable (offline). Tables and metrics still work.');
            }
            return;
        }
        
        if (this.charts[canvasId]) {
            this.charts[canvasId].data = data;
            this.charts[canvasId].options = options;
            this.charts[canvasId].update();
        } else {
            this.charts[canvasId] = new Chart(ctx, { type, data, options });
        }
    }
    
    loadMetricsCharts() {
        // Charts will be populated when results load
    }
    
    loadForecastCharts() {
        // Charts will be populated when results load
    }
    
    getNodeColor(index, alpha = 1) {
        const colors = [
            `rgba(0, 102, 204, ${alpha})`,
            `rgba(40, 167, 69, ${alpha})`,
            `rgba(255, 193, 7, ${alpha})`,
            `rgba(220, 53, 69, ${alpha})`,
            `rgba(23, 162, 184, ${alpha})`,
        ];
        return colors[index % colors.length];
    }
    
    async toggleNodeHealth(nodeName, healthy) {
        try {
            const url = `${this.apiBase}/nodes/${encodeURIComponent(nodeName)}/health?healthy=${healthy}`;
            const response = await fetch(url, {
                method: 'POST',
                headers: this.authHeaders()
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to update node health');
            }
            
            await this.loadNodes();
        } catch (error) {
            this.showError('Failed to update node health: ' + error.message);
        }
    }
    
    async exportCSV() {
        try {
            const response = await fetch(`${this.apiBase}/export/csv`);
            if (!response.ok) throw new Error('Export failed');
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `cwms_results_${Date.now()}.csv`;
            a.click();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            this.showError('CSV export failed: ' + error.message);
        }
    }
    
    async exportJSON() {
        try {
            const response = await fetch(`${this.apiBase}/export/json`);
            if (!response.ok) throw new Error('Export failed');
            
            const data = await response.json();
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `cwms_results_${Date.now()}.json`;
            a.click();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            this.showError('JSON export failed: ' + error.message);
        }
    }
    
    enableExports() {
        document.getElementById('export-csv').disabled = false;
        document.getElementById('export-json').disabled = false;
    }
    
    showLoading(show) {
        document.getElementById('loading-overlay').classList.toggle('active', show);
    }
    
    showError(message) {
        // Simple toast notification
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            background: #dc3545;
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
            z-index: 1001;
            animation: slideIn 0.3s ease;
        `;
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }
}

// Add toast animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new CWMSDashboard();
});