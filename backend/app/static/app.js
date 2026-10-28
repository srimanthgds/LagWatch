/**
 * InsulGuard 4.0 - ISA-101 High Performance HMI Application Engine
 * Real-Time Telemetry, API RP 581 Risk Matrix, UT/PEC Calibration, and Work Orders
 */

// Global State
const state = {
  activeTab: 'tabOverview',
  currentRole: 'engineer',
  token: null,
  userProfile: null,
  segments: [],
  filteredSegments: [],
  alarms: [],
  kpis: null,
  matrixData: null,
  activeMatrixCell: null,
  calibrationScatter: [],
  calibrationStats: null,
  workOrders: [],
  digs: [],
  financials: null,
  ws: null,
  telemetryMsgCount: 0,
  telemetryFeed: [],
  charts: {
    healthDonut: null,
    calibrationScatter: null
  }
};

const PERSONA_CREDENTIALS = {
  admin: { email: 'admin@insulguard.com', password: 'adminpassword123' },
  engineer: { email: 'engineer@insulguard.com', password: 'engineerpassword123' },
  viewer: { email: 'viewer@insulguard.com', password: 'viewerpassword123' }
};

// ==========================================
// Toast Notification Utility
// ==========================================
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span style="font-size: 1.1rem;">${type === 'success' ? '✓' : type === 'error' ? '⚠' : 'ℹ'}</span>
    <span>${message}</span>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ==========================================
// Authentication & API Client
// ==========================================
async function authenticatePersona(role) {
  try {
    const creds = PERSONA_CREDENTIALS[role] || PERSONA_CREDENTIALS.engineer;
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(creds)
    });

    if (!res.ok) throw new Error('Authentication failed');
    const data = await res.json();
    state.token = data.access_token;
    state.currentRole = role;
    state.userProfile = {
      email: data.email,
      name: data.full_name,
      role: data.role
    };

    showToast(`Authenticated as ${data.full_name} (${data.role.toUpperCase()})`, 'success');
  } catch (err) {
    console.error('Auth error:', err);
    showToast('Failed to switch persona credentials', 'error');
  }
}

function getAuthHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (state.token) {
    headers['Authorization'] = `Bearer ${state.token}`;
  }
  return headers;
}

// ==========================================
// WebSocket Real-Time Stream
// ==========================================
function initWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.host}/ws/live`;
  
  const statusBadge = document.getElementById('wsStatusBadge');
  const statusText = document.getElementById('wsStatusText');

  try {
    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
      statusBadge.classList.remove('disconnected');
      statusText.textContent = 'LIVE TELEMETRY (3s PULSE)';
      showToast('Connected to InsulGuard real-time sensor field stream', 'info');

      // Periodic heartbeat ping
      setInterval(() => {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
          state.ws.send(JSON.stringify({ type: 'PING' }));
        }
      }, 15000);
    };

    state.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleIncomingTelemetry(payload);
      } catch (e) {
        console.error('WS Parse Error:', e);
      }
    };

    state.ws.onclose = () => {
      statusBadge.classList.add('disconnected');
      statusText.textContent = 'DISCONNECTED (RECONNECTING...)';
      setTimeout(initWebSocket, 4000);
    };

    state.ws.onerror = (err) => {
      console.warn('WS Stream Hiccup:', err);
    };
  } catch (err) {
    console.error('Failed to init WS:', err);
  }
}

function handleIncomingTelemetry(payload) {
  if (payload.type === 'NODE_TELEMETRY_BATCH') {
    state.telemetryMsgCount++;
    document.getElementById('telemetryPulseCount').textContent = `${state.telemetryMsgCount} pulses`;

    const readings = payload.readings || [];
    const streamBody = document.getElementById('telemetryStreamBody');

    // Prepend new readings
    readings.forEach((r) => {
      const row = document.createElement('tr');
      row.className = 'flash-update';
      const timeStr = new Date(r.last_seen).toLocaleTimeString();

      const moistClass = r.moisture_pct > 25 ? 'text-rose' : r.moisture_pct > 10 ? 'text-amber' : 'text-emerald';

      row.innerHTML = `
        <td class="font-mono" style="font-weight: 600;">${r.node_id}</td>
        <td><span class="badge ${r.clock_position === 6 ? 'badge-priority' : 'badge-healthy'}">${r.clock_position}h</span></td>
        <td class="font-mono ${moistClass}" style="font-weight: 600;">${r.moisture_pct}%</td>
        <td class="font-mono">${r.jacket_temp_C}°C</td>
        <td class="font-mono">${r.battery_pct}%</td>
        <td class="text-muted" style="font-size: 0.72rem;">${timeStr}</td>
      `;

      if (streamBody.firstChild) {
        streamBody.insertBefore(row, streamBody.firstChild);
      } else {
        streamBody.appendChild(row);
      }
    });

    // Keep max 25 rows in table
    while (streamBody.children.length > 25) {
      streamBody.removeChild(streamBody.lastChild);
    }
  }
}

// ==========================================
// Data Fetching & KPIs
// ==========================================
async function loadKpis() {
  try {
    const res = await fetch('/api/v1/kpis');
    if (!res.ok) throw new Error('Failed to load KPIs');
    const data = await res.json();
    state.kpis = data;

    // Update Ticker
    document.getElementById('kpiTotalSegments').textContent = data.total_segments;
    document.getElementById('kpiTotalNodes').textContent = data.total_nodes.toLocaleString();
    document.getElementById('kpiWetCount').textContent = data.wet_segments_count;
    document.getElementById('kpiWetPct').textContent = `(${data.wet_segments_pct}%)`;
    
    const critTotal = (data.health_breakdown['Critical'] || 0) + (data.health_breakdown['Imminent'] || 0);
    document.getElementById('kpiCriticalCount').textContent = critTotal;
    
    document.getElementById('kpiActiveAlarms').textContent = data.active_alarms_count;
    document.getElementById('headerAlarmCount').textContent = data.active_alarms_count;
    document.getElementById('tabAlarmBadge').textContent = data.active_alarms_count;

    const avoidedM = (data.projected_avoided_cost_usd / 1000000).toFixed(2);
    document.getElementById('kpiAvoidedLoss').textContent = `$${avoidedM}M`;

    renderHealthDonutChart(data.health_breakdown);
  } catch (err) {
    console.error('KPI error:', err);
  }
}

function renderHealthDonutChart(breakdown) {
  const ctx = document.getElementById('healthDonutChart');
  if (!ctx) return;

  const labels = ['Healthy', 'Watch', 'Priority', 'Critical', 'Imminent'];
  const values = labels.map((l) => breakdown[l] || 0);
  const colors = ['#10b981', '#f59e0b', '#f97316', '#ef4444', '#e11d48'];

  if (state.charts.healthDonut) {
    state.charts.healthDonut.destroy();
  }

  state.charts.healthDonut = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: colors,
          borderColor: '#0f172a',
          borderWidth: 2,
          hoverOffset: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '72%',
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(15, 23, 42, 0.95)',
          titleColor: '#f8fafc',
          bodyColor: '#94a3b8',
          borderColor: '#1e293b',
          borderWidth: 1,
          padding: 10
        }
      }
    }
  });

  // Render HTML Legend
  const legendContainer = document.getElementById('healthLegendContainer');
  const total = values.reduce((a, b) => a + b, 0) || 1;

  legendContainer.innerHTML = labels
    .map((l, i) => {
      const cnt = values[i];
      const pct = ((cnt / total) * 100).toFixed(1);
      return `
      <div style="display: flex; align-items: center; justify-content: space-between; font-size: 0.8rem;">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
          <span style="width: 10px; height: 10px; border-radius: 2px; background: ${colors[i]};"></span>
          <span>${l}</span>
        </div>
        <div style="display: flex; align-items: baseline; gap: 0.4rem;">
          <span class="font-mono" style="font-weight: 600; color: #fff;">${cnt}</span>
          <span class="text-muted" style="font-size: 0.7rem;">(${pct}%)</span>
        </div>
      </div>
    `;
    })
    .join('');
}

// ==========================================
// Segments Explorer
// ==========================================
async function loadSegments() {
  try {
    const res = await fetch('/api/v1/segments?limit=350');
    if (!res.ok) throw new Error('Failed to load segments');
    const data = await res.json();
    state.segments = data;
    filterAndRenderSegments();
    renderUnitBreakdownCards(data);
    populateSelectDropdowns(data);
  } catch (err) {
    console.error('Segments error:', err);
  }
}

function filterAndRenderSegments() {
  const searchTerm = (document.getElementById('segSearchInput')?.value || '').toLowerCase();
  const areaFilter = document.getElementById('areaFilter')?.value || '';
  const healthFilter = document.getElementById('healthFilter')?.value || '';
  const riskFilter = document.getElementById('riskFilter')?.value || '';

  state.filteredSegments = state.segments.filter((s) => {
    if (searchTerm && !s.line_tag.toLowerCase().includes(searchTerm) && !s.material.toLowerCase().includes(searchTerm)) {
      return false;
    }
    if (areaFilter && s.area !== areaFilter) return false;
    if (healthFilter && s.health_state !== healthFilter) return false;
    if (riskFilter && s.risk_ranking !== riskFilter) return false;
    return true;
  });

  const countBadge = document.getElementById('filteredSegCount');
  if (countBadge) countBadge.textContent = `${state.filteredSegments.length} lines displayed`;

  const tbody = document.getElementById('segmentsTableBody');
  if (!tbody) return;

  if (state.filteredSegments.length === 0) {
    tbody.innerHTML = `<tr><td colspan="12" style="text-align:center; padding: 2rem; color: var(--text-muted);">No piping segments match selected criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = state.filteredSegments
    .slice(0, 100)
    .map((s) => {
      // Wall thickness loss calculation
      const lossMm = Math.max(0, s.nominal_wall_mm - s.current_wall_mm);
      const lossPct = Math.min(100, (lossMm / s.nominal_wall_mm) * 100).toFixed(1);
      const remMargin = Math.max(0, s.current_wall_mm - s.t_min_mm);
      const totalMargin = s.nominal_wall_mm - s.t_min_mm || 1;
      const barPct = Math.min(100, Math.max(0, (remMargin / totalMargin) * 100)).toFixed(0);

      const barColor =
        s.health_state === 'Healthy'
          ? '#10b981'
          : s.health_state === 'Watch'
          ? '#f59e0b'
          : s.health_state === 'Priority'
          ? '#f97316'
          : '#ef4444';

      const healthBadgeClass =
        s.health_state === 'Healthy'
          ? 'badge-healthy'
          : s.health_state === 'Watch'
          ? 'badge-watch'
          : s.health_state === 'Priority'
          ? 'badge-priority'
          : s.health_state === 'Critical'
          ? 'badge-critical'
          : 'badge-imminent';

      return `
      <tr>
        <td class="font-mono" style="font-weight: 700; color: #fff;">${s.line_tag}</td>
        <td style="font-size: 0.78rem;">${s.area}</td>
        <td class="text-muted" style="font-size: 0.75rem;">${s.material}</td>
        <td><span class="badge ${s.service === 'steam-traced' ? 'badge-watch' : 'badge-healthy'}">${s.service}</span></td>
        <td class="font-mono">${lossPct}%</td>
        <td>
          <div class="wall-progress-wrap">
            <div style="display: flex; justify-content: space-between; font-size: 0.68rem;" class="font-mono">
              <span style="color: ${barColor}; font-weight: 600;">${s.current_wall_mm.toFixed(2)}</span>
              <span class="text-muted">${s.nominal_wall_mm.toFixed(1)}</span>
            </div>
            <div class="wall-progress-bar">
              <div class="wall-progress-fill" style="width: ${barPct}%; background-color: ${barColor};"></div>
            </div>
          </div>
        </td>
        <td class="font-mono" style="font-weight: 600; color: ${s.remaining_life_yr < 2 ? '#ef4444' : s.remaining_life_yr < 5 ? '#f59e0b' : '#34d399'};">
          ${s.remaining_life_yr.toFixed(1)} yr
        </td>
        <td class="font-mono text-muted">${s.effective_cr_mm_yr.toFixed(2)}</td>
        <td class="font-mono">${(s.rolling_wet_fraction * 100).toFixed(0)}%</td>
        <td><span class="badge ${healthBadgeClass}">${s.health_state}</span></td>
        <td><span class="badge badge-alarm-${s.alarm_state}">State ${s.alarm_state}</span></td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="openSegmentInspector(${s.id})">
            Inspect
          </button>
        </td>
      </tr>
    `;
    })
    .join('');
}

function renderUnitBreakdownCards(segments) {
  const container = document.getElementById('unitCardsGrid');
  if (!container) return;

  const unitMap = {};
  segments.forEach((s) => {
    if (!unitMap[s.area]) {
      unitMap[s.area] = { total: 0, wet: 0, critical: 0 };
    }
    unitMap[s.area].total++;
    if (s.rolling_wet_fraction > 0.1) unitMap[s.area].wet++;
    if (s.health_state === 'Critical' || s.health_state === 'Imminent') unitMap[s.area].critical++;
  });

  container.innerHTML = Object.entries(unitMap)
    .map(([area, stats]) => {
      const wetPct = ((stats.wet / stats.total) * 100).toFixed(0);
      return `
      <div class="kpi-card ${stats.critical > 0 ? 'rose' : stats.wet > 5 ? 'amber' : 'cyan'}" style="flex-direction: column; align-items: flex-start; cursor: pointer;" onclick="filterByUnit('${area}')">
        <span style="font-size: 0.82rem; font-weight: 600; color: #fff; margin-bottom: 0.25rem;">${area}</span>
        <div style="display: flex; gap: 0.8rem; font-size: 0.72rem; color: var(--text-secondary);">
          <span>Total: <strong class="text-cyan">${stats.total}</strong></span>
          <span>Wet: <strong class="text-amber">${stats.wet} (${wetPct}%)</strong></span>
          <span>Crit: <strong class="text-rose">${stats.critical}</strong></span>
        </div>
      </div>
    `;
    })
    .join('');
}

function filterByUnit(area) {
  const areaSelect = document.getElementById('areaFilter');
  if (areaSelect) {
    areaSelect.value = area;
    switchTab('tabSegments');
    filterAndRenderSegments();
  }
}

// ==========================================
// Segment Detail Inspector Modal
// ==========================================
async function openSegmentInspector(segmentId) {
  try {
    const res = await fetch(`/api/v1/segments/${segmentId}`);
    if (!res.ok) throw new Error('Segment detail failed');
    const seg = await res.json();

    document.getElementById('modalLineTagTitle').textContent = `${seg.line_tag} — Detail Inspector`;
    document.getElementById('modalAreaSubtitle').textContent = `${seg.area} • ${seg.material} • Service: ${seg.service.toUpperCase()}`;
    document.getElementById('svgNominalText').textContent = `${seg.material.split(' ')[0]} ${seg.nominal_wall_mm}mm`;

    document.getElementById('modalCurrentWall').textContent = `${seg.current_wall_mm.toFixed(2)} mm`;
    document.getElementById('modalNominalWall').textContent = `/ ${seg.nominal_wall_mm.toFixed(1)} mm nom (t_min: ${seg.t_min_mm.toFixed(1)}mm)`;
    document.getElementById('modalRemLife').textContent = `${seg.remaining_life_yr.toFixed(1)} yrs`;

    const healthEl = document.getElementById('modalHealthState');
    healthEl.textContent = seg.health_state;
    healthEl.className = `badge ${seg.health_state === 'Healthy' ? 'badge-healthy' : seg.health_state === 'Watch' ? 'badge-watch' : 'badge-critical'}`;

    document.getElementById('modalEffCR').textContent = `${seg.effective_cr_mm_yr.toFixed(2)} mm/yr`;
    document.getElementById('modalRollingWet').textContent = `Wet Fraction: ${(seg.rolling_wet_fraction * 100).toFixed(0)}%`;

    // Update SVG Sensor Nodes Colors
    const nodeMap = {};
    (seg.nodes || []).forEach((n) => {
      nodeMap[n.clock_position] = n;
    });

    [3, 6, 9].forEach((pos) => {
      const circleEl = document.getElementById(`svgNode${pos}`);
      if (circleEl) {
        const node = nodeMap[pos];
        if (node) {
          const fill = node.moisture_pct > 25 ? '#ef4444' : node.moisture_pct > 10 ? '#f59e0b' : '#10b981';
          circleEl.setAttribute('fill', fill);
          circleEl.setAttribute('r', node.moisture_pct > 25 ? '10' : '8');
        }
      }
    });

    // Populate Attached Nodes Table
    const tbody = document.getElementById('modalNodesTableBody');
    tbody.innerHTML = (seg.nodes || [])
      .map((n) => {
        const timeStr = new Date(n.last_seen).toLocaleTimeString();
        const moistColor = n.moisture_pct > 25 ? '#f87171' : n.moisture_pct > 10 ? '#fbbf24' : '#34d399';
        return `
        <tr>
          <td class="font-mono" style="font-weight: 600;">${n.id}</td>
          <td><span class="badge ${n.clock_position === 6 ? 'badge-priority' : 'badge-healthy'}">${n.clock_position} o'clock</span></td>
          <td class="font-mono" style="font-weight: 600; color: ${moistColor};">${n.moisture_pct.toFixed(1)}%</td>
          <td class="font-mono">${n.jacket_temp_C.toFixed(1)} °C</td>
          <td class="font-mono">${n.battery_pct.toFixed(0)}%</td>
          <td class="text-muted" style="font-size: 0.72rem;">${timeStr}</td>
        </tr>
      `;
      })
      .join('');

    const modal = document.getElementById('segmentDetailModal');
    modal.classList.add('open');
  } catch (err) {
    console.error('Inspector error:', err);
    showToast('Failed to load segment details', 'error');
  }
}

// ==========================================
// API RP 581 Risk Matrix
// ==========================================
async function loadRiskMatrix() {
  try {
    const res = await fetch('/api/v1/risk/matrix');
    if (!res.ok) throw new Error('Risk matrix load failed');
    const data = await res.json();
    state.matrixData = data;

    const matrix = data.matrix || {};
    ['A', 'B', 'C', 'D', 'E'].forEach((cof) => {
      for (let pof = 1; pof <= 5; pof++) {
        const cell = document.getElementById(`cell-${cof}${pof}`);
        if (cell) {
          const count = matrix[cof]?.[pof] || 0;
          cell.querySelector('.cell-count').textContent = count;
        }
      }
    });

    const summary = data.summary || {};
    document.getElementById('riskCountHigh').textContent = summary['High'] || 0;
    document.getElementById('riskCountMedHigh').textContent = summary['Medium-High'] || 0;
    document.getElementById('riskCountMed').textContent = summary['Medium'] || 0;
    document.getElementById('riskCountLow').textContent = summary['Low'] || 0;

    loadInspectionPlanner();
  } catch (err) {
    console.error('Risk matrix error:', err);
  }
}

async function loadInspectionPlanner() {
  try {
    const res = await fetch('/api/v1/risk/inspection-planner?limit=50');
    if (!res.ok) throw new Error('Inspection planner load failed');
    const data = await res.json();

    const tbody = document.getElementById('inspectionPlannerBody');
    if (!tbody) return;

    tbody.innerHTML = data
      .map((s, idx) => {
        const riskClass =
          s.risk_ranking === 'High'
            ? 'badge-critical'
            : s.risk_ranking === 'Medium-High'
            ? 'badge-priority'
            : s.risk_ranking === 'Medium'
            ? 'badge-watch'
            : 'badge-healthy';

        return `
        <tr>
          <td class="font-mono text-muted">#${idx + 1}</td>
          <td class="font-mono" style="font-weight: 700; color: #fff;">${s.line_tag}</td>
          <td style="font-size: 0.78rem;">${s.area}</td>
          <td><span class="badge ${riskClass}">${s.risk_ranking}</span></td>
          <td class="font-mono" style="font-weight: 600;">POF ${s.pof_category}</td>
          <td class="font-mono" style="font-weight: 600;">Cat ${s.consequence_category}</td>
          <td class="font-mono" style="font-weight: 600; color: ${s.remaining_life_yr < 2 ? '#ef4444' : '#fbbf24'};">
            ${s.remaining_life_yr.toFixed(1)} yr
          </td>
          <td class="font-mono text-muted">${s.next_inspection_date}</td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="openSegmentInspector(${s.id})">
              Details
            </button>
          </td>
        </tr>
      `;
      })
      .join('');
  } catch (err) {
    console.error('Planner error:', err);
  }
}

// Matrix Cell Click Event
function initMatrixListeners() {
  document.querySelectorAll('.matrix-cell').forEach((cell) => {
    cell.addEventListener('click', () => {
      const cof = cell.getAttribute('data-cof');
      const pof = parseInt(cell.getAttribute('data-pof'), 10);
      const cellLabel = `${cof}${pof}`;

      document.querySelectorAll('.matrix-cell').forEach((c) => c.classList.remove('active-filter'));
      cell.classList.add('active-filter');

      const badge = document.getElementById('matrixActiveFilterBadge');
      const label = document.getElementById('activeCellLabel');
      badge.style.display = 'inline-flex';
      label.textContent = cellLabel;

      filterPlannerByCell(cof, pof);
    });
  });

  document.getElementById('clearMatrixFilterBtn')?.addEventListener('click', () => {
    document.querySelectorAll('.matrix-cell').forEach((c) => c.classList.remove('active-filter'));
    document.getElementById('matrixActiveFilterBadge').style.display = 'none';
    loadInspectionPlanner();
  });
}

async function filterPlannerByCell(cof, pof) {
  try {
    const res = await fetch('/api/v1/segments?limit=300');
    if (!res.ok) return;
    const all = await res.json();
    const matched = all.filter((s) => s.consequence_category === cof && s.pof_category === pof);

    const tbody = document.getElementById('inspectionPlannerBody');
    if (!tbody) return;

    if (matched.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 2rem; color: var(--text-muted);">No segments currently in Cell ${cof}${pof}.</td></tr>`;
      return;
    }

    tbody.innerHTML = matched
      .map((s, idx) => `
      <tr>
        <td class="font-mono text-muted">#${idx + 1}</td>
        <td class="font-mono" style="font-weight: 700; color: #fff;">${s.line_tag}</td>
        <td style="font-size: 0.78rem;">${s.area}</td>
        <td><span class="badge badge-priority">${s.risk_ranking}</span></td>
        <td class="font-mono">POF ${s.pof_category}</td>
        <td class="font-mono">Cat ${s.consequence_category}</td>
        <td class="font-mono" style="font-weight: 600;">${s.remaining_life_yr.toFixed(1)} yr</td>
        <td class="font-mono text-muted">${s.next_inspection_date}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="openSegmentInspector(${s.id})">Details</button>
        </td>
      </tr>
    `)
      .join('');
  } catch (e) {
    console.error('Cell filter error:', e);
  }
}

// ==========================================
// ISA-101 Alarms Console
// ==========================================
async function loadAlarms(statusFilter = '') {
  try {
    let url = '/api/v1/alarms?limit=150';
    if (statusFilter) url += `&status_filter=${statusFilter}`;

    const res = await fetch(url);
    if (!res.ok) throw new Error('Alarms load failed');
    const alarms = await res.json();
    state.alarms = alarms;

    const tbody = document.getElementById('alarmsTableBody');
    if (!tbody) return;

    if (alarms.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">No alarms matching current criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = alarms
      .map((a) => {
        const timeStr = new Date(a.created_at).toLocaleString();
        const sevClass =
          a.severity === 'CRITICAL'
            ? 'badge-critical'
            : a.severity === 'HIGH'
            ? 'badge-priority'
            : a.severity === 'MEDIUM'
            ? 'badge-watch'
            : 'badge-healthy';

        const statusClass =
          a.status === 'ACTIVE' ? 'badge-critical' : a.status === 'ACKNOWLEDGED' ? 'badge-watch' : 'badge-healthy';

        return `
        <tr>
          <td class="font-mono">#${a.id}</td>
          <td><span class="badge badge-alarm-${a.state}">State ${a.state}</span></td>
          <td><span class="badge ${sevClass}">${a.severity}</span></td>
          <td class="font-mono" style="font-weight: 700; color: #fff;">${a.line_tag || 'Segment ' + a.segment_id}</td>
          <td style="font-size: 0.78rem;">${a.area || 'Refinery Block 4'}</td>
          <td style="font-size: 0.82rem; max-width: 280px;">${a.trigger_reason}</td>
          <td><span class="badge ${statusClass}">${a.status}</span></td>
          <td class="text-muted" style="font-size: 0.72rem;">${timeStr}</td>
          <td style="font-size: 0.75rem;">
            ${a.acknowledged_by ? `<strong>${a.acknowledged_by.split('@')[0]}</strong>` : '<span class="text-muted">Unacknowledged</span>'}
          </td>
          <td>
            <div style="display: flex; gap: 0.4rem;">
              ${
                a.status === 'ACTIVE'
                  ? `<button class="btn btn-primary btn-sm" onclick="openAlarmAckModal(${a.id}, '${a.line_tag}', '${a.trigger_reason}')">Ack</button>`
                  : ''
              }
              ${
                a.status !== 'CLEARED'
                  ? `<button class="btn btn-secondary btn-sm" onclick="clearAlarm(${a.id})">Clear</button>`
                  : '<span class="text-muted" style="font-size: 0.72rem;">Closed</span>'
              }
            </div>
          </td>
        </tr>
      `;
      })
      .join('');
  } catch (err) {
    console.error('Alarms error:', err);
  }
}

// Alarm Acknowledgment (Two-Step ISA-101 Procedure)
let pendingAckAlarmId = null;

function openAlarmAckModal(alarmId, lineTag, triggerReason) {
  pendingAckAlarmId = alarmId;
  document.getElementById('alarmAckSubtitle').innerHTML = `
    Line: <strong class="text-cyan font-mono">${lineTag}</strong><br>
    Reason: <em>${triggerReason}</em>
  `;
  document.getElementById('ackNotesInput').value = '';
  document.getElementById('ackConfirmCheck').checked = false;
  document.getElementById('alarmAckModal').classList.add('open');
}

async function submitAlarmAck() {
  if (!pendingAckAlarmId) return;

  const confirmed = document.getElementById('ackConfirmCheck').checked;
  const notes = document.getElementById('ackNotesInput').value.trim();

  if (!confirmed) {
    showToast('Two-step operator confirmation check is mandatory (ISA-101)', 'error');
    return;
  }
  if (!notes) {
    showToast('Please provide operator verification notes', 'error');
    return;
  }

  try {
    const res = await fetch(`/api/v1/alarms/${pendingAckAlarmId}/acknowledge`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        ack_notes: notes,
        confirmed_by_operator: true
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Acknowledgment failed');
    }

    showToast(`Alarm #${pendingAckAlarmId} acknowledged and logged to audit trail`, 'success');
    document.getElementById('alarmAckModal').classList.remove('open');
    loadAlarms();
    loadKpis();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function clearAlarm(alarmId) {
  try {
    const res = await fetch(`/api/v1/alarms/${alarmId}/clear`, {
      method: 'POST',
      headers: getAuthHeaders()
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Clear failed');
    }

    showToast(`Alarm #${alarmId} cleared successfully`, 'success');
    loadAlarms();
    loadKpis();
    loadSegments();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ==========================================
// UT / PEC Calibration Studio
// ==========================================
async function loadCalibration() {
  try {
    // 1. Stats
    const statsRes = await fetch('/api/v1/calibration/stats');
    if (statsRes.ok) {
      const stats = await statsRes.json();
      document.getElementById('calibR2').textContent = stats.r2_score.toFixed(3);
      document.getElementById('calibBias').textContent = `${stats.bias_mm.toFixed(3)} mm`;
      document.getElementById('calibScatter').textContent = `${stats.scatter_mm.toFixed(3)} mm`;
      document.getElementById('calibPointsCount').textContent = stats.points_count;
    }

    // 2. Scatter Points
    const scatterRes = await fetch('/api/v1/calibration/scatter');
    if (scatterRes.ok) {
      const scatter = await scatterRes.json();
      state.calibrationScatter = scatter;
      renderCalibrationScatterChart(scatter);
    }

    // 3. Verification Digs Log
    const digsRes = await fetch('/api/v1/digs?limit=50');
    if (digsRes.ok) {
      const digs = await digsRes.json();
      state.digs = digs;
      renderDigsTable(digs);
    }

    // 4. Active Model Version Tag
    const verRes = await fetch('/api/v1/calibration/versions?limit=1');
    if (verRes.ok) {
      const vers = await verRes.json();
      if (vers.length > 0) {
        document.getElementById('activeModelTag').textContent = vers[0].version_tag;
      }
    }
  } catch (err) {
    console.error('Calibration error:', err);
  }
}

function renderCalibrationScatterChart(points) {
  const ctx = document.getElementById('calibrationScatterChart');
  if (!ctx) return;

  const dataPoints = points.map((p) => ({
    x: p.pec_predicted_wall_mm,
    y: p.ut_measured_wall_mm,
    tag: p.line_tag,
    delta: p.delta_mm
  }));

  if (state.charts.calibrationScatter) {
    state.charts.calibrationScatter.destroy();
  }

  state.charts.calibrationScatter = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: [
        {
          label: 'Verification Digs (PEC vs UT Ground Truth)',
          data: dataPoints,
          backgroundColor: '#06b6d4',
          borderColor: '#0891b2',
          pointRadius: 6,
          pointHoverRadius: 9
        },
        {
          label: 'Ideal 1:1 Parity Line',
          data: [
            { x: 3, y: 3 },
            { x: 14, y: 14 }
          ],
          type: 'line',
          borderColor: 'rgba(255, 255, 255, 0.4)',
          borderDash: [5, 5],
          pointRadius: 0,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          title: { display: true, text: 'Robotic PEC Predicted Wall Thickness (mm)', color: '#94a3b8' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#94a3b8' }
        },
        y: {
          title: { display: true, text: 'Ultrasonic (UT) Field Dig Measurement (mm)', color: '#94a3b8' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#94a3b8' }
        }
      },
      plugins: {
        legend: { labels: { color: '#cbd5e1' } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const raw = ctx.raw;
              if (raw.tag) {
                return `${raw.tag}: PEC ${raw.x}mm vs UT ${raw.y}mm (Δ: ${raw.delta}mm)`;
              }
              return 'Parity Line (x = y)';
            }
          }
        }
      }
    }
  });
}

function renderDigsTable(digs) {
  const tbody = document.getElementById('digsTableBody');
  if (!tbody) return;

  tbody.innerHTML = digs
    .map(
      (d) => `
    <tr>
      <td class="font-mono">#${d.id}</td>
      <td class="font-mono" style="font-weight: 700; color: #fff;">${d.line_tag || 'Segment ' + d.segment_id}</td>
      <td class="font-mono">${d.location_chainage_m.toFixed(1)} m</td>
      <td class="text-muted" style="font-size: 0.72rem;">${new Date(d.dig_date).toLocaleDateString()}</td>
      <td><span class="badge badge-watch">${d.insulation_condition}</span></td>
      <td style="font-size: 0.78rem;">${d.corrosion_severity}</td>
      <td class="font-mono">${d.pec_predicted_wall_mm.toFixed(2)}</td>
      <td class="font-mono" style="font-weight: 600; color: #34d399;">${d.ut_measured_wall_mm.toFixed(2)}</td>
      <td class="font-mono" style="color: ${Math.abs(d.delta_mm) > 0.4 ? '#f87171' : '#cbd5e1'};">
        ${d.delta_mm > 0 ? '+' : ''}${d.delta_mm.toFixed(3)}
      </td>
      <td><span class="badge badge-healthy">${d.status}</span></td>
    </tr>
  `
    )
    .join('');
}

// Record Verification Dig Form Submit
async function submitRecordDig() {
  const segId = parseInt(document.getElementById('digSegmentSelect').value, 10);
  const chainage = parseFloat(document.getElementById('digChainage').value);
  const insul = document.getElementById('digInsulation').value;
  const pec = parseFloat(document.getElementById('digPecVal').value);
  const ut = parseFloat(document.getElementById('digUtVal').value);
  const morphology = document.getElementById('digMorphology').value;
  const notes = document.getElementById('digNotes').value;

  try {
    const res = await fetch('/api/v1/digs', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        segment_id: segId,
        location_chainage_m: chainage,
        insulation_condition: insul,
        corrosion_severity: morphology,
        ut_measured_wall_mm: ut,
        pec_predicted_wall_mm: pec,
        inspector_notes: notes
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to record dig');
    }

    showToast('Verification dig recorded! Circuit model auto-calibrated.', 'success');
    document.getElementById('recordDigModal').classList.remove('open');
    loadCalibration();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ==========================================
// Work Orders Dispatch
// ==========================================
async function loadWorkOrders() {
  try {
    const statusFilter = document.getElementById('woStatusFilter')?.value || '';
    const prioFilter = document.getElementById('woPriorityFilter')?.value || '';

    let url = '/api/v1/work-orders?limit=150';
    if (statusFilter) url += `&status_filter=${statusFilter}`;
    if (prioFilter) url += `&priority=${prioFilter}`;

    const res = await fetch(url);
    if (!res.ok) throw new Error('Work orders load failed');
    const orders = await res.json();
    state.workOrders = orders;

    document.getElementById('tabWOCount').textContent = orders.length;

    const tbody = document.getElementById('workOrdersTableBody');
    if (!tbody) return;

    if (orders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">No maintenance work orders found.</td></tr>`;
      return;
    }

    tbody.innerHTML = orders
      .map((o) => {
        const timeStr = new Date(o.created_at).toLocaleDateString();
        const prioClass = o.priority === 'P1' ? 'badge-critical' : o.priority === 'P2' ? 'badge-priority' : 'badge-watch';

        return `
        <tr>
          <td class="font-mono" style="font-weight: 600;">${o.id}</td>
          <td><span class="badge ${prioClass}">${o.priority}</span></td>
          <td class="font-mono" style="font-weight: 700; color: #fff;">${o.line_tag || 'Segment ' + o.segment_id}</td>
          <td style="font-size: 0.78rem;">${o.area || 'Refinery Unit'}</td>
          <td style="font-size: 0.82rem; font-weight: 500;">${o.title}</td>
          <td style="font-size: 0.75rem;">${o.assigned_to || 'Unassigned'}</td>
          <td class="font-mono">$${(o.estimated_cost_usd || 0).toLocaleString()}</td>
          <td class="text-muted" style="font-size: 0.72rem;">${timeStr}</td>
          <td>
            <select class="form-select font-mono" style="padding: 2px 6px; font-size: 0.75rem;" onchange="updateWOStatus('${o.id}', this.value)">
              <option value="DRAFT" ${o.status === 'DRAFT' ? 'selected' : ''}>DRAFT</option>
              <option value="APPROVED" ${o.status === 'APPROVED' ? 'selected' : ''}>APPROVED</option>
              <option value="IN_PROGRESS" ${o.status === 'IN_PROGRESS' ? 'selected' : ''}>IN_PROGRESS</option>
              <option value="COMPLETED" ${o.status === 'COMPLETED' ? 'selected' : ''}>COMPLETED</option>
            </select>
          </td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="openSegmentInspector(${o.segment_id})">Line</button>
          </td>
        </tr>
      `;
      })
      .join('');
  } catch (err) {
    console.error('Work orders error:', err);
  }
}

async function updateWOStatus(woId, newStatus) {
  try {
    const res = await fetch(`/api/v1/work-orders/${woId}/status?new_status=${newStatus}`, {
      method: 'PATCH',
      headers: getAuthHeaders()
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Status update failed');
    }

    showToast(`Work order ${woId} updated to ${newStatus}`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function submitCreateWO() {
  const segId = parseInt(document.getElementById('woSegmentSelect').value, 10);
  const title = document.getElementById('woTitleInput').value.trim();
  const prio = document.getElementById('woPrioritySelect').value;
  const cost = parseFloat(document.getElementById('woCostInput').value) || 45000;
  const assigned = document.getElementById('woAssignedInput').value;
  const desc = document.getElementById('woDescInput').value;

  if (!title) {
    showToast('Please provide a work order title', 'error');
    return;
  }

  try {
    const res = await fetch('/api/v1/work-orders', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        segment_id: segId,
        title,
        priority: prio,
        estimated_cost_usd: cost,
        assigned_to: assigned,
        description: desc
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to dispatch work order');
    }

    showToast('Maintenance Work Order dispatched to turn-around queue', 'success');
    document.getElementById('createWOModal').classList.remove('open');
    loadWorkOrders();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ==========================================
// Financials & ROI Engine
// ==========================================
async function loadFinancials() {
  try {
    const baseline = parseFloat(document.getElementById('finBaseline').value) || 26800000;
    const capex = parseFloat(document.getElementById('finCapex').value) || 12513000;
    const opex = parseFloat(document.getElementById('finOpex').value) || 1850000;
    const discount = parseFloat(document.getElementById('finDiscount').value) || 0.08;
    const capture = (parseFloat(document.getElementById('finCapture').value) || 65) / 100.0;

    const res = await fetch('/api/v1/financials/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        baseline_annual_loss_usd: baseline,
        capex_usd: capex,
        opex_usd_yr: opex,
        discount_rate: discount,
        loss_reduction_pct: capture
      })
    });

    if (!res.ok) throw new Error('Financial calculation failed');
    const data = await res.json();
    state.financials = data;

    document.getElementById('finPayback').textContent = `${data.base_case_payback_years.toFixed(1)} yr`;
    const npvM = (data.base_case_5yr_npv_usd / 1000000).toFixed(1);
    document.getElementById('finNPV').textContent = `$${npvM}M`;

    // Render Sensitivity Scenarios
    const cardsList = document.getElementById('sensitivityCardsList');
    cardsList.innerHTML = (data.scenarios || [])
      .map(
        (s) => `
      <div class="kpi-card cyan" style="flex-direction: column; align-items: flex-start; gap: 0.4rem;">
        <div style="display: flex; justify-content: space-between; width: 100%; align-items: center;">
          <strong style="color: #fff; font-size: 0.85rem;">${s.scenario_name}</strong>
          <span class="badge badge-healthy font-mono">Capture: ${s.loss_reduction_pct}%</span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); width: 100%; font-size: 0.75rem; margin-top: 4px;">
          <div>Payback: <strong class="text-cyan">${s.payback_years} yrs</strong></div>
          <div>5-Yr NPV: <strong class="text-emerald">$${(s.npv_5yr_usd / 1000000).toFixed(1)}M</strong></div>
          <div>5-Yr Net: <strong class="text-emerald">$${(s.five_year_net_benefit_usd / 1000000).toFixed(1)}M</strong></div>
        </div>
      </div>
    `
      )
      .join('');
  } catch (err) {
    console.error('Financials error:', err);
  }
}

// ==========================================
// OPC-UA Mirror
// ==========================================
async function loadOPCUA() {
  try {
    const res = await fetch('/api/v1/opcua/browse?limit=30');
    if (!res.ok) throw new Error('OPC UA browse failed');
    const data = await res.json();

    const tbody = document.getElementById('opcuaNodesBody');
    if (!tbody) return;

    tbody.innerHTML = (data.nodes || [])
      .map(
        (n) => `
      <tr>
        <td style="font-weight: 500; color: #fff;">${n.displayName}</td>
        <td class="font-mono text-muted" style="font-size: 0.72rem;">${n.nodeId}</td>
        <td class="font-mono" style="font-weight: 600; color: var(--color-cyan);">${n.value}</td>
        <td class="font-mono text-muted">${n.engineeringUnits}</td>
        <td><span class="badge ${n.status === 'Good' ? 'badge-healthy' : 'badge-watch'}">${n.status}</span></td>
      </tr>
    `
      )
      .join('');
  } catch (err) {
    console.error('OPC UA error:', err);
  }
}

async function testReadOpcuaTag() {
  const path = document.getElementById('opcuaTagInput').value.trim();
  const box = document.getElementById('opcuaResponseBox');
  if (!path) return;

  try {
    box.textContent = 'Querying OPC UA Server Tag Mirror...';
    const res = await fetch(`/api/v1/opcua/read/${path}`);
    const data = await res.json();
    box.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    box.textContent = `Error reading tag: ${err.message}`;
  }
}

// ==========================================
// Scenario Sandbox Injection
// ==========================================
async function injectScenario(scenarioType) {
  try {
    showToast(`Injecting scenario: ${scenarioType.toUpperCase()}...`, 'info');
    const res = await fetch('/api/v1/scenarios/inject', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        scenario_type: scenarioType,
        severity: 1.0
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Injection failed');
    }

    const data = await res.json();
    showToast(data.message, 'success');
    document.getElementById('sandboxModal').classList.remove('open');

    // Refresh telemetry and registries
    loadKpis();
    loadSegments();
    loadAlarms();
    loadRiskMatrix();
    loadWorkOrders();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ==========================================
// Dropdowns and UI Wiring
// ==========================================
function populateSelectDropdowns(segments) {
  const woSelect = document.getElementById('woSegmentSelect');
  const digSelect = document.getElementById('digSegmentSelect');

  const options = segments
    .slice(0, 100)
    .map((s) => `<option value="${s.id}">${s.line_tag} (${s.area})</option>`)
    .join('');

  if (woSelect) woSelect.innerHTML = options;
  if (digSelect) digSelect.innerHTML = options;
}

function switchTab(tabId) {
  document.querySelectorAll('.nav-tab-btn').forEach((b) => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach((p) => p.classList.remove('active'));

  const btn = document.querySelector(`.nav-tab-btn[data-tab="${tabId}"]`);
  const pane = document.getElementById(tabId);

  if (btn) btn.classList.add('active');
  if (pane) pane.classList.add('active');
  state.activeTab = tabId;

  // Lazy load tab data
  if (tabId === 'tabRiskMatrix') loadRiskMatrix();
  if (tabId === 'tabAlarms') loadAlarms();
  if (tabId === 'tabCalibration') loadCalibration();
  if (tabId === 'tabWorkOrders') loadWorkOrders();
  if (tabId === 'tabFinancials') loadFinancials();
  if (tabId === 'tabOPCUA') loadOPCUA();
}

// ==========================================
// Application Bootstrap
// ==========================================
document.addEventListener('DOMContentLoaded', async () => {
  // 1. Initial Authentication (Default: Chief Engineer)
  await authenticatePersona('engineer');

  // 2. Persona Switcher Event
  document.getElementById('personaSelect')?.addEventListener('change', (e) => {
    authenticatePersona(e.target.value);
  });

  // 3. Navigation Tabs
  document.querySelectorAll('.nav-tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      switchTab(btn.getAttribute('data-tab'));
    });
  });

  // 4. Header Alarm Button -> Jumps to Alarms tab
  document.getElementById('headerAlarmBtn')?.addEventListener('click', () => {
    switchTab('tabAlarms');
  });

  // 5. Segments Filter Listeners
  document.getElementById('segSearchInput')?.addEventListener('input', filterAndRenderSegments);
  document.getElementById('areaFilter')?.addEventListener('change', filterAndRenderSegments);
  document.getElementById('healthFilter')?.addEventListener('change', filterAndRenderSegments);
  document.getElementById('riskFilter')?.addEventListener('change', filterAndRenderSegments);
  document.getElementById('resetSegFiltersBtn')?.addEventListener('click', () => {
    document.getElementById('segSearchInput').value = '';
    document.getElementById('areaFilter').value = '';
    document.getElementById('healthFilter').value = '';
    document.getElementById('riskFilter').value = '';
    filterAndRenderSegments();
  });

  // 6. Alarms Status Filter Buttons
  document.querySelectorAll('.alarm-status-filter').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.alarm-status-filter').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      loadAlarms(btn.getAttribute('data-status'));
    });
  });

  // 7. Modals Open / Close Wiring
  document.querySelectorAll('.modal-close-btn, .modal-close-btn-footer').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.modal-overlay').forEach((m) => m.classList.remove('open'));
    });
  });

  document.getElementById('openSandboxBtn')?.addEventListener('click', () => {
    document.getElementById('sandboxModal').classList.add('open');
  });

  document.getElementById('openCreateWOBtn')?.addEventListener('click', () => {
    document.getElementById('createWOModal').classList.add('open');
  });

  document.getElementById('openRecordDigBtn')?.addEventListener('click', () => {
    document.getElementById('recordDigModal').classList.add('open');
  });

  // 8. Form Submissions
  document.getElementById('submitAlarmAckBtn')?.addEventListener('click', submitAlarmAck);
  document.getElementById('submitCreateWOBtn')?.addEventListener('click', submitCreateWO);
  document.getElementById('submitRecordDigBtn')?.addEventListener('click', submitRecordDig);

  // 9. Financials Form Sliders & Recalc
  const captureSlider = document.getElementById('finCapture');
  const captureVal = document.getElementById('finCaptureVal');
  if (captureSlider && captureVal) {
    captureSlider.addEventListener('input', () => {
      captureVal.textContent = `${captureSlider.value}%`;
    });
  }
  document.getElementById('recalcFinancialsBtn')?.addEventListener('click', loadFinancials);

  // 10. Scenario Injections
  document.querySelectorAll('.btn-inject').forEach((btn) => {
    btn.addEventListener('click', () => {
      const type = btn.getAttribute('data-scenario');
      injectScenario(type);
    });
  });

  // 11. Work Orders Status and Priority Filters
  document.getElementById('woStatusFilter')?.addEventListener('change', loadWorkOrders);
  document.getElementById('woPriorityFilter')?.addEventListener('change', loadWorkOrders);

  // 12. OPC UA Direct Tag Reader
  document.getElementById('readOpcuaTagBtn')?.addEventListener('click', testReadOpcuaTag);

  // 13. Initialize Risk Matrix Listeners
  initMatrixListeners();

  // 14. Load Initial Data
  loadKpis();
  loadSegments();

  // 15. Connect Real-Time Telemetry WebSocket
  initWebSocket();
});
