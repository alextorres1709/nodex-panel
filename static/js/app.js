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

// Charts — TradingView-inspired (blue accent, crosshair, gradient fill)
function getChartTheme() {
    const isDark = document.body.getAttribute('data-theme') === 'dark';
    return {
        text: isDark ? 'rgba(245,245,245,0.82)' : '#0a0a0a',
        textSoft: isDark ? 'rgba(245,245,245,0.46)' : '#6b7280',
        grid: isDark ? 'rgba(255,255,255,0.055)' : 'rgba(15,23,42,0.06)',
        gridStrong: isDark ? 'rgba(255,255,255,0.11)' : 'rgba(15,23,42,0.10)',
        border: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(15,23,42,0.08)',
        crosshair: isDark ? 'rgba(147,197,253,0.55)' : 'rgba(29,78,216,0.45)',
        tooltipBg: isDark ? '#0b0f1a' : '#0b0f1a',
        tooltipText: '#f8fafc',
        primary: isDark ? '#3b82f6' : '#1d4ed8',
        colors: isDark
            ? ['#3b82f6', '#38bdf8', '#6366f1', '#22d3ee', '#60a5fa', '#818cf8', '#0ea5e9', '#2563eb']
            : ['#1d4ed8', '#0ea5e9', '#4f46e5', '#0284c7', '#2563eb', '#6366f1', '#0369a1', '#1e40af'],
    };
}

// Crosshair plugin — vertical guideline on hover (TradingView feel)
const CrosshairPlugin = {
    id: 'nodexCrosshair',
    afterDraw(chart) {
        const active = chart.tooltip && chart.tooltip.getActiveElements && chart.tooltip.getActiveElements();
        if (!active || !active.length) return;
        const { ctx, chartArea } = chart;
        const x = active[0].element.x;
        const theme = getChartTheme();
        ctx.save();
        ctx.beginPath();
        ctx.setLineDash([4, 4]);
        ctx.moveTo(x, chartArea.top);
        ctx.lineTo(x, chartArea.bottom);
        ctx.lineWidth = 1;
        ctx.strokeStyle = theme.crosshair;
        ctx.stroke();
        ctx.restore();
    },
};

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
    Chart.defaults.plugins.tooltip.borderColor = 'rgba(148,163,184,0.18)';
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.padding = 12;
    Chart.defaults.plugins.tooltip.cornerRadius = 10;
    Chart.defaults.plugins.tooltip.boxPadding = 6;
    Chart.defaults.plugins.tooltip.caretSize = 0;
    Chart.defaults.plugins.tooltip.caretPadding = 12;
    Chart.defaults.plugins.tooltip.titleFont = { size: 11, weight: '600' };
    Chart.defaults.plugins.tooltip.bodyFont = { size: 13, weight: '600', family: "'SF Mono', ui-monospace, Menlo, Consolas, monospace" };
    Chart.defaults.plugins.tooltip.displayColors = true;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.pointStyle = 'circle';
    Chart.defaults.plugins.legend.labels.boxWidth = 6;
    Chart.defaults.plugins.legend.labels.boxHeight = 6;
    Chart.defaults.plugins.legend.labels.padding = 14;
    Chart.defaults.elements.arc.borderWidth = 0;
    Chart.defaults.elements.line.borderWidth = 2;
    Chart.defaults.elements.line.tension = 0.35;
    Chart.defaults.elements.line.borderCapStyle = 'round';
    Chart.defaults.elements.line.borderJoinStyle = 'round';
    Chart.defaults.elements.point.radius = 0;
    Chart.defaults.elements.point.hoverRadius = 5;
    Chart.defaults.elements.point.hoverBorderWidth = 2;
    Chart.defaults.elements.bar.borderRadius = 4;
    Chart.defaults.elements.bar.borderSkipped = false;
    if (Chart.register && !Chart.registry.plugins.get('nodexCrosshair')) {
        Chart.register(CrosshairPlugin);
    }
}
applyChartDefaults();

function nfmtCompact(v) {
    if (v == null || isNaN(v)) return v;
    const abs = Math.abs(v);
    if (abs >= 1e6) return (v / 1e6).toFixed(abs >= 1e7 ? 0 : 1) + 'M';
    if (abs >= 1e3) return (v / 1e3).toFixed(abs >= 1e4 ? 0 : 1) + 'k';
    return String(v);
}

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
    const primary = theme.primary;

    let bg;
    if (isDoughnut) {
        bg = theme.colors.slice(0, data.length);
    } else if (isLine) {
        const grad = ctx.getContext('2d').createLinearGradient(0, 0, 0, 240);
        grad.addColorStop(0, hexToRgba(primary, 0.38));
        grad.addColorStop(0.6, hexToRgba(primary, 0.08));
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
                borderWidth: isDoughnut ? 0 : 2.25,
                borderRadius: isDoughnut ? 0 : 4,
                tension: 0.35,
                fill: isLine,
                pointBackgroundColor: primary,
                pointBorderColor: theme.tooltipBg,
                pointHoverBorderColor: theme.tooltipBg,
                pointHoverBorderWidth: 2,
                pointHoverRadius: 5,
                spanGaps: true,
                cubicInterpolationMode: isLine ? 'monotone' : 'default',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 8, right: 6, bottom: 0, left: 0 } },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: isDoughnut,
                    position: 'bottom',
                    labels: { color: theme.textSoft, padding: 14, usePointStyle: true, boxWidth: 6, boxHeight: 6, font: { size: 11 } },
                },
                tooltip: {
                    enabled: true,
                    callbacks: {
                        label(ctx) {
                            const v = ctx.parsed.y ?? ctx.parsed;
                            try {
                                return ' ' + new Intl.NumberFormat('es-ES').format(v) + (label ? ' ' + label : '');
                            } catch (e) { return ' ' + v; }
                        },
                    },
                },
            },
            cutout: isDoughnut ? '68%' : undefined,
            scales: isDoughnut ? {} : {
                x: {
                    ticks: { color: theme.textSoft, font: { size: 10 }, padding: 8, maxRotation: 0 },
                    grid: { display: false, drawBorder: false },
                    border: { display: false },
                },
                y: {
                    position: 'right',
                    ticks: {
                        color: theme.textSoft,
                        font: { size: 10, family: "'SF Mono', ui-monospace, Menlo, Consolas, monospace" },
                        padding: 8,
                        maxTicksLimit: 5,
                        callback: (v) => nfmtCompact(v),
                    },
                    grid: { color: theme.grid, drawBorder: false, drawTicks: false, lineWidth: 1 },
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
