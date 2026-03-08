// Theme
function initTheme() {
    const saved = localStorage.getItem('nodex-panel-theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    updateToggleIcon(saved);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('nodex-panel-theme', next);
    updateToggleIcon(next);
    rebuildCharts();
}

function updateToggleIcon(theme) {
    const btn = document.getElementById('themeToggle');
    if (btn) btn.textContent = theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19';
}

// Charts
function getChartTheme() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    return {
        text: isDark ? '#e2e8f0' : '#0f172a',
        grid: isDark ? '#1e293b' : '#e2e8f0',
        colors: ['#a3e635', '#0a0a0a', '#84cc16', '#22d3ee', '#f59e0b', '#c084fc', '#ef4444', '#14b8a6'],
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
