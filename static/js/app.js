// Theme
function initTheme() {
    const saved = localStorage.getItem('nodex-panel-theme') || 'dark';
    document.body.setAttribute('data-theme', saved);
    updateToggleIcon(saved);
}

function toggleTheme() {
    const current = document.body.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.body.setAttribute('data-theme', next);
    localStorage.setItem('nodex-panel-theme', next);
    updateToggleIcon(next);
    rebuildCharts();
}

function updateToggleIcon(theme) {
    const btn = document.getElementById('themeToggle');
    if (!btn) return;
    if (theme === 'dark') {
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
    } else {
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>';
    }
}

// Charts
function getChartTheme() {
    const isDark = document.body.getAttribute('data-theme') === 'dark';
    return {
        text: isDark ? '#e2e8f0' : '#0f172a',
        grid: isDark ? '#1e293b' : '#e2e8f0',
        colors: isDark
            ? ['#4ccd5c', '#36b446', '#6edb7a', '#22d3ee', '#fbbf24', '#a78bfa', '#ef4444', '#14b8a6']
            : ['#7c3aed', '#6d28d9', '#8b5cf6', '#06b6d4', '#f59e0b', '#a855f7', '#ef4444', '#14b8a6'],
    };
}

const chartInstances = {};

function createChart(canvasId, type, labels, data, label) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (chartInstances[canvasId]) chartInstances[canvasId].destroy();

    const theme = getChartTheme();
    const isDoughnut = type === 'doughnut' || type === 'pie';

    chartInstances[canvasId] = new Chart(ctx, {
        type: type,
        data: {
            labels: labels,
            datasets: [{
                label: label || '',
                data: data,
                backgroundColor: isDoughnut ? theme.colors.slice(0, data.length) : theme.colors[0],
                borderColor: isDoughnut ? 'transparent' : theme.colors[0],
                borderWidth: isDoughnut ? 0 : 2,
                borderRadius: isDoughnut ? 0 : 4,
                tension: 0.4,
                fill: type === 'line' ? { target: 'origin', alpha: 0.1 } : false,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: isDoughnut,
                    position: 'bottom',
                    labels: { color: theme.text, padding: 16, usePointStyle: true },
                },
            },
            scales: isDoughnut ? {} : {
                x: { ticks: { color: theme.text }, grid: { color: theme.grid } },
                y: { ticks: { color: theme.text }, grid: { color: theme.grid }, beginAtZero: true },
            },
        },
    });
}

let chartBuilders = [];
function registerChart(builder) { chartBuilders.push(builder); }
function rebuildCharts() { chartBuilders.forEach(fn => fn()); }

// Modal
function openModal(id) {
    const m = document.getElementById(id);
    if (m) m.classList.add('active');
}

function closeModal(id) {
    const m = document.getElementById(id);
    if (m) m.classList.remove('active');
}

document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
    }
});

// Mobile sidebar
function toggleSidebar() {
    const s = document.querySelector('.sidebar');
    if (s) s.classList.toggle('open');
}

// Edit modal population
function populateEditModal(data, formId) {
    const form = document.getElementById(formId);
    if (!form) return;
    Object.keys(data).forEach(key => {
        const input = form.querySelector('[name="' + key + '"]');
        if (input) {
            if (input.type === 'checkbox') {
                input.checked = !!data[key];
            } else {
                input.value = data[key] || '';
            }
        }
    });
}

// Confirm delete
function confirmDelete(form) {
    if (confirm('Seguro que quieres eliminar este registro?')) {
        form.submit();
    }
}

// Init
document.addEventListener('DOMContentLoaded', function() {
    initTheme();
    rebuildCharts();
});
