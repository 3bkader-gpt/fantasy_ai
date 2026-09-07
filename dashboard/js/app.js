// Fantasy AI - Cloudflare Pages Dashboard Engine

const TEAM_COLORS = {
  'ARS': '#ef0107',
  'AVL': '#670e36',
  'BHA': '#0057b8',
  'BOU': '#da291c',
  'BRE': '#e30613',
  'CHE': '#034694',
  'CRY': '#1b458f',
  'EVE': '#003399',
  'FUL': '#1c1c1c',
  'HUL': '#f5971d',
  'IPS': '#004488',
  'LEI': '#003090',
  'LIV': '#c8102e',
  'MCI': '#6cabdd',
  'MUN': '#da291c',
  'NEW': '#241f20',
  'NFO': '#dd0000',
  'SOU': '#d71920',
  'TOT': '#132257',
  'WHU': '#7a263a',
  'WOL': '#fdb913'
};

const GK_COLOR = '#00f5ff';

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

function getFdrClass(fixtureStr) {
  if (!fixtureStr) return 'fdr-2';
  if (fixtureStr.includes('[FDR 5]')) return 'fdr-5';
  if (fixtureStr.includes('[FDR 4]')) return 'fdr-4';
  if (fixtureStr.includes('[FDR 3]')) return 'fdr-3';
  return 'fdr-2';
}

function renderPlayerCard(player) {
  const card = document.createElement('div');
  card.className = 'player-card';
  card.setAttribute('role', 'button');
  card.setAttribute('tabindex', '0');

  let roleBadge = '';
  if (player.is_captain) {
    roleBadge = '<div class="badge-role badge-c">C</div>';
  } else if (player.is_vice_captain) {
    roleBadge = '<div class="badge-role badge-vc">V</div>';
  }

  const fdrClass = getFdrClass(player.fixture);

  card.innerHTML = `
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
      <div class="fdr-badge ${fdrClass}">${player.fixture.replace(/\[FDR \d\]/, '').trim()}</div>
    </div>
  `;

  card.addEventListener('click', () => openPlayerModal(player));
  card.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      openPlayerModal(player);
    }
  });

  return card;
}

function openPlayerModal(player) {
  const modal = document.getElementById('player-modal');
  document.getElementById('modal-player-name').textContent = player.name;
  document.getElementById('modal-player-team-pos').textContent = `${player.position} • ${player.team} | ${player.is_captain ? 'Captain (C)' : (player.is_vice_captain ? 'Vice Captain (VC)' : 'Starter')}`;
  document.getElementById('modal-cost').textContent = `£${player.cost.toFixed(1)}m`;
  document.getElementById('modal-xp').textContent = `${player.xp.toFixed(1)} xP`;
  document.getElementById('modal-horizon-xp').textContent = `${player.horizon_xp ? player.horizon_xp.toFixed(1) : player.xp.toFixed(1)} xP`;
  document.getElementById('modal-mins').textContent = `${Math.round(player.expected_minutes || 90)}'`;
  document.getElementById('modal-fixture').textContent = player.fixture;

  modal.classList.add('active');
}

function setupModal() {
  const modal = document.getElementById('player-modal');
  const closeBtn = document.getElementById('modal-close-btn');

  closeBtn.addEventListener('click', () => modal.classList.remove('active'));
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.remove('active');
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.classList.contains('active')) {
      modal.classList.remove('active');
    }
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
    const data = await res.json();
    renderDashboard(data);
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

  // Hero Stats
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

  if (data.captain) {
    document.getElementById('header-captain').textContent = `${data.captain.name} (C)`;
  }
  if (data.vice_captain) {
    document.getElementById('header-vc').textContent = `${data.vice_captain.name} (VC)`;
  }

  if (meta.last_updated) {
    const dt = new Date(meta.last_updated);
    document.getElementById('last-updated-text').textContent = dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  // Deadline Countdown
  if (meta.deadline) {
    startCountdown(meta.deadline);
  }

  // Group Starters by Position
  const startersByPos = { 'GK': [], 'DEF': [], 'MID': [], 'FWD': [] };
  (data.starters || []).forEach(p => {
    if (startersByPos[p.position]) {
      startersByPos[p.position].push(p);
    }
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

  (data.bench || []).forEach(p => rowBench.appendChild(renderPlayerCard(p)));

  // Render Tactical Briefing
  const briefingBox = document.getElementById('ai-briefing-content');
  if (data.briefing) {
    if (typeof window.marked !== 'undefined') {
      briefingBox.innerHTML = window.marked.parse(data.briefing);
    } else {
      briefingBox.innerText = data.briefing;
    }
  }

  // Render Mini-Leagues
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
  } else {
    leaguesBody.innerHTML = '<tr><td colspan="2" style="color: var(--text-muted);">No mini-leagues found</td></tr>';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  setupModal();
  loadSquadData();
});
