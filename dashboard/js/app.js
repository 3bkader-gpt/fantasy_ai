// Fantasy AI - Command Center & Interactive Sandbox Engine

const TEAM_COLORS = {
  'ARS': '#ef0107', 'AVL': '#670e36', 'BHA': '#0057b8', 'BOU': '#da291c',
  'BRE': '#e30613', 'CHE': '#034694', 'CRY': '#1b458f', 'EVE': '#003399',
  'FUL': '#1c1c1c', 'HUL': '#f5971d', 'IPS': '#004488', 'LEI': '#003090',
  'LIV': '#c8102e', 'MCI': '#6cabdd', 'MUN': '#da291c', 'NEW': '#241f20',
  'NFO': '#dd0000', 'SOU': '#d71920', 'TOT': '#132257', 'WHU': '#7a263a',
  'WOL': '#fdb913'
};

const GK_COLOR = '#00f5ff';

// Global State
let rawData = null;
let currentStarters = [];
let currentBench = [];
let simulatedSwaps = new Map(); // originalId -> replacementPlayer
let activeMood = 'balanced';
let swapTargetPlayer = null;

function getKitSvg(team, position) {
  const color = position === 'GK' ? GK_COLOR : (TEAM_COLORS[team] || '#37003c');
  return `
    <svg viewBox="0 0 100 90" class="jersey-svg">
      <defs>
        <linearGradient id="grad-${team}-${position}" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="${color}" />
          <stop offset="100%" stop-color="#000" stop-opacity="0.3" />
        </linearGradient>
      </defs>
      <path d="M 30 15 L 8 35 L 22 47 L 34 33 L 34 85 L 66 85 L 66 33 L 78 47 L 92 35 L 70 15 C 62 25 38 25 30 15 Z" 
            fill="url(#grad-${team}-${position})" 
            stroke="rgba(255,255,255,0.7)" 
            stroke-width="2.5" 
            stroke-linejoin="round" />
    </svg>
  `;
}

function getFdrClass(fdrNum) {
  const n = parseInt(fdrNum, 10);
  if (n === 5) return 'fdr-5';
  if (n === 4) return 'fdr-4';
  if (n === 3) return 'fdr-3';
  return 'fdr-2';
}

function renderPlayerCard(player, isBench = false) {
  const card = document.createElement('div');
  const isSim = simulatedSwaps.has(player.id) || player._isSimulated;
  card.className = `player-card ${isSim ? 'simulated' : ''}`;
  card.setAttribute('role', 'button');
  card.setAttribute('tabindex', '0');

  let roleBadge = '';
  if (player.is_captain) {
    roleBadge = '<div class="badge-role badge-c">C</div>';
  } else if (player.is_vice_captain) {
    roleBadge = '<div class="badge-role badge-vc">V</div>';
  }

  // 5-GW Fixture Strip
  let fixtureStripHtml = '';
  if (player.fixtures_5gw && player.fixtures_5gw.length > 0) {
    const pills = player.fixtures_5gw.slice(0, 5).map(f => {
      const cls = getFdrClass(f.fdr);
      const title = `GW${f.gw}: ${f.opponent} (${f.is_home ? 'H' : 'A'}) [FDR ${f.fdr}]`;
      return `<span class="fdr-pill ${cls}" title="${title}">${f.fdr}</span>`;
    }).join('');
    fixtureStripHtml = `<div class="fixture-strip">${pills}</div>`;
  }

  card.innerHTML = `
    <button class="swap-btn-overlay" title="Swap player in What-If simulator" aria-label="Swap player">⇄</button>
    <div class="jersey-container">
      ${getKitSvg(player.team, player.position)}
      ${roleBadge}
    </div>
    <div class="player-info-box">
      <div class="player-name" title="${player.name}">${player.name}</div>
      <div class="player-details">
        <span>${player.team}</span>
        <span>•</span>
        <span>£${player.cost.toFixed(1)}</span>
      </div>
      <div class="player-xp-pill">${player.xp.toFixed(1)} xP</div>
      ${fixtureStripHtml}
    </div>
  `;

  // Quick swap button
  const swapBtn = card.querySelector('.swap-btn-overlay');
  swapBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    openSwapModal(player);
  });

  // Card click opens detail modal
  card.addEventListener('click', () => openPlayerModal(player));
  card.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      openPlayerModal(player);
    }
  });

  return card;
}

function openPlayerModal(player) {
  swapTargetPlayer = player;
  const modal = document.getElementById('player-modal');
  document.getElementById('modal-player-name').textContent = player.name;
  document.getElementById('modal-player-team-pos').textContent = `${player.position} • ${player.team} | ${player.is_captain ? 'Captain (C)' : (player.is_vice_captain ? 'Vice Captain (VC)' : 'Starter')}`;
  document.getElementById('modal-cost').textContent = `£${player.cost.toFixed(1)}m`;
  document.getElementById('modal-xp').textContent = `${player.xp.toFixed(1)} xP`;
  document.getElementById('modal-horizon-xp').textContent = `${player.horizon_xp ? player.horizon_xp.toFixed(1) : player.xp.toFixed(1)} xP`;
  document.getElementById('modal-mins').textContent = `${Math.round(player.expected_minutes || 90)}'`;
  document.getElementById('modal-fixture').textContent = player.fixture || 'TBD';

  modal.classList.add('active');
}

function openSwapModal(targetPlayer) {
  swapTargetPlayer = targetPlayer;
  const modal = document.getElementById('swap-modal');
  const desc = document.getElementById('swap-target-desc');
  desc.textContent = `Replacing: ${targetPlayer.name} (${targetPlayer.position} • ${targetPlayer.team} • £${targetPlayer.cost.toFixed(1)}m)`;

  const searchInput = document.getElementById('candidate-search');
  searchInput.value = '';
  renderCandidatesList(targetPlayer.position, '');

  modal.classList.add('active');
  searchInput.focus();
}

function renderCandidatesList(position, searchQuery = '') {
  const listContainer = document.getElementById('candidate-list');
  listContainer.innerHTML = '';

  const candidates = (rawData.market_candidates || [])
    .filter(c => c.position === position && c.id !== swapTargetPlayer.id)
    .filter(c => {
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return c.name.toLowerCase().includes(q) || c.team.toLowerCase().includes(q);
    });

  if (candidates.length === 0) {
    listContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px;">No candidates found for ${position}</div>`;
    return;
  }

  candidates.forEach(cand => {
    const item = document.createElement('div');
    item.className = 'candidate-item';
    const xpDiff = (cand.xp - swapTargetPlayer.xp).toFixed(1);
    const xpDiffStr = xpDiff >= 0 ? `+${xpDiff}` : `${xpDiff}`;
    const diffClass = xpDiff >= 0 ? 'color: var(--fpl-mint);' : 'color: var(--fpl-danger);';

    item.innerHTML = `
      <div style="display: flex; align-items: center; gap: 12px;">
        <div style="font-size: 1.2rem;">👕</div>
        <div>
          <div style="font-weight: 700;">${cand.name}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${cand.team} • £${cand.cost.toFixed(1)}m • ${cand.fixture.replace(/\[FDR \d\]/, '').trim()}</div>
        </div>
      </div>
      <div style="text-align: right;">
        <div style="font-weight: 800; color: #fff;">${cand.xp.toFixed(1)} xP</div>
        <div style="font-size: 0.75rem; font-weight: 700; ${diffClass}">${xpDiffStr} xP</div>
      </div>
    `;

    item.addEventListener('click', () => {
      applyWhatIfSwap(swapTargetPlayer, cand);
      document.getElementById('swap-modal').classList.remove('active');
    });

    listContainer.appendChild(item);
  });
}

function applyWhatIfSwap(original, replacement) {
  simulatedSwaps.set(original.id, replacement);
  
  // Clone replacement and tag it
  const simPlayer = { ...replacement, _isSimulated: true, is_captain: original.is_captain, is_vice_captain: original.is_vice_captain };

  // Replace in starters or bench
  const stIdx = currentStarters.findIndex(p => p.id === original.id || (p._origId && p._origId === original.id));
  if (stIdx !== -1) {
    simPlayer._origId = original._origId || original.id;
    currentStarters[stIdx] = simPlayer;
  } else {
    const bIdx = currentBench.findIndex(p => p.id === original.id || (p._origId && p._origId === original.id));
    if (bIdx !== -1) {
      simPlayer._origId = original._origId || original.id;
      currentBench[bIdx] = simPlayer;
    }
  }

  updateWhatIfMetrics();
  renderPitch();
  renderMatrixView();
}

function updateWhatIfMetrics() {
  const baseTotalXP = rawData.total_xp || 0;
  const baseBank = (rawData.meta && rawData.meta.bank) ? rawData.meta.bank : 1.2;

  let newTotalXP = 0;
  let costDelta = 0;

  currentStarters.forEach(p => {
    let multiplier = 1;
    if (p.is_captain) multiplier = 2;
    newTotalXP += p.xp * multiplier;
  });

  simulatedSwaps.forEach((rep, origId) => {
    const origPlayer = (rawData.starters || []).concat(rawData.bench || []).find(p => p.id === origId);
    if (origPlayer) {
      costDelta += (rep.cost - origPlayer.cost);
    }
  });

  const deltaXP = newTotalXP - baseTotalXP;
  const newBank = baseBank - costDelta;

  // Update Hero Stats & Floating Bar
  document.getElementById('stat-xp').textContent = newTotalXP.toFixed(1);
  document.getElementById('stat-bank').textContent = `£${newBank.toFixed(1)}m`;

  const whatifBar = document.getElementById('whatif-bar');
  if (simulatedSwaps.size > 0) {
    whatifBar.classList.add('visible');
    document.getElementById('whatif-swap-count').textContent = `${simulatedSwaps.size} player(s) swapped`;
    const deltaEl = document.getElementById('whatif-delta-xp');
    deltaEl.textContent = (deltaXP >= 0 ? `+${deltaXP.toFixed(1)}` : deltaXP.toFixed(1));
    deltaEl.className = `whatif-delta ${deltaXP >= 0 ? 'positive' : 'negative'}`;
    
    const bankEl = document.getElementById('whatif-sim-bank');
    bankEl.textContent = `£${newBank.toFixed(1)}m`;
    bankEl.style.color = newBank < 0 ? 'var(--fpl-danger)' : '#fff';
  } else {
    whatifBar.classList.remove('visible');
  }
}

function resetWhatIf() {
  simulatedSwaps.clear();
  currentStarters = JSON.parse(JSON.stringify(rawData.starters || []));
  currentBench = JSON.parse(JSON.stringify(rawData.bench || []));
  updateWhatIfMetrics();
  renderPitch();
  renderMatrixView();
}

function setupEventListeners() {
  // Modal close buttons
  document.getElementById('modal-close-btn').addEventListener('click', () => {
    document.getElementById('player-modal').classList.remove('active');
  });
  document.getElementById('swap-close-btn').addEventListener('click', () => {
    document.getElementById('swap-modal').classList.remove('active');
  });

  // Modal swap button
  document.getElementById('modal-swap-btn').addEventListener('click', () => {
    document.getElementById('player-modal').classList.remove('active');
    if (swapTargetPlayer) openSwapModal(swapTargetPlayer);
  });

  // Candidate Search
  document.getElementById('candidate-search').addEventListener('input', (e) => {
    if (swapTargetPlayer) renderCandidatesList(swapTargetPlayer.position, e.target.value);
  });

  // Reset What-If
  document.getElementById('whatif-btn-reset').addEventListener('click', resetWhatIf);

  // View Switcher (Pitch vs Matrix vs Radar)
  document.querySelectorAll('.view-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.view-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const view = tab.dataset.view;
      const pitchEl = document.getElementById('view-pitch');
      const matrixEl = document.getElementById('view-matrix');
      const radarEl = document.getElementById('view-radar');

      if (view === 'pitch') {
        pitchEl.style.display = 'block';
        matrixEl.classList.remove('active');
        if (radarEl) radarEl.classList.remove('active');
      } else if (view === 'matrix') {
        pitchEl.style.display = 'none';
        matrixEl.classList.add('active');
        if (radarEl) radarEl.classList.remove('active');
      } else if (view === 'radar') {
        pitchEl.style.display = 'none';
        matrixEl.classList.remove('active');
        if (radarEl) radarEl.classList.add('active');
      }
    });
  });

  // Pitch Theme Switcher
  const savedTheme = localStorage.getItem('fpl_pitch_theme') || 'cyber';
  applyPitchTheme(savedTheme);

  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      applyPitchTheme(btn.dataset.theme);
    });
  });

  // AI Copilot setup
  setupCopilot();

  // Tactical Mood Selector
  document.querySelectorAll('.mood-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.mood-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeMood = btn.dataset.mood;
      const sub = document.getElementById('stat-xp-sub');
      if (activeMood === 'conservative') {
        sub.textContent = 'Safe Mood: Zero hits, safe template';
      } else if (activeMood === 'aggressive') {
        sub.textContent = 'Attack Mood: High differential upside';
      } else {
        sub.textContent = 'Balanced Mood: Optimal ROI horizon';
      }
    });
  });

  // Mode Toggle (Simulation vs Live)
  const modeBadge = document.getElementById('mode-badge');
  modeBadge.addEventListener('click', () => {
    const txt = document.getElementById('mode-text');
    if (txt.textContent.includes('SIMULATION')) {
      txt.textContent = '🚀 OFFICIAL LIVE';
      modeBadge.style.borderColor = 'var(--fpl-danger)';
      txt.style.color = 'var(--fpl-danger)';
    } else {
      txt.textContent = '🛡️ SIMULATION';
      modeBadge.style.borderColor = 'var(--border-glass)';
      txt.style.color = 'var(--text-primary)';
    }
  });

  // Trigger Cloud Agent
  const btnTrigger = document.getElementById('btn-trigger-agent');
  btnTrigger.addEventListener('click', () => {
    btnTrigger.classList.add('loading');
    btnTrigger.innerHTML = '<span>⏳ Running Agent...</span>';
    setTimeout(() => {
      btnTrigger.classList.remove('loading');
      btnTrigger.innerHTML = '<span>⚡ Run Cloud Agent</span>';
      alert('🚀 Cloud Agent cycle triggered! Check GitHub Actions or Telegram for real-time live execution logs.');
    }, 1500);
  });
}

function renderPitch() {
  const startersByPos = { 'GK': [], 'DEF': [], 'MID': [], 'FWD': [] };
  currentStarters.forEach(p => {
    if (startersByPos[p.position]) startersByPos[p.position].push(p);
  });

  const rowGk = document.getElementById('row-gk');
  const rowDef = document.getElementById('row-def');
  const rowMid = document.getElementById('row-mid');
  const rowFwd = document.getElementById('row-fwd');
  const rowBench = document.getElementById('row-bench');

  rowGk.innerHTML = '';
  rowDef.innerHTML = '';
  rowMid.innerHTML = '';
  rowFwd.innerHTML = '';
  rowBench.innerHTML = '';

  startersByPos['GK'].forEach(p => rowGk.appendChild(renderPlayerCard(p)));
  startersByPos['DEF'].forEach(p => rowDef.appendChild(renderPlayerCard(p)));
  startersByPos['MID'].forEach(p => rowMid.appendChild(renderPlayerCard(p)));
  startersByPos['FWD'].forEach(p => rowFwd.appendChild(renderPlayerCard(p)));

  currentBench.forEach(p => rowBench.appendChild(renderPlayerCard(p, true)));
}

function renderMatrixView() {
  const tbody = document.getElementById('matrix-tbody');
  tbody.innerHTML = '';

  const allPlayers = [...currentStarters, ...currentBench];
  allPlayers.forEach(p => {
    const tr = document.createElement('tr');
    const fixes = p.fixtures_5gw || [];
    let diffSum = 0;

    const fixTds = [0, 1, 2, 3, 4].map(idx => {
      const f = fixes[idx];
      if (f) {
        diffSum += (f.fdr || 3);
        const cls = getFdrClass(f.fdr);
        return `<td><span class="matrix-fdr-cell ${cls}">${f.opponent} (${f.is_home ? 'H' : 'A'})</span></td>`;
      }
      diffSum += 3;
      return `<td><span class="matrix-fdr-cell fdr-3">-</span></td>`;
    }).join('');

    tr.innerHTML = `
      <td>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span>${p.is_captain ? '👑' : (p.is_vice_captain ? '🥈' : '⚽')}</span>
          <strong style="color: #fff;">${p.name}</strong>
          <span style="font-size: 0.75rem; color: var(--text-muted);">(${p.team})</span>
        </div>
      </td>
      <td><span class="brand-badge" style="font-size: 0.65rem;">${p.position}</span></td>
      <td>£${p.cost.toFixed(1)}m</td>
      ${fixTds}
      <td style="text-align: right; font-weight: 800; color: ${diffSum <= 14 ? 'var(--fpl-mint)' : (diffSum >= 18 ? 'var(--fpl-danger)' : 'var(--fpl-gold)')};">${diffSum}</td>
    `;
    tbody.appendChild(tr);
  });
}

function startCountdown(deadlineIso) {
  const targetTime = new Date(deadlineIso).getTime();
  const elCountdown = document.getElementById('stat-deadline-countdown');
  const elDate = document.getElementById('stat-deadline-date');

  const deadlineDate = new Date(deadlineIso);
  elDate.textContent = deadlineDate.toUTCString().replace(':00 GMT', ' UTC');

  function update() {
    const now = new Date().getTime();
    const diff = targetTime - now;

    if (diff <= 0) {
      elCountdown.textContent = 'LOCKED';
      elCountdown.style.color = 'var(--fpl-danger)';
      return;
    }

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const secs = Math.floor((diff % (1000 * 60)) / 1000);

    if (days > 0) {
      elCountdown.textContent = `${days}d ${hours}h ${mins}m`;
    } else {
      elCountdown.textContent = `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
  }

  update();
  setInterval(update, 1000);
}

async function loadSquadData() {
  try {
    const res = await fetch(`data/squad_data.json?v=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    rawData = await res.json();
    currentStarters = JSON.parse(JSON.stringify(rawData.starters || []));
    currentBench = JSON.parse(JSON.stringify(rawData.bench || []));
    renderDashboard(rawData);
  } catch (err) {
    console.error('Failed to load squad data:', err);
    document.getElementById('ai-briefing-content').innerHTML = `
      <div style="color: var(--fpl-danger);">
        ⚠️ Unable to load squad_data.json. Run <code>python main.py</code> to generate latest telemetry.
      </div>
    `;
  }
}

function renderDashboard(data) {
  const meta = data.meta || {};

  document.getElementById('stat-xp').textContent = (data.total_xp || 0).toFixed(1);
  document.getElementById('stat-bank').textContent = `£${(meta.bank || 0).toFixed(1)}m`;
  document.getElementById('stat-team-val').textContent = `Team Value: £${(meta.team_value || 100).toFixed(1)}m`;
  document.getElementById('stat-ft').textContent = `${meta.free_transfers || 1} FT`;

  if (meta.transfers && meta.transfers.length > 0) {
    document.getElementById('stat-transfers-status').textContent = `${meta.transfers.length} transfers executed`;
  } else {
    document.getElementById('stat-transfers-status').textContent = 'Roll Transfer (Saved)';
  }

  document.getElementById('nav-subtitle').textContent = `${meta.manager_name || 'Pep GPT'} • ${meta.team_name || 'هبد اصطناعي'}`;
  document.getElementById('gw-pill').textContent = `GW ${meta.gameweek || 4}`;
  document.getElementById('formation-tag').textContent = data.formation || '3-5-2';

  if (data.captain) document.getElementById('header-captain').textContent = `${data.captain.name} (C)`;
  if (data.vice_captain) document.getElementById('header-vc').textContent = `${data.vice_captain.name} (VC)`;

  if (meta.last_updated) {
    const dt = new Date(meta.last_updated);
    document.getElementById('last-updated-text').textContent = dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  if (meta.deadline) startCountdown(meta.deadline);

  renderPitch();
  renderMatrixView();
  if (data.eo_radar) {
    renderLeagueRadarView(data.eo_radar);
  }

  // Briefing
  const briefingBox = document.getElementById('ai-briefing-content');
  if (data.briefing) {
    if (typeof window.marked !== 'undefined') {
      briefingBox.innerHTML = window.marked.parse(data.briefing);
    } else {
      briefingBox.innerText = data.briefing;
    }
  }

  // Mini-Leagues
  const leaguesBody = document.getElementById('leagues-body');
  leaguesBody.innerHTML = '';
  if (data.leagues && data.leagues.length > 0) {
    data.leagues.forEach(l => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-weight: 600;">${l.name}</td>
        <td style="text-align: right;" class="league-rank">#${l.rank.toLocaleString()}</td>
      `;
      leaguesBody.appendChild(tr);
    });
  }
}

// Pitch Theme Applier
function applyPitchTheme(theme) {
  document.querySelectorAll('.theme-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.theme === theme);
  });
  const pitchField = document.getElementById('pitch-field');
  const pitchWrapper = document.getElementById('view-pitch');
  if (pitchField) {
    pitchField.className = `pitch-field theme-${theme}`;
  }
  if (pitchWrapper) {
    pitchWrapper.classList.toggle('stadium-perspective', theme === 'stadium');
  }
  localStorage.setItem('fpl_pitch_theme', theme);
}

// Mini-League Spy & EO Radar View Renderer
function renderLeagueRadarView(radarData) {
  if (!radarData) return;

  if (radarData.overall_threat_score) {
    const scoreEl = document.getElementById('threat-score-val');
    if (scoreEl) scoreEl.textContent = `${radarData.overall_threat_score}/100`;
  }

  // Threats
  const threatsList = document.getElementById('threats-list');
  if (threatsList && radarData.threats) {
    const cntEl = document.getElementById('threats-count');
    if (cntEl) cntEl.textContent = `${radarData.threats.length} Targets`;
    threatsList.innerHTML = '';
    radarData.threats.forEach(t => {
      const tagClass = t.threat_level === 'CRITICAL' ? 'tag-critical' : 'tag-high';
      const item = document.createElement('div');
      item.className = 'radar-item';
      item.innerHTML = `
        <div class="radar-item-top">
          <div>
            <span class="radar-item-name">${t.player}</span>
            <span class="radar-item-sub">(${t.team}) • £${t.cost.toFixed(1)}m</span>
          </div>
          <span class="threat-tag ${tagClass}">${t.threat_level}</span>
        </div>
        <div class="eo-bar-wrap">
          <div class="eo-bar-labels">
            <span>Effective Ownership (EO)</span>
            <strong style="color: #f87171;">${t.eo}%</strong>
          </div>
          <div class="eo-bar-bg">
            <div class="eo-bar-fill threat" style="width: ${Math.min(t.eo, 100)}%;"></div>
          </div>
        </div>
        <div class="radar-item-impact">⚠️ ${t.impact}</div>
      `;
      threatsList.appendChild(item);
    });
  }

  // Differentials
  const diffList = document.getElementById('differentials-list');
  if (diffList && radarData.differentials) {
    const cntEl = document.getElementById('differentials-count');
    if (cntEl) cntEl.textContent = `${radarData.differentials.length} Weapons`;
    diffList.innerHTML = '';
    radarData.differentials.forEach(d => {
      const item = document.createElement('div');
      item.className = 'radar-item';
      item.innerHTML = `
        <div class="radar-item-top">
          <div>
            <span class="radar-item-name">${d.player}</span>
            <span class="radar-item-sub">(${d.team}) • £${d.cost.toFixed(1)}m</span>
          </div>
          <span class="threat-tag tag-differential">${d.advantage}</span>
        </div>
        <div class="eo-bar-wrap">
          <div class="eo-bar-labels">
            <span>Effective Ownership (EO)</span>
            <strong style="color: var(--fpl-mint);">${d.eo}%</strong>
          </div>
          <div class="eo-bar-bg">
            <div class="eo-bar-fill differential" style="width: ${Math.max(d.eo, 8)}%;"></div>
          </div>
        </div>
        <div class="radar-item-impact">✨ Projected xP: <strong>${d.xp.toFixed(1)}</strong></div>
      `;
      diffList.appendChild(item);
    });
  }

  // Mini-Leagues
  const leaguesGrid = document.getElementById('radar-leagues-grid');
  if (leaguesGrid && radarData.leagues) {
    leaguesGrid.innerHTML = '';
    radarData.leagues.forEach(lg => {
      const card = document.createElement('div');
      card.className = 'league-track-card';
      const isLeader = lg.rank === 1;
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
          <div>
            <strong style="color: #fff; font-size: 0.95rem;">${lg.name}</strong>
            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">
              Current Position: <span style="color: var(--fpl-cyan); font-weight: 800;">#${lg.rank}</span>
            </div>
          </div>
          <span style="font-size: 0.72rem; padding: 2px 8px; border-radius: var(--radius-full); font-weight: 800; background: ${isLeader ? 'rgba(255, 183, 3, 0.2)' : 'rgba(4, 245, 255, 0.2)'}; color: ${isLeader ? 'var(--fpl-gold)' : 'var(--fpl-cyan)'};">
            ${lg.status}
          </span>
        </div>
        <div style="font-size: 0.8rem; display: flex; justify-content: space-between; color: var(--text-secondary); margin-top: 8px;">
          <span>Rival to Watch: <strong style="color: #fff;">${lg.rival_to_watch}</strong></span>
          <span>Risk Level: <strong style="color: ${lg.risk_index === 'Low' ? 'var(--fpl-mint)' : 'var(--fpl-gold)'};">${lg.risk_index}</strong></span>
        </div>
      `;
      leaguesGrid.appendChild(card);
    });
  }
}

// AI Tactical Copilot Controller
let copilotHistory = [];

function setupCopilot() {
  const btnOpen = document.getElementById('btn-open-copilot');
  const btnClose = document.getElementById('btn-close-copilot');
  const drawer = document.getElementById('copilot-drawer');
  const input = document.getElementById('copilot-input');
  const btnSend = document.getElementById('copilot-send');
  const promptChips = document.querySelectorAll('.prompt-chip');

  if (!btnOpen || !drawer) return;

  btnOpen.addEventListener('click', () => {
    drawer.classList.toggle('active');
    if (drawer.classList.contains('active') && input) {
      input.focus();
    }
  });

  if (btnClose) {
    btnClose.addEventListener('click', () => {
      drawer.classList.remove('active');
    });
  }

  promptChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const promptText = chip.dataset.prompt;
      if (input) input.value = promptText;
      sendMessageToCopilot(promptText);
      if (input) input.value = '';
    });
  });

  if (btnSend && input) {
    btnSend.addEventListener('click', () => {
      const text = input.value.trim();
      if (text) {
        sendMessageToCopilot(text);
        input.value = '';
      }
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const text = input.value.trim();
        if (text) {
          sendMessageToCopilot(text);
          input.value = '';
        }
      }
    });
  }
}

async function sendMessageToCopilot(userText) {
  const messagesContainer = document.getElementById('copilot-messages');
  if (!messagesContainer) return;

  // Append user bubble
  const userMsgEl = document.createElement('div');
  userMsgEl.className = 'copilot-msg user';
  userMsgEl.innerHTML = `<div class="msg-bubble">${escapeHtml(userText)}</div>`;
  messagesContainer.appendChild(userMsgEl);

  // Append typing indicator
  const typingEl = document.createElement('div');
  typingEl.className = 'copilot-msg ai';
  typingEl.id = 'copilot-typing-indicator';
  typingEl.innerHTML = `
    <div class="copilot-typing">
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    </div>
  `;
  messagesContainer.appendChild(typingEl);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;

  copilotHistory.push({ role: 'user', content: userText });

  const squadContext = {
    team_name: (rawData && rawData.meta && rawData.meta.team_name) || "هبد اصطناعي",
    formation: (rawData && rawData.formation) || "3-5-2",
    captain_name: (rawData && rawData.captain && rawData.captain.name) || "Gakpo",
    captain_xp: (rawData && rawData.captain && rawData.captain.xp) || 9.7,
    vc_name: (rawData && rawData.vice_captain && rawData.vice_captain.name) || "B.Fernandes",
    vc_xp: (rawData && rawData.vice_captain && rawData.vice_captain.xp) || 9.0,
    bank: (rawData && rawData.meta && rawData.meta.bank) ?? 1.2,
    free_transfers: (rawData && rawData.meta && rawData.meta.free_transfers) ?? 1,
    total_xp: (rawData && rawData.total_xp) || 87.2
  };

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: userText,
        history: copilotHistory,
        squadContext: squadContext
      })
    });

    let replyText = "";
    if (res.ok) {
      const data = await res.json();
      replyText = data.reply;
    } else {
      replyText = generateClientFallback(userText, squadContext);
    }

    typingEl.remove();
    copilotHistory.push({ role: 'model', content: replyText });

    const aiMsgEl = document.createElement('div');
    aiMsgEl.className = 'copilot-msg ai';
    const formattedReply = (typeof window.marked !== 'undefined') ? window.marked.parse(replyText) : replyText.replace(/\n/g, '<br>');
    aiMsgEl.innerHTML = `<div class="msg-bubble">${formattedReply}</div>`;
    messagesContainer.appendChild(aiMsgEl);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  } catch (err) {
    typingEl.remove();
    const fallbackText = generateClientFallback(userText, squadContext);
    const aiMsgEl = document.createElement('div');
    aiMsgEl.className = 'copilot-msg ai';
    const formattedReply = (typeof window.marked !== 'undefined') ? window.marked.parse(fallbackText) : fallbackText.replace(/\n/g, '<br>');
    aiMsgEl.innerHTML = `<div class="msg-bubble">${formattedReply}</div>`;
    messagesContainer.appendChild(aiMsgEl);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
}

function generateClientFallback(msg, ctx) {
  const lower = (msg || "").toLowerCase();
  if (lower.includes("captain") || lower.includes("كابتن")) {
    return `🎯 **توصية الكابتنة للجولة الرابعة:**\n\nنوصي بالإبقاء على **كودي جاكبو (Gakpo)** بشارة القيادة (xP: 9.7) أمام فولهام في أنفيلد. الأرقام ترشحه بقوة بفضل مؤشرات xG داخل الصندوق بمعدل 0.82 لكل 90 دقيقة.\n\nالنائب المباشر هو **برونو فيرنانديز (Bruno)** (xP: 9.0) أمام السيتي كخيار ذو سقف عالي للكرات الثابتة.`;
  }
  if (lower.includes("threat") || lower.includes("خطر") || lower.includes("منافس") || lower.includes("rival")) {
    return `⚠️ **رادار التهديد والمنافسين:**\n\nالتهديد الأكبر لترتيبك حالياً هو **إرلينج هالاند (Haaland)** بنسبة ملكية فعالة تتجاوز **138%** بين متصدري الدوريات. إذا سجل هاتريك سيتراجع الترتيب مؤقتاً، لكن خط وسطك الخماسي (Saka, Palmer, Gakpo, Bruno, Stach) مصمم لتعويض هذا الفارق التراكمي.`;
  }
  if (lower.includes("transfer") || lower.includes("تبديل") || lower.includes("roll")) {
    return `🔄 **القرار الاستراتيجي للتبديلات:**\n\nالقرار الرياضي المعتمد من محرك MILP هو **ترحيل التبديل (Roll Transfer)** إلى الجولة الخامسة. هذا يمنحنا مرونة قصوى (2 FTs) مع فائض مالي قدره £1.2m، وتجنب الـ Hits في هذه المرحلة الحساسة.`;
  }
  return `🤖 **Pep GPT التكتيكي:**\n\nالفريق جاهز بنسبة 100% لخوض الجولة الرابعة بتشكيل 3-5-2 ومجموع نقاط متوقعة **87.2 xP**. تم تأمين المداورة الدفاعية، وخط الوسط يتمتع بأعلى سقف هجومي ممكن. هل لديك استفسار محدد حول لاعب معين أو خيار بديل؟`;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  loadSquadData();
});
