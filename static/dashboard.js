'use strict';

const byId = (id) => document.getElementById(id);
const readDashboard = (page) => JSON.parse(page.querySelector('#dashboard-data').textContent);
let dashboard = readDashboard(document);
let currentLab = dashboard.initialLab;

const labSelect = byId('lab-select');
const labNodes = [...document.querySelectorAll('.lab-node')];
const deviceButtons = [...document.querySelectorAll('.device-grid .device')];
const trainer = byId('trainer-device');
const dialog = byId('device-dialog');
const dashboardContent = byId('content');
const sidebar = byId('sidebar');
const navToggle = byId('nav-toggle');
const navOverlay = document.querySelector('.nav-overlay');
const drawerLayout = window.matchMedia('(max-width: 1060px)');
const stackedLayout = window.matchMedia('(max-width: 680px)');
const riyadhTime = new Intl.DateTimeFormat('ar-SA', {
    calendar: 'gregory', numberingSystem: 'latn', timeZone: 'Asia/Riyadh',
    dateStyle: 'medium', timeStyle: 'short',
});

function renderLab() {
    const states = dashboard.deviceStates[currentLab];
    const links = dashboard.labLinks[currentLab];
    byId('devices-heading').textContent = `أجهزة معمل (${currentLab})`;
    labSelect.value = currentLab;
    byId('lab-qr-link').href = links.qr;
    const report = byId('lab-report-link');
    report.href = links.report;
    report.querySelector('span').textContent = `بلاغ جديد لمعمل (${currentLab})`;

    for (const node of labNodes) {
        const lab = Number(node.dataset.lab);
        const state = dashboard.labStates[lab];
        node.dataset.state = state;
        node.setAttribute('aria-label', `معمل ${lab}، ${dashboard.labLabels[state]}`);
        if (lab === currentLab) {
            node.setAttribute('aria-current', 'true');
        } else {
            node.removeAttribute('aria-current');
        }
    }

    const trainerState = states[0] || 'ok';
    trainer.dataset.state = trainerState;
    const trainerLabel = trainer.querySelector('.status-pill');
    trainerLabel.dataset.tone = trainerState;
    trainerLabel.textContent = dashboard.deviceLabels[trainerState];

    let ready = 0;
    for (const device of deviceButtons) {
        const state = states[device.dataset.seat] || 'ok';
        device.dataset.state = state;
        device.querySelector('small').textContent = dashboard.deviceLabels[state];
        ready += Number(state === 'ok');
    }
    byId('device-count').textContent = `${ready} من ${deviceButtons.length} جاهزة`;
}

function selectLab(lab) {
    currentLab = lab;
    renderLab();
    const url = new URL(window.location.href);
    url.searchParams.set('lab', lab);
    history.replaceState(history.state, '', url);
}

labSelect.addEventListener('change', () => selectLab(Number(labSelect.value)));
for (const node of labNodes) {
    node.addEventListener('click', (event) => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.defaultPrevented) return;
        event.preventDefault();
        selectLab(Number(node.dataset.lab));
        if (stackedLayout.matches) {
            const heading = byId('devices-heading');
            heading.focus({ preventScroll: true });
            byId('devices').scrollIntoView({ block: 'start' });
        }
    });
}

function ticketNumber(ticket) {
    return `#${ticket.lab}-${ticket.id}`;
}

function historyItem(ticket) {
    const item = document.createElement('li');
    const header = document.createElement('div');
    header.className = 'history-row-head';
    const label = document.createElement('strong');
    label.textContent = [ticketNumber(ticket), ticket.category].filter(Boolean).join(' · ');
    label.dir = 'auto';
    header.append(label);
    if (ticket.created) {
        const date = new Date(ticket.created.trim().replace(' ', 'T').replace(/T(\d\d:\d\d(?::\d\d(?:\.\d+)?)?)$/, 'T$1Z'));
        if (!Number.isNaN(date.getTime())) {
            const time = document.createElement('time');
            time.dateTime = date.toISOString();
            time.textContent = riyadhTime.format(date);
            header.append(time);
        }
    }
    const description = document.createElement('p');
    description.className = 'history-description';
    description.textContent = ticket.issue || '';
    item.append(header, description);
    if (ticket.parts && ticket.parts !== 'لا يوجد') {
        const parts = document.createElement('small');
        parts.textContent = `القطع المستبدلة: ${ticket.parts}`;
        item.append(parts);
    }
    return item;
}

function openDevice(lab, seat) {
    const related = dashboard.tickets.filter((ticket) => ticket.lab === lab && ticket.seat === seat);
    const active = related.find((ticket) => ticket.updateUrl);
    const previous = related.filter((ticket) => !ticket.updateUrl);
    const validSeat = seat === 0 || deviceButtons.some((device) => Number(device.dataset.seat) === seat);
    const deviceName = seat === 0 ? 'منصة المدرب' : validSeat ? `جهاز ${seat}` : 'جهاز غير محدد';
    byId('dialog-device').textContent = `معمل ${lab} · ${deviceName}`;
    byId('active-ticket').hidden = !active;
    byId('no-active-ticket').hidden = Boolean(active);
    const statusForm = byId('status-form');
    statusForm.hidden = !active;
    if (active) {
        const badge = byId('dialog-status');
        badge.dataset.tone = dashboard.statusTones[active.status] || 'danger';
        badge.textContent = active.status || 'بلاغ نشط';
        byId('dialog-ticket-id').textContent = ticketNumber(active);
        byId('dialog-reporter').textContent = active.reporter || '—';
        byId('dialog-category').textContent = active.category || '—';
        byId('dialog-issue').textContent = active.issue || '—';
        const status = byId('ticket-status');
        status.value = active.status;
        if (!status.value) status.selectedIndex = 0;
        byId('ticket-parts').value = active.parts === 'لا يوجد' ? '' : active.parts || '';
        byId('status-dashboard-lab').value = currentLab;
        statusForm.action = active.updateUrl;
    }

    const report = byId('device-report-link');
    report.hidden = Boolean(active) || !validSeat;
    if (!report.hidden) {
        const url = new URL(dashboard.labLinks[lab].report, window.location.href);
        url.searchParams.set('seat', seat);
        report.href = url;
    }

    byId('history-list').replaceChildren(...previous.map(historyItem));
    byId('history-empty').hidden = previous.length > 0;
    if (!dialog.open) dialog.showModal();
}

dashboardContent.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-seat]');
    if (!button) return;
    const seat = button.dataset.seat === '' ? null : Number(button.dataset.seat);
    openDevice(Number(button.dataset.ticketLab || currentLab), seat);
});
dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
});

function searchText(value) {
    return value.toLowerCase().replace(/[٠-٩۰-۹]/g, (digit) => String(digit.charCodeAt(0) & 15))
        .replace(/[\u064B-\u065F\u0670\u0640]/g, '').replace(/[أإآٱ]/g, 'ا').trim();
}

function filterTickets() {
    const query = searchText(byId('ticket-search')?.value || '');
    const status = byId('ticket-filter')?.value || '';
    let visible = 0;
    for (const row of document.querySelectorAll('[data-ticket-row]')) {
        const match = (!status || row.dataset.status === status) && searchText(row.textContent).includes(query);
        row.hidden = !match;
        visible += Number(match);
    }
    byId('ticket-count').textContent = `${visible} بلاغ`;
    const empty = byId('no-matches');
    if (empty) empty.hidden = visible > 0;
}

dashboardContent.addEventListener('input', (event) => {
    if (event.target.id === 'ticket-search') filterTickets();
});
dashboardContent.addEventListener('change', (event) => {
    if (event.target.id === 'ticket-filter') filterTickets();
});

function setDrawer(open, restoreFocus = true) {
    const wasOpen = sidebar.classList.contains('is-open');
    sidebar.classList.toggle('is-open', open);
    navToggle.setAttribute('aria-expanded', String(open));
    navToggle.setAttribute('aria-label', open ? 'إغلاق القائمة' : 'فتح القائمة');
    navOverlay.hidden = !open;
    document.querySelector('.workspace').inert = open;
    if (open) {
        sidebar.querySelector('[aria-current]').focus();
    } else if (wasOpen && restoreFocus) {
        navToggle.focus();
    }
}

navToggle.addEventListener('click', () => setDrawer(navOverlay.hidden));
navOverlay.addEventListener('click', () => setDrawer(false));
sidebar.addEventListener('click', (event) => {
    if (event.target.closest('a') && !navOverlay.hidden) setDrawer(false);
});
drawerLayout.addEventListener('change', () => setDrawer(false, false));
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !navOverlay.hidden) setDrawer(false);
});

function updateSection() {
    const hash = window.location.hash.slice(1);
    const links = [...sidebar.querySelectorAll('[data-section]')];
    const active = links.find((link) => link.dataset.section === hash) || links[0];
    for (const link of links) {
        if (link === active) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
    }
    byId('section-name').textContent = active.textContent.trim();
}

window.addEventListener('hashchange', updateSection);
updateSection();

const viewport = byId('map-viewport');
const zoomIn = byId('zoom-in');
const zoomOut = byId('zoom-out');
const zoomReset = byId('zoom-reset');
let zoomLevel = 0;
let drag = null;
let suppressClick = false;

function zoomTo(level) {
    const width = viewport.clientWidth;
    const height = viewport.clientHeight;
    const centerX = (viewport.scrollLeft + width / 2) / viewport.scrollWidth;
    const centerY = (viewport.scrollTop + height / 2) / viewport.scrollHeight;

    zoomLevel = Math.max(0, Math.min(level, 4));
    viewport.style.setProperty('--map-zoom', String(1 + zoomLevel * .35));
    viewport.classList.toggle('is-zoomed', zoomLevel > 0);
    viewport.scrollLeft = centerX * viewport.scrollWidth - viewport.clientWidth / 2;
    viewport.scrollTop = centerY * viewport.scrollHeight - viewport.clientHeight / 2;
    zoomIn.disabled = zoomLevel === 4;
    zoomOut.disabled = zoomLevel === 0;
    zoomReset.hidden = zoomLevel === 0;
}

zoomIn.addEventListener('click', () => zoomTo(zoomLevel + 1));
zoomOut.addEventListener('click', () => zoomTo(zoomLevel - 1));
zoomReset.addEventListener('click', () => {
    zoomTo(0);
    zoomIn.focus();
});
viewport.addEventListener('pointerdown', (event) => {
    suppressClick = false;
    if (!zoomLevel || event.pointerType !== 'mouse' || event.button !== 0) return;
    drag = { x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
});
viewport.addEventListener('pointermove', (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!suppressClick && Math.hypot(dx, dy) < 5) return;
    suppressClick = true;
    viewport.setPointerCapture(event.pointerId);
    viewport.classList.add('is-dragging');
    viewport.scrollLeft = drag.left - dx;
    viewport.scrollTop = drag.top - dy;
});
for (const eventName of ['pointerup', 'pointercancel', 'pointerleave', 'lostpointercapture']) {
    viewport.addEventListener(eventName, () => {
        drag = null;
        viewport.classList.remove('is-dragging');
    });
}
viewport.addEventListener('click', (event) => {
    if (suppressClick && event.detail) {
        event.preventDefault();
        event.stopPropagation();
    }
    suppressClick = false;
}, true);

const monitor = byId('monitor-toggle');
const monitorStatus = byId('monitor-status');
const refreshInterval = 30;
let refreshAt = 0;
let monitorTimer;
let refreshing = false;

async function refreshDashboard() {
    if (refreshing || dialog.open || document.activeElement?.closest('.ticket-toolbar')) return;
    refreshing = true;
    try {
        const url = new URL(window.location.href);
        url.searchParams.set('lab', currentLab);
        const response = await fetch(url, { cache: 'no-store' });
        if (response.redirected) {
            window.location.assign(response.url);
            return;
        }
        if (!response.ok) throw new Error('Dashboard refresh failed');
        const page = new DOMParser().parseFromString(await response.text(), 'text/html');
        if (!monitorTimer || dialog.open || document.activeElement?.closest('.ticket-toolbar')) return;
        const query = byId('ticket-search')?.value;
        const status = byId('ticket-filter')?.value;
        dashboard = readDashboard(page);
        const reminder = document.querySelector('.report-reminder');
        const freshReminder = page.querySelector('.report-reminder');
        if (reminder && freshReminder) reminder.replaceWith(freshReminder);
        else if (reminder) reminder.remove();
        else if (freshReminder) document.querySelector('.metrics').before(freshReminder);
        for (const selector of ['.metrics', '.lower-layout']) {
            document.querySelector(selector).replaceWith(page.querySelector(selector));
        }
        if (query && byId('ticket-search')) byId('ticket-search').value = query;
        if (status && byId('ticket-filter')) byId('ticket-filter').value = status;
        filterTickets();
        renderLab();
    } catch (error) {
        console.warn('Dashboard refresh failed', error);
    } finally {
        refreshing = false;
        refreshAt = Date.now() + refreshInterval * 1000;
    }
}

function updateCountdown() {
    const remaining = Math.max(0, Math.ceil((refreshAt - Date.now()) / 1000));
    byId('countdown').textContent = String(remaining);
    if (remaining === 0) refreshDashboard();
}

function stopMonitor() {
    clearInterval(monitorTimer);
    monitorTimer = null;
    document.body.classList.remove('monitor-active');
    monitor.setAttribute('aria-pressed', 'false');
    monitor.querySelector('span').textContent = 'شاشة المراقبة';
    monitorStatus.hidden = true;
}

monitor.addEventListener('click', () => {
    if (monitorTimer) {
        stopMonitor();
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        return;
    }
    setDrawer(false);
    document.body.classList.add('monitor-active');
    monitor.setAttribute('aria-pressed', 'true');
    monitor.querySelector('span').textContent = 'إنهاء المراقبة';
    monitorStatus.hidden = false;
    refreshAt = Date.now() + refreshInterval * 1000;
    monitorTimer = setInterval(updateCountdown, 1000);
    updateCountdown();
    document.documentElement.requestFullscreen?.().catch(() => {});
});
document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && monitorTimer) stopMonitor();
});
