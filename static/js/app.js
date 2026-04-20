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
        text: isDark ? 'rgba(245,245,245,0.78)' : '#0a0a0a',
        textSoft: isDark ? 'rgba(245,245,245,0.48)' : '#737373',
        grid: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(10,10,10,0.06)',
        border: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(10,10,10,0.08)',
        tooltipBg: isDark ? '#0a0a0a' : '#0a0a0a',
        tooltipText: '#fafafa',
        colors: isDark
            ? ['#a78bfa', '#22d3ee', '#4ade80', '#fbbf24', '#f87171', '#f472b6', '#60a5fa', '#34d399']
            : ['#7c3aed', '#0891b2', '#059669', '#d97706', '#dc2626', '#db2777', '#2563eb', '#0d9488'],
    };
}

function applyChartDefaults() {
    if (typeof Chart === 'undefined') return;
    const t = getChartTheme();
    Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', system-ui, sans-serif";
    Chart.defaults.font.size = 11;
    Chart.defaults.font.weight = '500';
    Chart.defaults.color = t.textSoft;
    Chart.defaults.borderColor = t.border;
    Chart.defaults.plugins.tooltip.backgroundColor = t.tooltipBg;
    Chart.defaults.plugins.tooltip.titleColor = t.tooltipText;
    Chart.defaults.plugins.tooltip.bodyColor = t.tooltipText;
    Chart.defaults.plugins.tooltip.borderColor = 'rgba(255,255,255,0.08)';
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.boxPadding = 6;
    Chart.defaults.plugins.tooltip.titleFont = { size: 12, weight: '600' };
    Chart.defaults.plugins.tooltip.bodyFont = { size: 12, weight: '500' };
    Chart.defaults.plugins.tooltip.displayColors = true;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.pointStyle = 'circle';
    Chart.defaults.plugins.legend.labels.boxWidth = 6;
    Chart.defaults.plugins.legend.labels.boxHeight = 6;
    Chart.defaults.plugins.legend.labels.padding = 14;
    Chart.defaults.elements.arc.borderWidth = 0;
    Chart.defaults.elements.line.borderWidth = 2;
    Chart.defaults.elements.line.tension = 0.32;
    Chart.defaults.elements.point.radius = 0;
    Chart.defaults.elements.point.hoverRadius = 5;
    Chart.defaults.elements.point.hoverBorderWidth = 2;
    Chart.defaults.elements.bar.borderRadius = 6;
    Chart.defaults.elements.bar.borderSkipped = false;
}
applyChartDefaults();

const chartInstances = {};

function hexToRgba(hex, a) {
    const h = hex.replace('#', '');
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
}

function createChart(canvasId, type, labels, data, label) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (chartInstances[canvasId]) chartInstances[canvasId].destroy();

    applyChartDefaults();
    const theme = getChartTheme();
    const isDoughnut = type === 'doughnut' || type === 'pie';
    const isLine = type === 'line';
    const primary = theme.colors[0];

    let bg;
    if (isDoughnut) {
        bg = theme.colors.slice(0, data.length);
    } else if (isLine) {
        const grad = ctx.getContext('2d').createLinearGradient(0, 0, 0, 220);
        grad.addColorStop(0, hexToRgba(primary, 0.22));
        grad.addColorStop(1, hexToRgba(primary, 0.0));
        bg = grad;
    } else {
        bg = primary;
    }

    chartInstances[canvasId] = new Chart(ctx, {
        type: type,
        data: {
            labels: labels,
            datasets: [{
                label: label || '',
                data: data,
                backgroundColor: bg,
                borderColor: isDoughnut ? 'transparent' : primary,
                borderWidth: isDoughnut ? 0 : 2,
                borderRadius: isDoughnut ? 0 : 6,
                tension: 0.32,
                fill: isLine,
                pointBackgroundColor: primary,
                pointBorderColor: '#fff',
                pointHoverBorderColor: '#fff',
                spanGaps: true,
                cubicInterpolationMode: isLine ? 'monotone' : 'default',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 6, right: 4, bottom: 0, left: 0 } },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: isDoughnut,
                    position: 'bottom',
                    labels: { color: theme.textSoft, padding: 14, usePointStyle: true, boxWidth: 6, boxHeight: 6, font: { size: 11 } },
                },
                tooltip: { enabled: true },
            },
            cutout: isDoughnut ? '68%' : undefined,
            scales: isDoughnut ? {} : {
                x: {
                    ticks: { color: theme.textSoft, font: { size: 10 }, padding: 6 },
                    grid: { display: false, drawBorder: false },
                    border: { display: false },
                },
                y: {
                    ticks: { color: theme.textSoft, font: { size: 10 }, padding: 8, maxTicksLimit: 5 },
                    grid: { color: theme.grid, drawBorder: false, drawTicks: false },
                    border: { display: false },
                    beginAtZero: true,
                },
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
    if (window._nodexPendingReload) {
        window._nodexPendingReload = false;
        window.location.reload();
    }
}

document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
        if (window._nodexPendingReload) {
            window._nodexPendingReload = false;
            window.location.reload();
        }
    }
});

// Mobile sidebar
function toggleSidebar() {
    const s = document.querySelector('.sidebar');
    const o = document.querySelector('.sidebar-overlay');
    if (s) s.classList.toggle('open');
    if (o) o.classList.toggle('open');
}
// Auto-close sidebar on nav link click (mobile)
document.querySelectorAll('.sidebar-nav a').forEach(function(link) {
    link.addEventListener('click', function() {
        if (window.innerWidth <= 768) {
            const s = document.querySelector('.sidebar');
            const o = document.querySelector('.sidebar-overlay');
            if (s) s.classList.remove('open');
            if (o) o.classList.remove('open');
        }
    });
});

// macOS fullscreen detection — remove titlebar padding when in native fullscreen
(function() {
    if (document.documentElement.classList.contains('android-webview')) return;
    function checkMacFullscreen() {
        var fs = Math.abs(window.innerHeight - screen.height) < 10;
        document.documentElement.classList.toggle('macos-fullscreen', fs);
    }
    window.addEventListener('resize', checkMacFullscreen);
    checkMacFullscreen();
})();

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
