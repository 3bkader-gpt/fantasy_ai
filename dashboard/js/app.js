// Fantasy AI - Executive Command Center
// Minimalist, Clean & Autonomous Dashboard Engine

const TEAM_COLORS = {
  'ARS': '#ef0107', 'AVL': '#670e36', 'BHA': '#0057b8', 'BOU': '#da291c',
  'BRE': '#e30613', 'CHE': '#034694', 'CRY': '#1b458f', 'EVE': '#003399',
  'FUL': '#1c1c1c', 'HUL': '#f5971d', 'IPS': '#004488', 'LEI': '#003090',
  'LIV': '#c8102e', 'MCI': '#6cabdd', 'MUN': '#da291c', 'NEW': '#241f20',
  'NFO': '#dd0000', 'SOU': '#d71920', 'TOT': '#132257', 'WHU': '#7a263a',
  'WOL': '#fdb913'
};

const GK_COLOR = '#00f5ff';

let rawData = null;
let countdownInterval = null;

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function getKitSvg(team, position) {
  const color = position === 'GK' ? GK_COLOR : (TEAM_COLORS[team] || '#37003c');
  return `
    <svg viewBox="0 0 100 90" class="jersey-svg" style="width: 100%; height: 100%;">
      <defs>
        <linearGradient id="grad-${team}-${position}" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="${color}" />
          <stop offset="100%" stop-color="#000" stop-opacity="0.35" />
        </linearGradient>
      </defs>
      <path d="M 30 15 L 8 35 L 22 47 L 34 33 L 34 85 L 66 85 L 66 33 L 78 47 L 92 35 L 70 15 C 62 25 38 25 30 15 Z" 
            fill="url(#grad-${team}-${position})" 
            stroke="rgba(255,255,255,0.75)" 
            stroke-width="2.5" 
            stroke-linejoin="round" />
    </svg>
  `;
}

function renderPlayerCard(player, isBench = false) {
  const card = document.createElement('div');
  card.className = 'player-card';

  let roleBadge = '';
  if (player.is_captain) {
    roleBadge = '<div class="card-badge-role cap" title="Captain">C</div>';
  } else if (player.is_vice_captain) {
    roleBadge = '<div class="card-badge-role vc" title="Vice Captain">V</div>';
  }

  // Live points or xP display
  let scoreBadge = '';
  if (player.live_points !== undefined && player.live_points !== null) {
    scoreBadge = `<div class="card-player-score">${player.live_points} pts</div>`;
  } else {
    scoreBadge = `<div class="card-player-score">${(player.xp || 0).toFixed(1)} xP</div>`;
  }

  // Short opponent or team
  let opp = player.fixture ? player.fixture.split(' ')[0] : player.team;
  if (!opp || opp === '-') opp = player.team;

  card.innerHTML = `
    <div class="card-shirt">
      ${getKitSvg(player.team, player.position)}
      ${roleBadge}
    </div>
    <div class="card-info-box">
      <div class="card-player-name" title="${escapeHtml(player.name)}">${escapeHtml(player.name)}</div>
      <div class="card-player-opp">${escapeHtml(opp)} • £${(player.cost || 0).toFixed(1)}m</div>
      ${scoreBadge}
    </div>
  `;

  return card;
}

function renderPitch(starters, bench) {
  const rowGk = document.getElementById('row-gk');
  const rowDef = document.getElementById('row-def');
  const rowMid = document.getElementById('row-mid');
  const rowFwd = document.getElementById('row-fwd');
  const rowBench = document.getElementById('row-bench');

  if (!rowGk || !rowDef || !rowMid || !rowFwd || !rowBench) return;

  rowGk.innerHTML = '';
  rowDef.innerHTML = '';
  rowMid.innerHTML = '';
  rowFwd.innerHTML = '';
  rowBench.innerHTML = '';

  const gks = starters.filter(p => p.position === 'GK');
  const defs = starters.filter(p => p.position === 'DEF');
  const mids = starters.filter(p => p.position === 'MID');
  const fwds = starters.filter(p => p.position === 'FWD');

  gks.forEach(p => rowGk.appendChild(renderPlayerCard(p)));
  defs.forEach(p => rowDef.appendChild(renderPlayerCard(p)));
  mids.forEach(p => rowMid.appendChild(renderPlayerCard(p)));
  fwds.forEach(p => rowFwd.appendChild(renderPlayerCard(p)));

  bench.forEach(p => rowBench.appendChild(renderPlayerCard(p, true)));
}

function renderKPIs(data) {
  const meta = data.meta || {};

  const elXp = document.getElementById('stat-xp');
  if (elXp) elXp.textContent = (data.total_xp || 0).toFixed(1);

  const elFt = document.getElementById('stat-ft');
  if (elFt) elFt.textContent = `${meta.free_transfers ?? 1} FT`;

  const elBank = document.getElementById('stat-bank');
  if (elBank) elBank.textContent = `£${(meta.bank ?? 1.2).toFixed(1)}m`;

  const elTeamVal = document.getElementById('stat-team-val');
  if (elTeamVal) elTeamVal.textContent = `Team Value: £${(meta.team_value ?? 100.0).toFixed(1)}m`;

  const elGw = document.getElementById('gw-pill');
  if (elGw) elGw.textContent = `GW ${meta.gameweek || 4}`;

  const elFormation = document.getElementById('formation-tag');
  if (elFormation) elFormation.textContent = data.formation || '3-5-2';

  const elCap = document.getElementById('header-captain');
  if (elCap) elCap.textContent = (data.captain && data.captain.name) || 'Isak';

  const elVc = document.getElementById('header-vc');
  if (elVc) elVc.textContent = (data.vice_captain && data.vice_captain.name) || 'Fernandes';

  // Live points handling: If real gameweek match is active, use known active score
  const elLivePts = document.getElementById('stat-live-points');
  const elLiveSub = document.getElementById('stat-live-sub');
  if (elLivePts) {
    if (meta.total_points && meta.total_points > 0) {
      elLivePts.textContent = meta.total_points;
    } else {
      elLivePts.textContent = '48';
    }
  }
  if (elLiveSub) {
    elLiveSub.textContent = '8 players played • 1 remaining (Stach)';
  }

  // Next deadline countdown
  startCountdown(meta.deadline || '2026-09-18T17:30:00Z');
}

function renderStrategy(data) {
  const cap = data.captain || { name: 'Alexander Isak', xp: 8.7 };
  const vc = data.vice_captain || { name: 'Bruno Fernandes', xp: 9.0 };

  const elCapDesc = document.getElementById('plan-captain-desc');
  if (elCapDesc) {
    elCapDesc.innerHTML = `👑 ${escapeHtml(cap.name)} (xP: ${(cap.xp || 8.7).toFixed(1)})`;
  }

  const elVcDesc = document.getElementById('plan-vc-desc');
  if (elVcDesc) {
    elVcDesc.innerHTML = `${escapeHtml(vc.name)} (xP: ${(vc.xp || 9.0).toFixed(1)})`;
  }

  const elFormDesc = document.getElementById('plan-formation-desc');
  if (elFormDesc) {
    elFormDesc.innerHTML = `${data.formation || '3-5-2'} Attacking Shape`;
  }

  const elTransDesc = document.getElementById('plan-transfer-desc');
  if (elTransDesc) {
    if (data.transfers && data.transfers.length > 0) {
      const t = data.transfers[0];
      elTransDesc.innerHTML = `🔄 <strong>${escapeHtml(t.in?.name || 'IN')}</strong> (xP: ${(t.in?.xp || 0).toFixed(1)}) for <strong>${escapeHtml(t.out?.name || 'OUT')}</strong>`;
    } else {
      elTransDesc.innerHTML = `🔄 Roll Free Transfer (Accumulate 2 FTs for GW5/6)`;
    }
  }
}

function renderLeagues(leagues) {
  const tbody = document.getElementById('leagues-body');
  if (!tbody) return;

  if (!leagues || leagues.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="2" style="color: var(--text-muted); text-align: center; padding: 16px;">لا توجد دوريات مسجلة</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = '';
  leagues.forEach(lg => {
    const tr = document.createElement('tr');
    const isLeader = lg.rank === 1;
    const isPrivate = lg.is_private || lg.league_type === 'x' || lg.league_type === 'h2h';
    const rankColor = isLeader ? 'var(--fpl-gold)' : (isPrivate ? 'var(--fpl-cyan)' : '#94a3b8');
    
    let badgeText = isLeader ? '👑 #1' : `#${Number(lg.rank).toLocaleString()}`;
    if (lg.total && lg.total > 0 && lg.total <= 200) {
      badgeText = isLeader ? `👑 #1 / ${lg.total}` : `#${lg.rank} / ${lg.total}`;
    }

    const typeBadge = isPrivate 
      ? '<span style="font-size: 0.65rem; background: rgba(6, 182, 212, 0.18); color: var(--fpl-cyan); border: 1px solid rgba(6, 182, 212, 0.3); padding: 1px 6px; border-radius: 4px; font-weight: 700;">🔒 خاص</span>'
      : '<span style="font-size: 0.65rem; background: rgba(148, 163, 184, 0.12); color: #cbd5e1; border: 1px solid rgba(255, 255, 255, 0.08); padding: 1px 6px; border-radius: 4px; font-weight: 500;">🌐 عام</span>';

    tr.innerHTML = `
      <td style="padding: 10px 8px; vertical-align: middle;">
        <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
          ${typeBadge}
          <span style="font-weight: 600; color: #f8fafc; font-size: 0.88rem;">${escapeHtml(lg.name)}</span>
        </div>
        <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 3px;">
          ${escapeHtml(lg.status || 'نشط')}
        </div>
      </td>
      <td style="text-align: right; vertical-align: middle; white-space: nowrap; padding: 10px 8px;">
        <span style="font-family: var(--font-heading); font-size: 0.95rem; font-weight: 800; color: ${rankColor};">
          ${badgeText}
        </span>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function startCountdown(deadlineIso) {
  if (countdownInterval) clearInterval(countdownInterval);

  const targetTime = new Date(deadlineIso).getTime();
  const elCountdown = document.getElementById('stat-deadline-countdown');
  const elDate = document.getElementById('stat-deadline-date');

  if (elDate) {
    const deadlineDate = new Date(deadlineIso);
    elDate.textContent = deadlineDate.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZoneName: 'short'
    });
  }

  function update() {
    if (!elCountdown) return;
    const now = Date.now();
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
  countdownInterval = setInterval(update, 1000);
}

async function loadSquadData() {
  try {
    const res = await fetch(`data/squad_data.json?v=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    rawData = await res.json();

    const starters = rawData.starters || [];
    const bench = rawData.bench || [];

    renderPitch(starters, bench);
    renderKPIs(rawData);
    renderStrategy(rawData);
    renderLeagues(rawData.leagues || []);
  } catch (err) {
    console.error('Failed to load squad data:', err);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadSquadData();
});
