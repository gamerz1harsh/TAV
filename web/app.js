/* Anime Sim client: pack-driven presentation over the authoritative Python rules engine. */
const app = document.getElementById('app');
const toastNode = document.getElementById('toast');
const ICONS = {
  life: '☀', character: '✦', stats: '⬡', skills: '▥', training: '◈', jutsu: '印', abilities: '✥', combat: '⚔', equipment: '⚒',
  map: '⌖', people: '♧', missions: '⚑', village: '城', market: '◇', legacy: '♾', chronicle: '▤',
  codex: '巻', settings: '⚙', save: '▣', academy: '⌂', chakra: '◉', explore: '➶',
};
const SKILL_ICONS = {
  ninjutsu: '印', taijutsu: '拳', genjutsu: '◉', shurikenjutsu: '✣', crafting: '⌁',
  smithing: '⚒', medicine: '✚', survival: '⌖',
};
const PAGES = [
  { group: 'Your Life', items: [['life', 'Life'], ['character', 'Character'], ['stats', 'Attributes'], ['skills', 'Skills'], ['training', 'Training'], ['jutsu', 'Techniques'], ['abilities', 'Skill Trees'], ['combat', 'Combat'], ['equipment', 'Equipment']] },
  { group: 'World & People', items: [['map', 'World Map'], ['people', 'People'], ['missions', 'Missions'], ['village', 'Village & Work'], ['market', 'Market']] },
  { group: 'Your Story', items: [['legacy', 'Legacy'], ['chronicle', 'Chronicle'], ['codex', 'World Codex']] },
  { group: 'Simulation', items: [['settings', 'Settings']] },
];
let state = null;
let packs = [];
let selectedPage = 'life';
let selectedChatNpc = null;
let toastTimeout = null;
let busy = false;

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const label = (value) => String(value ?? '').replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase());
const clamp = (value, min = 0, max = 100) => Math.max(min, Math.min(max, Number(value) || 0));
const player = () => state?.player || {};
const profile = () => state?.naruto || player().naruto || {};
const locationName = (id) => state?.world_places?.find((place) => place.id === id)?.name || label(id);

async function request(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data;
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok || data.success === false) throw new Error(data.error || data.message || `Request failed (${response.status})`);
  return data;
}

function toast(message, isError = false) {
  toastNode.textContent = message;
  toastNode.className = `toast show${isError ? ' error' : ''}`;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { toastNode.className = 'toast'; }, 3100);
}

async function mutate(path, body, successText) {
  if (busy) return;
  busy = true;
  try {
    const data = await request(path, body);
    if (data.state) state = data.state;
    render();
    if (successText) toast(successText);
  } catch (error) {
    toast(error.message, true);
  } finally {
    busy = false;
  }
}

function brandMark(size = '') {
  return `<div class="brand-seal ${size}">A</div>`;
}

function renderSetup() {
  const pack = packs.find((item) => item.id === 'naruto') || packs[0];
  if (!pack) {
    app.innerHTML = '<div class="boot-screen"><div class="seal-mark">A</div><p>No world packs are installed.</p></div>';
    return;
  }
  const creation = pack.creation || {};
  const options = (items = []) => items.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join('');
  app.innerHTML = `
    <main class="setup-screen"><div class="setup-wrap">
      <div class="setup-brand">${brandMark()}<div><div class="brand-word">Anime Sim</div><div class="brand-sub">Worlds shaped by your life</div></div></div>
      <section class="setup-card">
        <div class="setup-main">
          <div class="eyebrow">World pack / ${escapeHtml(pack.name)}</div>
          <h1 class="setup-title">A life is not <span>prewritten.</span></h1>
          <p class="setup-intro">Begin as a young shinobi. Your choices shape your skills, relationships, work, reputation, and the world you leave behind. There is no fixed route to becoming someone.</p>
          <form class="setup-form" id="new-life-form">
            <div class="field full"><label for="new-name">Name</label><input id="new-name" name="name" maxlength="32" placeholder="Your shinobi name" required autocomplete="off"></div>
            <div class="field"><label for="new-age">Starting age</label><input id="new-age" name="age" type="number" min="0" max="30" value="0"></div>
            <div class="field"><label for="new-village">Village</label><select id="new-village" name="village">${options(creation.villages)}</select></div>
            <div class="field"><label for="new-clan">Family / clan</label><select id="new-clan" name="clan">${options(creation.clans)}</select></div>
            <div class="field"><div class="field-label">Chakra nature ceremony</div><div class="notice">Your affinity is not chosen at birth. A ceremony at age five reveals your natural chakra nature.</div></div>
            <div class="field full"><div class="field-label">Birth traits</div><div class="traits-preview"><span class="trait-chip"><i class="trait-dot"></i>Randomly inherited</span><span class="trait-chip"><i class="trait-dot"></i>Revealed at birth</span></div><div class="card-copy">No starting perk is selected. The simulation rolls two distinct traits from this world's weighted trait pool; those traits shape your early strengths and limitations.</div></div>
            <div class="field full setup-actions"><button class="button primary" type="submit">Begin this life <span aria-hidden="true">↗</span></button><span class="card-copy">Actions are yours to spend. Advance the year when you are ready.</span></div>
          </form>
          <div class="setup-note">This simulation is rules-first and works offline. Optional LM Studio dialogue can be configured later; it cannot alter stats, rewards, or world rules.</div>
        </div>
        <aside class="setup-aside">
          <div class="eyebrow">The Naruto world pack</div><h2 class="aside-heading">A world with room to grow.</h2>
          <p class="aside-copy">Start at home, earn your place at the Academy, meet the people who will remember you, then decide where your life leads.</p>
          <div class="pack-fact"><div class="pack-fact-icon">⌖</div><div><strong>Six connected countries</strong><small>Travel between the great nations, villages, and frontier settlements. Expeditions can change your standing.</small></div></div>
          <div class="pack-fact"><div class="pack-fact-icon">印</div><div><strong>Progression that opens by doing</strong><small>Chakra control, academy study, nature shaping, clan paths, and jutsu unlock as their requirements are met.</small></div></div>
          <div class="pack-fact"><div class="pack-fact-icon">♧</div><div><strong>People with persistent memory</strong><small>Chat is free. Trust, time together, gifts, and missions are meaningful actions NPCs remember.</small></div></div>
          <div class="pack-fact"><div class="pack-fact-icon">⚑</div><div><strong>Careers and missions</strong><small>Meet a clerk or mentor, build a record, work assignments, and see your reputation grow.</small></div></div>
          <div class="saved-lives"><div class="eyebrow">Continue a life</div><div id="saved-lives" class="saved-list"><span class="card-copy">Looking for saved lives...</span></div></div>
        </aside>
      </section>
    </div></main>`;
  loadSavedLives();
}

async function loadSavedLives() {
  const container = document.getElementById('saved-lives');
  if (!container) return;
  try {
    const data = await request('/api/world/saves');
    const lives = (data.games || []).filter((game) => game.has_save).slice(0, 5);
    container.innerHTML = lives.length ? lives.map((game) => `<button class="saved-life" data-load-game="${escapeHtml(game.folder)}"><span><strong>${escapeHtml(game.player_name)}</strong><small class="identity-meta"> Saved simulation</small></span><span>Continue →</span></button>`).join('') : '<span class="card-copy">No saved lives yet.</span>';
  } catch {
    container.innerHTML = '<span class="card-copy">Saved lives will appear here.</span>';
  }
}

function statValue(name) {
  const values = player().ui_stats || {};
  if (name === 'chakra') return profile().chakra_current ?? 0;
  return values[name] ?? 0;
}

function vitalCard(name, icon, value, tone, maximum = 100) {
  const pct = Math.round(clamp(Number(value) / Math.max(1, maximum) * 100));
  return `<div class="vital-card"><div class="vital-top"><span class="vital-name"><span>${icon}</span>${escapeHtml(label(name))}</span><b class="vital-value">${escapeHtml(value)}${name === 'chakra' ? ` / ${escapeHtml(maximum)}` : ''}</b></div><div class="bar-track"><div class="bar-fill ${tone}" style="width:${pct}%"></div></div></div>`;
}

function renderVitals() {
  const ui = player().ui_stats || {};
  return `<div class="vitals">
    ${vitalCard('health', '♥', ui.health ?? 0, 'health')}
    ${vitalCard('happiness', '✺', ui.happiness ?? 0, 'happiness')}
    ${vitalCard('smarts', '✧', ui.smarts ?? 0, 'smarts')}
    ${vitalCard('chakra', '◉', state.chakra_current ?? 0, 'chakra', state.chakra_capacity ?? 0)}
  </div>`;
}

function navMarkup() {
  const offered = (state.world_quests || []).filter((quest) => quest.status === 'offered').length;
  const opportunities = (state.world_opportunities || []).length;
  return `<aside id="sidebar" class="sidebar">
    <div class="sidebar-brand">${brandMark()}<div><div class="brand-word">Anime Sim</div><div class="brand-sub">Naruto world pack</div></div></div>
    ${PAGES.map((group) => `<div class="nav-group"><div class="nav-heading">${group.group}</div>${group.items.map(([id, title]) => `<button class="nav-link ${selectedPage === id ? 'active' : ''}" data-page="${id}"><span class="nav-icon">${ICONS[id]}</span><span>${title}</span>${id === 'missions' && offered + opportunities ? `<span class="nav-count">${offered + opportunities}</span>` : ''}</button>`).join('')}</div>`).join('')}
    <div class="sidebar-bottom">A life is shaped by the choices you make.</div>
  </aside><div class="mobile-scrim" id="mobile-scrim"></div>`;
}

function shellHeader() {
  const p = player();
  const village = profile().village?.name || 'Unknown village';
  const personal = state.personal_actions_remaining ?? 0;
  const social = state.social_actions_remaining ?? 0;
  return `<header class="topbar">
    <div class="identity"><button class="icon-button mobile-menu" data-menu-toggle aria-label="Open navigation">☰</button><div class="avatar-seal">${escapeHtml(String(p.name || 'A').slice(0, 1).toUpperCase())}</div><div><div class="identity-name">${escapeHtml(p.name || 'Shinobi')} <span style="color:var(--gold)">· ${escapeHtml(state.world_title || 'Unproven')}</span></div><div class="identity-meta">${escapeHtml(village)} / ${escapeHtml(state.world_state?.rank || 'Academy Student')} / age ${escapeHtml(p.age ?? 0)}</div></div></div>
    <div class="top-actions"><span class="top-pill"><b>YEAR ${escapeHtml(state.year ?? 1)}</b></span><span class="top-pill accent">PERSONAL <b>${personal}/${state.action_budget?.personal ?? personal}</b></span><span class="top-pill accent">SOCIAL <b>${social}/${state.action_budget?.social ?? social}</b></span><button class="button" data-save>▣ Save</button><button class="icon-button" data-new-life title="New life" aria-label="New life">＋</button></div>
  </header>`;
}

function pageHeading(kicker, title, subtitle, actions = '') {
  return `<div class="page-head"><div><div class="page-kicker">${escapeHtml(kicker)}</div><h1 class="page-title">${escapeHtml(title)}</h1><p class="page-subtitle">${escapeHtml(subtitle)}</p></div>${actions ? `<div class="page-head-actions">${actions}</div>` : ''}</div>`;
}

function card(title, body, options = {}) {
  const icon = options.icon ? `<span class="card-eyebrow">${options.icon}</span>` : '';
  return `<section class="card"><div class="card-head"><h2 class="card-title">${title}</h2>${icon}</div><div class="card-body">${body}</div></section>`;
}

function availableActions(filter, limit = 0) {
  let actions = (state.world_actions || []).filter((action) => action.available && action.action_type === 'personal');
  if (filter) actions = actions.filter((action) => action.category?.toLowerCase().includes(filter.toLowerCase()) || action.id?.includes(filter.toLowerCase()));
  if (limit) actions = actions.slice(0, limit);
  if (!actions.length) return `<div class="empty-state"><strong>Nothing to do here right now</strong>Travel to a place where an activity is available, or advance the year when you're ready.</div>`;
  return `<div class="action-grid">${actions.map((action) => {
    const icon = action.category?.toLowerCase().includes('chakra') || action.category?.toLowerCase().includes('ninjutsu') ? '印' : action.category?.toLowerCase().includes('body') ? '拳' : action.category?.toLowerCase().includes('academy') ? '▤' : '✦';
    return `<button class="action-card" data-action-id="${escapeHtml(action.id)}"><span class="action-icon">${icon}</span><span><span class="action-title">${escapeHtml(action.label)}</span><span class="action-desc">${escapeHtml(action.description)}</span><span class="action-cost">${escapeHtml(action.action_type)} action${action.chakra_cost ? ` · ${escapeHtml(action.chakra_cost)} chakra` : ''}</span></span></button>`;
  }).join('')}</div>`;
}

function memoryRows(items, limit = 5) {
  const entries = [...(items || [])].slice(-limit).reverse();
  if (!entries.length) return '<div class="empty-state">The chronicle is quiet for now. Your choices will leave a record.</div>';
  return `<div class="memory-list">${entries.map((entry) => {
    const text = typeof entry === 'string' ? entry : entry.text;
    return `<div class="memory-item"><span class="memory-age">Year ${escapeHtml(state.year ?? 1)} / Age ${escapeHtml(player().age ?? 0)}</span>${escapeHtml(text)}</div>`;
  }).join('')}</div>`;
}

function renderEncounter() {
  const encounter = state.world_encounter;
  if (!encounter) return '';
  return `<section class="encounter-card"><div class="encounter-tag">${escapeHtml(label(encounter.type || 'expedition'))} / ${escapeHtml(label(encounter.region_id))}</div><h2 class="encounter-title">${escapeHtml(encounter.title)}</h2><p class="encounter-copy">${escapeHtml(encounter.description)}</p><div class="choice-list">${(encounter.choices || []).map((choice) => `<button class="button primary" data-encounter-choice="${escapeHtml(choice.id)}">${escapeHtml(choice.label)}</button>`).join('')}</div></section>`;
}

function renderNatureCeremony() {
  const ceremony = state.world_nature_ceremony;
  if (!ceremony || Number(ceremony.year) !== Number(state.year)) return '';
  return `<section class="ceremony-reveal"><span class="ceremony-seal">◉</span><div><div class="eyebrow">Age-five chakra ceremony</div><strong>Your natural affinity is ${escapeHtml(ceremony.nature)}.</strong><p>${escapeHtml(state.world_last_narration || 'The ceremony reveals your first nature transformation path.')}</p></div></section>`;
}

function renderTrainingResult() {
  const result = state.world_last_action_result;
  if (!result) return '';
  const gains = (items) => Object.entries(items || {}).filter(([, value]) => Number(value) > 0).map(([key, value]) => `<span>+${escapeHtml(value)} ${escapeHtml(label(key))}</span>`).join('');
  const techniqueGains = Object.entries(result.technique_mastery_gains || {}).map(([key, value]) => `<span>+${escapeHtml(value)} ${escapeHtml(label(key))} mastery XP</span>`).join('');
  const allGains = [gains(result.attribute_gains), gains(result.skill_xp_gains), gains(result.nature_affinity_gains), techniqueGains].filter(Boolean).join('');
  return `<section class="training-result ${result.critical ? 'critical' : ''}"><div class="training-result-head"><span class="eyebrow">Last training result</span>${result.critical ? '<strong class="critical-badge">CRITICAL SUCCESS ×2</strong>' : '<span class="eyebrow">STANDARD RESULT</span>'}</div><strong>${escapeHtml(result.label || 'Training')}</strong><div class="training-gains">${allGains || `<span>Technique mastery +${escapeHtml(result.mastery_gain || 'progress')}</span>`}</div><small>Random training gain · ${escapeHtml(result.critical_chance ?? 8)}% critical chance</small></section>`;
}

function renderWorldOpportunities() {
  return (state.world_opportunities || []).map((opportunity) => `<section class="encounter-card opportunity-card"><div class="encounter-tag">A turning point / Year ${escapeHtml(opportunity.triggered_year || state.year || 1)}</div><h2 class="encounter-title">${escapeHtml(opportunity.title)}</h2><p class="encounter-copy">${escapeHtml(opportunity.description)}</p><div class="opportunity-choices">${(opportunity.choices || []).map((choice) => {
    const costs = choice.costs || {};
    const costText = [costs.personal_actions ? `${costs.personal_actions} personal` : '', costs.social_actions ? `${costs.social_actions} social` : '', costs.money ? `${costs.money} Ryo` : ''].filter(Boolean).join(' · ') || 'No action cost';
    const locked = (state.personal_actions_remaining || 0) < Number(costs.personal_actions || 0) || (state.social_actions_remaining || 0) < Number(costs.social_actions || 0) || (state.world_wallet || 0) < Number(costs.money || 0);
    return `<button class="opportunity-choice" data-opportunity="${escapeHtml(opportunity.id)}" data-opportunity-choice="${escapeHtml(choice.id)}" ${locked ? 'disabled' : ''}><span class="choice-glyph">${costs.personal_actions || costs.social_actions ? '◈' : '✦'}</span><span class="choice-copy"><strong>${escapeHtml(choice.label)}</strong><small>${escapeHtml(choice.description || '')}</small><em>${escapeHtml(costText)}</em></span><span class="choice-arrow">›</span></button>`;
  }).join('')}</div><div class="free-note">This opportunity stays open if you need to advance the year to refresh your actions.</div></section>`).join('');
}

function renderLife() {
  const p = player();
  const naruto = profile();
  const remaining = state.personal_actions_remaining || 0;
  const stage = state.life_stage || 'Academy preparation';
  const intro = remaining ? `There are ${remaining} personal choices left in this year. Spend them where you are, or travel to a place that opens a different path.` : 'You have used this year’s personal actions. Review the year, then move time forward when ready.';
  const available = (state.world_actions || []).filter((action) => action.available && action.action_type === 'personal');
  const recommendations = state.recommended_world_actions || [];
  return `${pageHeading('Life overview', 'Your shinobi year', `${stage} · actions are yours to use; the year advances when you choose.`, `<button class="button primary" data-advance ${state.world_encounter ? 'disabled' : ''}>Advance year <span>›</span></button>`)}
    ${renderEncounter()}
    ${renderNatureCeremony()}
    ${renderTrainingResult()}
    ${renderWorldOpportunities()}
    <section class="hero-card"><div class="hero-line"><span>✦</span> Age ${escapeHtml(p.age ?? 0)} / Year ${escapeHtml(state.year ?? 1)} / ${escapeHtml(state.world_state?.phase || 'A new beginning')}</div><h2 class="hero-heading">A year of possibility.</h2><p class="hero-text">${escapeHtml(intro)} Your role is not chosen for you: academy, family, training, village service, travel, and the people you meet all shape what comes next.</p><div class="hero-meta"><span class="meta-chip">⌖ ${escapeHtml(locationName(state.world_location))}</span><span class="meta-chip">⚑ ${escapeHtml(state.world_state?.rank || 'Academy Student')}</span><span class="meta-chip">◈ ${escapeHtml(naruto.chakra_nature?.name || 'Unknown')} nature</span><span class="meta-chip">♧ ${escapeHtml((state.world_people_present || []).length)} here</span></div></section>
    <div class="grid wide-left" style="margin-top:16px">
      <div class="grid">
        ${card('Open choices', `<p class="card-copy">Available activities at ${escapeHtml(locationName(state.world_location))}. Locked activities stay out of this list until their conditions are met.</p>${available.length ? availableActions('', 4) : '<div class="empty-state"><strong>No available action at this place</strong>Use World Map to travel, visit the Academy, or go to a training ground.</div>'}<div style="margin-top:12px"><button class="button ghost" data-page="training">All available activities →</button></div>`)}
        ${card('Recommended training', recommendations.length ? `<p class="card-copy">Suggestions match your current level and remove drills you have already outgrown.</p><div class="action-grid">${recommendations.map((action) => `<button class="action-card" data-action-id="${escapeHtml(action.id)}"><span class="action-icon">✦</span><span><span class="action-title">${escapeHtml(action.label)}</span><span class="action-desc">${escapeHtml(action.recommendation_reason || action.description)}</span><span class="action-cost">${escapeHtml(action.category || 'Training')} · 1 personal action</span></span></button>`).join('')}</div>` : '<div class="empty-state">No training is currently available here. Visit the Academy or training ground to open more paths.</div>')}
        ${card('Recent memories', memoryRows(state.memories, 5), { icon: 'YOUR STORY' })}
      </div>
      <div class="grid">
        ${card('Shinobi profile', `<div class="profile-summary"><div class="profile-monogram">${escapeHtml(String(p.name || '?').slice(0, 1).toUpperCase())}</div><div><div class="profile-primary">${escapeHtml(naruto.clan?.name || 'Civilian-born')} · ${escapeHtml(naruto.chakra_nature?.name || 'Undetermined')}</div><div class="profile-secondary">${escapeHtml(naruto.village?.name || '')} / ${escapeHtml(state.world_state?.rank || '')}</div></div></div><div class="combat-banner" style="margin-top:16px"><div><div class="combat-label">Combat power</div><div class="card-copy">Physical ability · chakra · skill · technique mastery</div></div><div class="combat-number">${escapeHtml(state.combat_power || 0)}</div></div><div class="section-label">Traits at birth</div><div class="traits-preview">${(naruto.traits || []).map((trait) => `<span class="trait-chip rarity-${escapeHtml(String(trait.rarity || 'common').toLowerCase())}"><i class="trait-dot"></i>${escapeHtml(trait.name)}</span>`).join('') || '<span class="card-copy">No traits recorded.</span>'}</div>`)}
        ${card('Your standing', `<div class="attribute-grid"><div class="attribute-tile"><div class="attribute-top"><span>Village influence</span><span>◆</span></div><div class="attribute-value">${escapeHtml(state.world_influence || 0)}</div><div class="attribute-context">${escapeHtml(state.world_title || 'Unproven')}</div></div><div class="attribute-tile"><div class="attribute-top"><span>Ryo</span><span>◈</span></div><div class="attribute-value">${escapeHtml(state.world_wallet || 0)}</div><div class="attribute-context">Personal funds</div></div></div><p class="card-copy" style="margin:12px 0 0">Your reputation grows through what you do and who remembers it. No fixed career path is required.</p><button class="button ghost" style="margin-top:12px" data-page="village">Village & work →</button>`)}
      </div>
    </div>`;
}

function renderCharacter() {
  const p = player();
  const naruto = profile();
  const traits = naruto.traits || [];
  const traitCards = traits.length ? traits.map((trait) => {
    const modifierNames = { all_xp_percent: 'all skill XP', training_xp_percent: 'training XP', ninjutsu_xp_percent: 'Ninjutsu XP', taijutsu_xp_percent: 'Taijutsu XP', chakra_cost_percent: 'chakra cost', combat_power_percent: 'combat power', income_percent: 'income', disaster_resistance_percent: 'disaster resistance', training_crit_chance_percent: 'critical chance', relationship_gain_percent: 'relationship gains' };
    const effects = Object.entries(trait.modifiers || {}).filter(([key]) => modifierNames[key]).map(([key, value]) => `${Number(value) > 0 ? '+' : ''}${value}% ${modifierNames[key]}`).join(' · ');
    return `<div class="trait-card rarity-${escapeHtml(String(trait.rarity || 'common').toLowerCase())}"><span class="action-icon">✦</span><div><div class="trait-name">${escapeHtml(trait.name)} <span class="trait-rarity rarity-${escapeHtml(String(trait.rarity || 'common').toLowerCase())}">${escapeHtml(trait.rarity)}</span></div><div class="trait-description">${escapeHtml(trait.description)}</div>${effects ? `<div class="trait-effect">${escapeHtml(effects)}</div>` : ''}</div></div>`;
  }).join('') : '<div class="empty-state"><strong>No birth traits recorded in this save.</strong>Older lives keep their original stats. New lives receive two random traits from this world pack.</div>';
  const lineage = naruto.clan?.lineage;
  return `${pageHeading('Identity & history', 'Character', 'The life you inherited, the qualities you carry, and what may still emerge.')}
    <div class="grid two">
      ${card('Who you are', `<div class="profile-summary"><div class="profile-monogram">${escapeHtml(String(p.name || '?').slice(0, 1).toUpperCase())}</div><div><div class="profile-primary">${escapeHtml(p.name || '')}</div><div class="profile-secondary">Age ${escapeHtml(p.age ?? 0)} · ${escapeHtml(p.life_stage || 'Growing up')}</div></div></div><div class="section-label">Roots</div><div class="attribute-grid"><div class="attribute-tile"><div class="attribute-top">Village</div><div class="attribute-value" style="font-size:17px">${escapeHtml(naruto.village?.name || '—')}</div></div><div class="attribute-tile"><div class="attribute-top">Clan</div><div class="attribute-value" style="font-size:17px">${escapeHtml(naruto.clan?.name || '—')}</div></div><div class="attribute-tile"><div class="attribute-top">Nature</div><div class="attribute-value" style="font-size:17px">${escapeHtml(naruto.chakra_nature?.name || '—')}</div></div><div class="attribute-tile"><div class="attribute-top">Rank</div><div class="attribute-value" style="font-size:17px">${escapeHtml(state.world_state?.rank || '—')}</div></div></div>`)}
      ${card('Birth traits', `<p class="card-copy">Traits are rolled from this world's weighted pool at the start of a life. They are not selected perks: they may help in one area while creating limits in another.</p><div class="trait-list">${traitCards}</div>`)}
      ${card('Lineage', lineage ? `<div class="eyebrow">${escapeHtml(naruto.clan?.name || 'Clan')}</div><h3 class="aside-heading">${escapeHtml(lineage.name)}</h3><p class="card-copy">This inherited ability is currently ${escapeHtml(lineage.status || 'dormant')}. Bloodline abilities emerge through world-pack conditions and story events; they are not guaranteed at character creation.</p><div class="notice">Lineage progression is modular pack content. This Naruto pack tracks the inherited state but does not yet implement every bloodline awakening path.</div>` : `<h3 class="aside-heading">A path of your own</h3><p class="card-copy">You were born without a named clan lineage. Your skills and relationships can still open a distinctive shinobi path.</p>`)}
      ${card('Family & bonds', `<div class="attribute-grid">${Object.entries(naruto.relationships || {}).map(([key, value]) => `<div class="attribute-tile"><div class="attribute-top">${escapeHtml(label(key))}</div><div class="attribute-value">${escapeHtml(value)}</div><div class="bar-track"><div class="bar-fill" style="width:${clamp(value)}%"></div></div></div>`).join('')}</div><p class="card-copy" style="margin-top:12px">Individual relationships are tracked on each person. These group values reflect the broader social roots of your life.</p>`)}
    </div>`;
}

function radarChart(attributes) {
  const points = [
    ['Strength', attributes.strength || 0], ['Agility', attributes.agility || 0], ['Control', attributes.chakra_control || 0],
    ['Intellect', attributes.intelligence || 0], ['Vitality', attributes.vitality || 0], ['Will', attributes.willpower || 0],
  ];
  const cx = 190, cy = 170, radius = 112;
  const angle = (index) => (-Math.PI / 2) + index * Math.PI / 3;
  const xy = (index, scale) => [cx + Math.cos(angle(index)) * radius * scale, cy + Math.sin(angle(index)) * radius * scale];
  const polygon = (scale) => points.map((_, i) => xy(i, scale).map((n) => n.toFixed(1)).join(',')).join(' ');
  const valuePoly = points.map(([, value], i) => xy(i, clamp(value) / 100).map((n) => n.toFixed(1)).join(',')).join(' ');
  const labels = points.map(([name], i) => {
    const [x, y] = xy(i, 1.24);
    const anchor = x < cx - 14 ? 'end' : x > cx + 14 ? 'start' : 'middle';
    return `<text class="radar-label" x="${x.toFixed(1)}" y="${(y + 3).toFixed(1)}" text-anchor="${anchor}">${escapeHtml(name)}</text>`;
  }).join('');
  const dots = points.map(([, value], i) => { const [x, y] = xy(i, clamp(value) / 100); return `<circle class="radar-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4"/>`; }).join('');
  const axes = points.map((_, i) => { const [x, y] = xy(i, 1); return `<line class="radar-axis" x1="${cx}" y1="${cy}" x2="${x}" y2="${y}"/>`; }).join('');
  return `<div class="radar-wrap"><svg viewBox="0 0 380 340" role="img" aria-label="Hexagonal attribute chart">
    ${[.25, .5, .75, 1].map((scale) => `<polygon class="radar-grid" points="${polygon(scale)}"/>`).join('')}${axes}<polygon class="radar-shape" points="${valuePoly}"/>${dots}${labels}
  </svg></div>`;
}

function renderStats() {
  const attrs = state.effective_attributes || profile().attributes || {};
  const fields = [
    ['Strength', attrs.strength], ['Agility', attrs.agility], ['Intelligence', attrs.intelligence], ['Vitality', attrs.vitality],
    ['Chakra control', attrs.chakra_control], ['Chakra capacity', attrs.chakra_capacity], ['Academy knowledge', attrs.academy_knowledge],
    ['Hand seals', attrs.hand_seals], ['Body conditioning', attrs.body_conditioning], ['Willpower', attrs.willpower], ['Charisma', attrs.charisma], ['Luck', attrs.luck],
  ];
  const tiles = fields.map(([name, value]) => `<div class="attribute-tile"><div class="attribute-top"><span>${escapeHtml(name)}</span><span>⬡</span></div><div class="attribute-value">${escapeHtml(value ?? 0)}</div><div class="attribute-context">${escapeHtml(value >= 70 ? 'Exceptional' : value >= 45 ? 'Developed' : value >= 20 ? 'Growing' : 'Early potential')}</div></div>`).join('');
  const nature = Object.entries(profile().nature_affinity || {}).map(([key, value]) => `<div class="skill-row"><div class="skill-name">◉ ${escapeHtml(label(key))} nature</div><div class="skill-track"><div class="skill-fill" style="width:${clamp(value)}%"></div></div><div class="skill-rank"><b>${escapeHtml(value)}</b> affinity</div></div>`).join('');
  return `${pageHeading('Character metrics', 'Attributes', 'Your hexagonal profile updates with training, gear, passive jutsu, and modes. The age-five ceremony reveals your primary nature; advanced releases depend on trained affinities.')}
    <div class="combat-banner" style="margin-bottom:16px"><div><div class="combat-label">Combat power / power level</div><div class="card-copy">Effective attributes, shinobi disciplines, equipped tier, technique mastery, and active transformations.</div></div><div class="combat-number">${escapeHtml(state.power_level || state.combat_power || 0)}</div></div>
    <div class="stats-layout">${card('Attribute profile', radarChart(attrs), { icon: 'HEXAGON / 01' })}${card('Detailed attributes', `<div class="attribute-grid">${tiles}</div>`)}</div>
    <div style="margin-top:16px">${card('Chakra nature affinity', `<p class="card-copy">The ceremony reveals one primary nature. Repeated practice builds secondary affinities; combinations such as Ice and Sand require the Character Skill Tree as well as their component natures.</p><div class="skill-list">${nature}</div>`)}</div>`;
}

function renderSkills() {
  const skills = state.effective_skills || profile().skills || {};
  const ranks = state.world_skill_ranks || {};
  const entries = Object.entries(skills).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const rows = entries.map(([key, value]) => `<div class="skill-row"><div class="skill-name"><span class="nav-icon">${SKILL_ICONS[key] || '✦'}</span>${escapeHtml(label(key))}</div><div class="skill-track"><div class="skill-fill" style="width:${clamp(value)}%"></div></div><div class="skill-rank"><b>Lv ${escapeHtml(value)}</b>${escapeHtml(ranks[key] || 'Beginner')}</div></div>`).join('');
  return `${pageHeading('Practice becomes ability', 'Skills', 'Skills are earned through actions, studies, work, and lived experience. No point allocation screen.')}
    <div class="grid two"><div>${card('Shinobi disciplines', `<p class="card-copy">Combat power: <strong style="color:var(--gold)">${escapeHtml(state.combat_power || 0)}</strong> · learned techniques: <strong>${(profile().techniques || []).length}</strong></p><div class="skill-list">${rows}</div>`)}</div><div class="grid">${card('What shapes growth', `<div class="pack-fact"><div class="pack-fact-icon">拳</div><div><strong>Training</strong><small>Body conditioning, chakra control, and practice improve attributes and linked skills.</small></div></div><div class="pack-fact"><div class="pack-fact-icon">▤</div><div><strong>Education</strong><small>Academy study builds knowledge, seal fluency, and the prerequisites for techniques.</small></div></div><div class="pack-fact"><div class="pack-fact-icon">⌖</div><div><strong>Experience</strong><small>Expeditions and missions grow field skills. Different jobs can add new progression tracks.</small></div></div>`)}${card('Skill ranks', `<p class="card-copy">Beginner 0–19 · Intermediate 20–44 · Advanced 45–69 · Expert 70–89 · Master 90+.</p><button class="button ghost" data-page="training">Practice a skill →</button>`)}</div></div>`;
}

function renderTraining() {
  const available = (state.world_actions || []).filter((action) => action.available && action.action_type === 'personal' && !['Adventure', 'World Building'].includes(action.category));
  const unlocks = (state.training_unlocks || []).filter((item) => item.unlocked);
  const places = (state.world_places || []).filter((place) => !place.region_id || place.region_id === state.world_state?.current_region);
  return `${pageHeading('Learn by doing', 'Training & study', 'Only actions whose age, location, skill, and progression requirements are met appear here.')}
    <div class="notice" style="margin-bottom:15px">You are at <strong>${escapeHtml(locationName(state.world_location))}</strong>. Actions are personal choices and use one personal action. Choose a different location on the map to open other activities.</div>
    ${renderTrainingResult()}
    ${available.length ? `<div class="action-grid">${available.map((action) => `<button class="action-card" data-action-id="${escapeHtml(action.id)}"><span class="action-icon">${action.category?.toLowerCase().includes('chakra') ? '◉' : action.category?.toLowerCase().includes('academy') ? '▤' : action.category?.toLowerCase().includes('body') ? '拳' : '✦'}</span><span><span class="action-title">${escapeHtml(action.label)}</span><span class="action-desc">${escapeHtml(action.description)}</span><span class="action-cost">${escapeHtml(action.category || 'Activity')} · 1 personal action${action.chakra_cost ? ` · ${escapeHtml(action.chakra_cost)} chakra` : ''}</span></span></button>`).join('')}</div>` : '<div class="empty-state"><strong>No training activity is currently available here.</strong>Travel to the Academy or a training ground. More options unlock as your character meets requirements.</div>'}
    <div class="grid two" style="margin-top:17px">${card('Progression milestones reached', unlocks.length ? `<div class="unlock-list">${unlocks.map((item) => `<div class="unlock-item"><span class="unlock-stamp">✓</span><div><div class="unlock-name">${escapeHtml(item.label)}</div><div class="unlock-copy">${escapeHtml(item.description)}</div></div></div>`).join('')}</div>` : '<div class="empty-state">Your specialized training paths have not unlocked yet.</div>')}${card('Places to learn', `<div class="place-grid">${places.filter((place) => ['academy', 'training_ground', 'clinic'].includes(place.id)).map((place) => `<div class="place-card ${state.world_location === place.id ? 'current' : ''}"><div><div class="place-name">${escapeHtml(place.name)}</div><div class="place-description">${escapeHtml(place.description)}</div></div>${state.world_location === place.id ? '<span class="eyebrow">HERE</span>' : `<button class="button small" data-travel-location="${escapeHtml(place.id)}">Go</button>`}</div>`).join('')}</div>`)}</div>`;
}

function renderTechniques() {
  const known = profile().techniques || [];
  const learnActions = (state.world_actions || []).filter((action) => action.available && action.action_type === 'personal' && ['Ninjutsu', 'Technique'].includes(action.category));
  const locks = (state.world_actions || []).filter((action) => !action.available && action.category === 'Ninjutsu');
  const knownCards = known.length ? known.map((technique) => {
    const tier = Number(technique.tier || 1);
    const power = Number(technique.combat_power || 0)
      + Math.max(0, Number(technique.level || 1) - 1) * Number(technique.power_per_level || 0)
      + Math.max(0, tier - 1) * Number(technique.power_per_tier || 2);
    return `<article class="technique-card"><div class="tech-head"><div><div class="tech-name">${escapeHtml(technique.name)}</div><div class="tech-rank">${escapeHtml(technique.rank || 'Academy')} / ${escapeHtml(technique.nature || 'Ninjutsu')} / ${technique.type === 'passive' ? 'PASSIVE' : 'ACTIVE'}</div></div><span class="tier-seal">T${tier}</span></div><p class="tech-desc">${escapeHtml(technique.description)}</p><div class="tech-stats"><span>◉ ${escapeHtml(technique.chakra_cost ?? 0)} chakra</span><span>⌖ ${escapeHtml(technique.range || '—')}</span><span>⚡ ${escapeHtml(power)} power</span><span>Level ${escapeHtml(technique.level || 1)} · ${escapeHtml(technique.xp || 0)} XP</span></div><div class="bar-track" style="margin-top:12px"><div class="bar-fill chakra" style="width:${clamp((Number(technique.xp || 0) % Number(technique.xp_per_level || 20)) / Number(technique.xp_per_level || 20) * 100)}%"></div></div><div class="tech-footer"><span class="mastery-copy">${technique.type === 'passive' ? `Passive ${technique.active ? 'active' : 'inactive'}` : `Mastery ${escapeHtml(technique.mastery ?? 0)}%`} · Cooldown ${escapeHtml(technique.cooldown || 'None')}</span>${technique.type === 'passive' ? `<button class="button small" data-passive-toggle="${escapeHtml(technique.id)}" data-active="${technique.active ? 'false' : 'true'}">${technique.active ? 'Disable' : 'Enable'}</button>` : `<button class="button small" data-action-id="practice_technique_${escapeHtml(technique.id)}" ${state.chakra_current < (technique.chakra_cost || 0) ? 'disabled' : ''}>Practice · ${escapeHtml(technique.chakra_cost || 0)} chakra</button>`}</div></article>`;
  }).join('') : '<div class="empty-state"><strong>Your scroll is still blank.</strong>Meet the Academy requirements or unlock a clan/nature technique in Skill Trees.</div>';
  return `${pageHeading('Technique archive', 'Jutsu & mastery', 'Jutsu list their chakra cost, range, combat rating, cooldown, and personal mastery.')}
    <div class="combat-banner" style="margin-bottom:16px"><div><div class="combat-label">Chakra reserve</div><div class="card-copy">Current chakra refills at the beginning of each year. Active techniques can be practiced for XP and levels.</div></div><div class="combat-number">${escapeHtml(state.chakra_current || 0)} <span style="font-size:14px;color:var(--muted)">/ ${escapeHtml(state.chakra_capacity || 0)}</span></div></div>
    ${card(`Known techniques <span class="card-eyebrow">${known.length} learned</span>`, `<div class="technique-grid">${knownCards}</div>`)}
    <div class="grid two" style="margin-top:16px">${card('Available to learn', learnActions.length ? `<div class="action-grid">${learnActions.map((action) => `<button class="action-card" data-action-id="${escapeHtml(action.id)}"><span class="action-icon">印</span><span><span class="action-title">${escapeHtml(action.label)}</span><span class="action-desc">${escapeHtml(action.description)}</span><span class="action-cost">Requires one personal action</span></span></button>`).join('')}</div>` : '<div class="empty-state">No technique is currently ready to learn. Study at the Academy and meet the listed milestones.</div>')}${card('Progression notes', locks.length ? `<div class="unlock-list">${locks.slice(0, 6).map((action) => `<div class="unlock-item locked"><span class="unlock-stamp">⌑</span><div><div class="unlock-name">${escapeHtml(action.label)}</div><div class="unlock-copy">${escapeHtml(action.lock_reason || 'Requirement not met')}</div></div></div>`).join('')}</div>` : '<div class="notice">More techniques become available as the world pack expands.</div>')}</div>`;
}

function renderCombat() {
  const fight = state.world_combat;
  const last = state.world_last_combat;
  if (fight?.status === 'active') {
    const techniques = (profile().techniques || []).filter((technique) => technique.type !== 'passive').map((technique) => `<button class="button" data-combat-move="technique:${escapeHtml(technique.id)}" ${state.chakra_current < (technique.chakra_cost || 0) ? 'disabled' : ''}>印 ${escapeHtml(technique.name)} · ${escapeHtml(technique.chakra_cost || 0)} chakra</button>`).join('');
    return `${pageHeading('Supervised match / Round ' + fight.round, 'Combat', `Sparring with ${fight.opponent_name}. One match uses one personal action; combat choices inside the match do not cost additional actions.`)}
      <div class="combat-arena"><div class="arena-title"><span>⚔</span> ACADEMY TRAINING MATCH <span>⚔</span></div><div class="arena-duel"><div class="fighter-card"><div class="fighter-mark">${escapeHtml(String(player().name || 'A').slice(0, 1).toUpperCase())}</div><div class="fighter-name">${escapeHtml(player().name)}</div><div class="fighter-note">Combat power ${escapeHtml(state.combat_power || 0)}</div><div class="bar-track arena-health"><div class="bar-fill health" style="width:${clamp(fight.player_hp / fight.player_max_hp * 100)}%"></div></div><div class="fighter-hp">${escapeHtml(fight.player_hp)} / ${escapeHtml(fight.player_max_hp)}</div></div><div class="arena-vs">VS</div><div class="fighter-card"><div class="fighter-mark opponent">${escapeHtml(String(fight.opponent_name || '?').slice(0, 1))}</div><div class="fighter-name">${escapeHtml(fight.opponent_name)}</div><div class="fighter-note">Training partner · power ${escapeHtml(fight.opponent_power)}</div><div class="bar-track arena-health"><div class="bar-fill" style="width:${clamp(fight.opponent_hp / fight.opponent_max_hp * 100)}%"></div></div><div class="fighter-hp">${escapeHtml(fight.opponent_hp)} / ${escapeHtml(fight.opponent_max_hp)}</div></div></div><div class="arena-odds"><div><span>Win estimate</span><strong>${escapeHtml(fight.player_win_probability || 50)}%</strong></div><div><span>Nature matchup</span><strong>${fight.nature_advantage > 0 ? 'Advantage' : fight.nature_advantage < 0 ? 'Disadvantage' : 'Neutral'}</strong></div><div class="bar-track"><div class="bar-fill chakra" style="width:${clamp(fight.player_win_probability || 50)}%"></div></div></div><div class="arena-log">${(fight.log || []).slice().reverse().map((line) => `<div>· ${escapeHtml(line)}</div>`).join('')}</div></div>
      ${card('Choose your next move', `<p class="card-copy">A strike uses strength, agility, and taijutsu. Guard reduces the incoming exchange. Learned jutsu deal technique-weighted damage and spend chakra.</p><div class="choice-list"><button class="button primary" data-combat-move="strike">拳 Strike</button><button class="button" data-combat-move="guard">◉ Guard</button>${techniques}<button class="button danger" data-combat-move="retreat">Yield match</button></div>`)}`;
  }
  const opponents = (state.world_combat_opponents || []).filter((item) => Number(player().age || 0) >= Number(item.min_age || 0));
  const ready = opponents.filter((item) => item.location === state.world_location);
  const result = last ? `<div class="encounter-card"><div class="encounter-tag">Last match / ${escapeHtml(last.status)}</div><h2 class="encounter-title">${last.status === 'won' ? 'A clean win.' : last.status === 'retreated' ? 'You yielded.' : 'The instructor called the match.'}</h2><p class="encounter-copy">${escapeHtml(last.opponent_name)} · ${escapeHtml(last.round || 0)} rounds. Skill growth and any consequences have been recorded.</p><div class="arena-log">${(last.log || []).slice(-6).map((line) => `<div>· ${escapeHtml(line)}</div>`).join('')}</div></div>` : '';
  const opponentCards = ready.map((opponent) => {
    const npc = (state.world_people || []).find((person) => person.id === opponent.npc_id);
    return `<div class="quest-card"><div class="quest-head"><div><div class="quest-name">${escapeHtml(npc?.name || 'Training partner')}</div><div class="person-role">${escapeHtml(opponent.mode || 'Sparring')} · ${escapeHtml(locationName(opponent.location))}</div></div><span class="quest-status">READY</span></div><p class="quest-copy">${escapeHtml(npc?.description || opponent.description)}</p><div class="quest-meta"><span>Partner power ${escapeHtml(npc?.combat_power || 18)}</span><span>One personal action</span></div><button class="button primary small" style="margin-top:12px" data-combat-start="${escapeHtml(opponent.id)}">Begin supervised spar</button></div>`;
  }).join('');
  const sparringContent = opponentCards || '<div class="empty-state"><strong>Go to the training ground</strong>Sparring opens at age 8. This is a supervised match, not a life-or-death encounter.</div>';
  const travelButton = state.world_location !== 'training_ground' ? '<button class="button ghost" data-travel-location="training_ground">Travel to the training ground →</button>' : '';
  const modelContent = `<div class="pack-fact"><div class="pack-fact-icon">⬡</div><div><strong>Strength, agility & taijutsu</strong><small>Contribute to your base strike; combat power is a broader long-term estimate.</small></div></div><div class="pack-fact"><div class="pack-fact-icon">◉</div><div><strong>Guard or spend chakra</strong><small>Guard reduces damage. A known jutsu can swing a round, but pays its listed chakra cost.</small></div></div><div class="pack-fact"><div class="pack-fact-icon">✚</div><div><strong>Bounded consequences</strong><small>Supervised sparring can lower health and raise taijutsu, morale, influence, and teammate trust. No random instant death.</small></div></div>`;
  return `${pageHeading('A test of control', 'Combat & sparring', 'Train with a partner before the field tests you for real. Combat power is an estimate; preparation, chakra, and choices decide an exchange.')}${result}
    <div class="grid two"><div>${card('Available sparring', sparringContent)}${travelButton}</div>${card('Combat model', modelContent)}</div>`;
}

function renderMap() {
  const regions = state.world_regions || [];
  const byId = Object.fromEntries(regions.map((region) => [region.id, region]));
  const lines = [];
  for (const region of regions) for (const route of region.routes || []) {
    if (region.id.localeCompare(route) > 0 || !byId[route]) continue;
    const [x1, y1] = region.map_position || [40, 50];
    const [x2, y2] = byId[route].map_position || [60, 50];
    lines.push(`<line class="route-line" x1="${x1}%" y1="${y1}%" x2="${x2}%" y2="${y2}%"/>`);
  }
  const nodes = regions.map((region, index) => {
    const [x, y] = region.map_position || [20 + index * 12, 50];
    const disabled = !region.current && !region.reachable;
    return `<button class="map-node ${region.current ? 'current' : ''} ${disabled ? 'unreachable' : ''}" style="left:${x}%;top:${y}%" data-travel-region="${escapeHtml(region.id)}" ${disabled ? 'disabled' : ''}><span class="map-node-dot">${region.current ? '✦' : '⌖'}</span><span class="map-node-name">${escapeHtml(region.name)}</span><span class="map-node-detail">${region.current ? 'CURRENT REGION' : region.reachable ? 'ROUTE OPEN' : 'NO DIRECT ROUTE'}</span></button>`;
  }).join('');
  const places = (state.world_places || []).filter((place) => !place.region_id || place.region_id === state.world_state?.current_region);
  const expedition = (state.world_actions || []).find((action) => action.id === 'adventure_expedition');
  return `${pageHeading('Travel & discovery', 'World map', 'Choose a connected route to travel between countries. Travel uses one personal action; arrival may begin an expedition encounter.')}
    ${renderEncounter()}
    ${expedition ? `<div class="map-expedition-callout"><div><span class="eyebrow">Field activity / one personal action</span><strong>Explore the current country</strong><p>${escapeHtml(expedition.available ? expedition.description : expedition.lock_reason || expedition.description)}</p></div><button class="button primary" data-action-id="${escapeHtml(expedition.id)}" ${expedition.available ? '' : 'disabled'}>Set out ↗</button></div>` : ''}
    <div class="grid wide-left"><div class="card"><div class="card-head"><h2 class="card-title">${escapeHtml(state.world_pack?.name || 'Shinobi Nations')}</h2><span class="card-eyebrow">${escapeHtml(state.world_state?.current_region ? label(state.world_state.current_region) : 'COUNTRY ROUTES')}</span></div><div class="card-body"><div class="map-caption"><span>⟡ Routes are pack-defined. You can only move to a connected region.</span><span>⌖ ${escapeHtml(locationName(state.world_location))}</span></div><div class="map-canvas"><svg class="map-routes" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${lines.join('')}</svg>${nodes}</div><p class="card-copy" style="margin:13px 0 0">A journey can surface a courier, patrol, local emergency, or other encounter. Each choice influences skills, relationships, money, and village standing.</p></div></div>
      <div class="grid">${card('Local places', `<div class="place-grid">${places.map((place) => `<div class="place-card ${state.world_location === place.id ? 'current' : ''}"><div><div class="place-name">${escapeHtml(place.name)}</div><div class="place-description">${escapeHtml(place.description)}</div></div>${state.world_location === place.id ? '<span class="eyebrow">HERE</span>' : `<button class="button small" data-travel-location="${escapeHtml(place.id)}">Go</button>`}</div>`).join('')}</div>`)}${card('Current region', `<div class="eyebrow">${escapeHtml(label(state.world_state?.current_region || ''))}</div><p class="card-copy" style="margin-top:9px">${escapeHtml(regions.find((item) => item.current)?.description || 'Set out from your home region.')}</p>${(() => { const local = regions.find((item) => item.current)?.local_state || {}; return `<div class="region-meters">${[['security', 'Security'], ['prosperity', 'Prosperity'], ['public_trust', 'Public trust']].map(([key, name]) => `<div class="region-meter"><div><span>${name}</span><b>${escapeHtml(local[key] ?? 50)}</b></div><div class="bar-track"><div class="bar-fill" style="width:${clamp(local[key] ?? 50)}%"></div></div></div>`).join('')}</div>`; })()}<div class="attribute-tile"><div class="attribute-top">World influence</div><div class="attribute-value">${escapeHtml(state.world_influence || 0)}</div><div class="attribute-context">${escapeHtml(state.world_title || 'Unproven')}</div></div><p class="card-copy" style="margin:12px 0 0">Local prosperity shifts market prices and wages. Security and trust change through expedition choices and missions.</p></div>`)}</div>
    </div>`;
}

function chatRoster() {
  const people = state.world_people || [];
  if (!selectedChatNpc || !people.some((person) => person.id === selectedChatNpc)) selectedChatNpc = people.find((person) => person.location === state.world_location)?.id || people[0]?.id;
  return people.map((person) => `<button class="chat-select ${selectedChatNpc === person.id ? 'active' : ''}" data-select-chat="${escapeHtml(person.id)}"><span class="person-avatar">${escapeHtml(String(person.name || '?').slice(0, 1))}</span><span><span class="person-name">${escapeHtml(person.name)}</span><span class="person-role" style="display:block">${person.location === state.world_location ? 'Here · ' : `${escapeHtml(locationName(person.location))} · `}${escapeHtml(person.role)}</span></span></button>`).join('');
}

function chatContent() {
  const npc = (state.world_people || []).find((person) => person.id === selectedChatNpc);
  if (!npc) return '<div class="empty-state">No one is available to talk to yet.</div>';
  const present = npc.location === state.world_location;
  const history = npc.chat_history || [];
  const initial = history.length ? history.map((message) => `<div class="chat-bubble ${message.speaker === 'player' ? 'player' : ''}">${escapeHtml(message.text)}</div>`).join('') : `<div class="chat-bubble">${escapeHtml(npc.description || 'They look over as you approach.')}</div>`;
  const interactionButtons = (state.world_interactions || []).filter((interaction) => (!interaction.requires_role || interaction.requires_role === npc.role) && Number(player().age || 0) >= Number(interaction.min_age || 0) && (interaction.range === 'anywhere' || present)).map((interaction) => `<button class="button small" data-interact="${escapeHtml(interaction.id)}" data-npc="${escapeHtml(npc.id)}" ${state.social_actions_remaining <= 0 ? 'disabled' : ''}>${escapeHtml(interaction.label)} · social</button>`).join('');
  return `<div class="chat-header"><span>${escapeHtml(npc.name)}</span><span style="color:var(--muted);font:10px var(--sans);margin-left:8px">${escapeHtml(npc.role)} · ${present ? 'present' : `at ${escapeHtml(locationName(npc.location))}`}</span></div>
    <div class="chat-history" id="chat-history">${initial}</div>
    ${present ? `<form class="chat-compose" id="chat-form"><input type="hidden" name="npc_id" value="${escapeHtml(npc.id)}"><textarea name="message" maxlength="1200" placeholder="Talk naturally. Ask about training, their work, or what is happening..." required></textarea><button class="button primary" type="submit">Send ↗</button></form><div class="free-note">Free conversation · does not consume a personal or social action. NPC memory persists in this save.</div>` : `<div class="notice">Travel to ${escapeHtml(locationName(npc.location))} to speak face to face. ${interactionButtons}</div>`}
    ${present ? `<div class="person-actions">${interactionButtons || '<span class="free-note">No formal social actions available with this person at your age.</span>'}</div>` : ''}`;
}

function peopleCards() {
  const present = state.world_people_present || [];
  if (!present.length) return '<div class="empty-state"><strong>No one is here right now.</strong>Travel home, to the Academy, the clinic, or another village place to meet people.</div>';
  return `<div class="people-grid">${present.map((person) => `<article class="person-card"><div class="person-top"><span class="person-avatar">${escapeHtml(String(person.name || '?').slice(0, 1))}</span><div><div class="person-name">${escapeHtml(person.name)}</div><div class="person-role">${escapeHtml(person.role)} · ${escapeHtml(person.age || '?')}</div></div></div><p class="person-desc">${escapeHtml(person.description || 'A person in your life.')}</p><div class="bond-line"><span>Affinity</span><b>${escapeHtml(person.affinity || 0)}</b></div><div class="bond-bar"><div class="bond-fill" style="width:${clamp(person.affinity)}%"></div></div><div class="bond-line"><span>Trust</span><b>${escapeHtml(person.trust || 0)}</b></div><div class="bond-bar"><div class="bond-fill" style="width:${clamp(person.trust)}%"></div></div><div class="person-actions"><button class="button small" data-select-chat="${escapeHtml(person.id)}" data-open-chat>▣ Talk freely</button>${(state.world_interactions || []).filter((interaction) => (!interaction.requires_role || interaction.requires_role === person.role) && Number(player().age || 0) >= Number(interaction.min_age || 0) && (interaction.range === 'anywhere' || person.location === state.world_location)).slice(0, 2).map((interaction) => `<button class="button small" data-interact="${escapeHtml(interaction.id)}" data-npc="${escapeHtml(person.id)}" ${state.social_actions_remaining <= 0 ? 'disabled' : ''}>${escapeHtml(interaction.label)} · 1 social</button>`).join('')}</div></article>`).join('')}</div>`;
}

function renderPeople() {
  const all = state.world_people || [];
  return `${pageHeading('Relationships shape the story', 'People', 'NPCs keep their own memories. Free chat can deepen a bond or open a mission; gifts, training, and other actions use social choices.')}
    ${card('People present · ' + escapeHtml(locationName(state.world_location)), peopleCards())}
    <div class="section-label">Conversation / zero action cost</div>
    <section class="card"><div class="chat-layout"><div class="chat-roster">${chatRoster()}</div><div class="chat-window">${chatContent()}</div></div></section>
    <div class="section-label">People across your life</div><div class="notice">${all.length} persistent characters in this world pack. Travel to the location shown in their conversation roster to meet them.</div>`;
}

function rewardSummary(reward = {}) {
  const entries = [];
  if (reward.money) entries.push(`${reward.money > 0 ? '+' : ''}${reward.money} Ryo`);
  if (reward.world_influence) entries.push(`${reward.world_influence > 0 ? '+' : ''}${reward.world_influence} influence`);
  if (reward.skill_xp) for (const [key, amount] of Object.entries(reward.skill_xp)) entries.push(`+${amount} ${label(key)} XP`);
  return entries.join(' · ') || 'Experience and reputation';
}

function renderMissions() {
  const quests = state.world_quests || [];
  const cards = quests.length ? quests.slice().reverse().map((quest) => `<article class="quest-card ${quest.status === 'offered' ? 'offered' : ''}"><div class="quest-head"><div><div class="quest-name">${escapeHtml(quest.title)}</div><div class="person-role">Offered by ${escapeHtml(quest.offered_by_name || 'Village contact')} · Year ${escapeHtml(quest.created_year || 1)}</div></div><span class="quest-status">${escapeHtml(quest.status)}</span></div><p class="quest-copy">${escapeHtml(quest.briefing || quest.completion || 'A new assignment.')}</p><div class="quest-meta"><span>${escapeHtml(label(quest.objective?.type || 'objective'))}: ${escapeHtml(label(quest.objective?.target || 'Complete'))} ${quest.objective?.count > 1 ? `(${escapeHtml(quest.progress || 0)}/${escapeHtml(quest.objective.count)})` : ''}</span><span>Reward · ${escapeHtml(rewardSummary(quest.reward))}</span></div>${quest.status === 'offered' ? `<div class="quest-footer"><button class="button primary small" data-accept-quest="${escapeHtml(quest.id)}">Accept assignment</button><span class="card-copy">Accepting is free; completing it changes your world.</span></div>` : ''}${quest.status === 'accepted' ? `<div class="quest-footer"><span class="card-copy">Progress ${escapeHtml(quest.progress || 0)} / ${escapeHtml(quest.objective?.count || 1)}</span>${(state.world_people_present || []).some((npc) => npc.trust >= 15) ? `<select class="button small" data-assign-select="${escapeHtml(quest.id)}"><option value="">Delegate to trusted NPC…</option>${(state.world_people_present || []).filter((npc) => npc.trust >= 15).map((npc) => `<option value="${escapeHtml(npc.id)}">${escapeHtml(npc.name)} · trust ${escapeHtml(npc.trust)}</option>`).join('')}</select>` : ''}</div>` : ''}${quest.last_attempt ? `<div class="notice" style="margin-top:9px">${escapeHtml(quest.last_attempt)}</div>` : ''}</article>`).join('') : '<div class="empty-state"><strong>No assignments yet.</strong>Talk to an instructor, mission clerk, or another local. Ask about missions or offer help; eligible quests come from this world pack.</div>';
  return `${pageHeading('Work that changes things', 'Missions & quests', 'Assignments emerge through conversation. Your accepted missions progress through your choices, travel, and relationships.')}
    ${renderWorldOpportunities()}
    <div class="grid wide-left"><div>${card('Your assignments', `<div class="quest-grid">${cards}</div>`)}</div><div class="grid">${card('How missions work', `<div class="pack-fact"><div class="pack-fact-icon">▣</div><div><strong>Talk first</strong><small>Free conversation can surface only quests defined by the active pack. The model cannot invent rewards or rules.</small></div></div><div class="pack-fact"><div class="pack-fact-icon">⌖</div><div><strong>Do it yourself</strong><small>Visit locations, train, and interact with people to make objective progress.</small></div></div><div class="pack-fact"><div class="pack-fact-icon">♧</div><div><strong>Delegate</strong><small>Ask a trusted person nearby to take a mission. They may succeed or return with it unfinished next year.</small></div></div>`)}</div></div>`;
}

function renderVillage() {
  const orgs = state.world_organizations || [];
  const activeCareer = state.world_careers?.active || {};
  const jobs = state.world_careers?.jobs || [];
  const foundingActions = (state.world_actions || []).filter((action) => action.category === 'World Building');
  const foundingCard = foundingActions.length ? card('Found a lasting institution', `<p class="card-copy">High-impact projects need rank, power, influence, funds, and a personal action. Each founding becomes a persistent part of the world's record.</p><div class="founding-list">${foundingActions.map((action) => `<div class="founding-row"><div><strong>${escapeHtml(action.label)}</strong><small>${escapeHtml(action.description)}</small>${!action.available ? `<em>${escapeHtml(action.lock_reason || 'Requirements not met')}</em>` : ''}</div><button class="button small ${action.available ? 'primary' : ''}" data-action-id="${escapeHtml(action.id)}" ${action.available ? '' : 'disabled'}>${action.available ? `Found · ${escapeHtml(action.costs?.money || 0)} Ryo` : 'Locked'}</button></div>`).join('')}</div>`) : '';
  const orgCards = orgs.map((org) => {
    const levelIndex = clamp(org.level || 0, 0, Math.max(0, (org.levels || []).length - 1));
    return `<div class="org-card"><div class="org-icon">${org.kind === 'school' ? '▤' : org.kind === 'clan' ? '♧' : org.kind === 'team' ? '⚑' : '城'}</div><div><div class="org-name">${escapeHtml(org.name)}</div><div class="org-desc">${escapeHtml(org.description)}</div><div class="bar-track"><div class="bar-fill" style="width:${clamp((org.influence || 0) * 5)}%"></div></div></div><div class="org-level">${escapeHtml(org.influence || 0)}<small>${escapeHtml(org.levels?.[levelIndex] || 'New')}</small></div></div>`;
  }).join('');
  const jobCards = jobs.map((job) => `<div class="quest-card"><div class="quest-head"><div><div class="quest-name">${escapeHtml(job.name)}</div><div class="person-role">${escapeHtml(job.kind || 'Village work')} · ${escapeHtml(job.min_rank || 'Any rank')}</div></div><span class="quest-status">${job.available ? 'OPEN' : job.qualified ? 'ASK IN PERSON' : 'LOCKED'}</span></div><p class="quest-copy">${escapeHtml(job.description || 'A village role shaped through service and reputation.')}</p><div class="quest-meta"><span>Pay ${escapeHtml(job.pay || 0)} Ryo / shift</span><span>Work at ${escapeHtml(locationName(job.location))}</span>${job.lock_reason ? `<span>${escapeHtml(job.lock_reason)}</span>` : ''}</div><div class="quest-footer">${job.id === activeCareer.job_id ? '<span class="eyebrow">CURRENT ROLE</span>' : `<button class="button small" data-meet-npc="${escapeHtml(job.contact_id || 'mission_clerk')}" ${job.qualified ? '' : 'disabled'}>Meet hiring contact</button>`}</div></div>`).join('');
  const workButton = activeCareer.job_id ? `<button class="button primary" data-work-job ${state.world_careers?.workplace_here && state.personal_actions_remaining > 0 ? '' : 'disabled'}>Work a shift · 1 personal action</button>` : '';
  return `${pageHeading('Institutions & livelihood', 'Village life', 'Academies, clans, teams, and the village change with the standing you build. Work and promotion depend on age, rank, place, and service.', workButton)}
    <div class="grid wide-left"><div class="grid">${card('Organizations', `<div class="org-list">${orgCards}</div><p class="card-copy" style="margin-top:13px">Influence changes through pack-defined actions and mission outcomes. Organization types are modular so other worlds can replace these with schools, sects, guilds, or kingdoms.</p>`)}${foundingCard}${card('Academy & education', `<div class="profile-summary"><span class="action-icon">▤</span><div><div class="profile-primary">${escapeHtml(state.education?.status || 'Academy candidate')}</div><div class="profile-secondary">A physical place in the village, not a generic menu toggle.</div></div></div><p class="card-copy" style="margin-top:12px">Visit the Academy to study, learn techniques, meet classmates, and build an instructor relationship. The pack can later add enrollment, attendance, exams, and school-specific events.</p><button class="button ghost" data-travel-location="academy">Go to the Academy →</button>`)}</div><div class="grid">${card('Current work', activeCareer.job_id ? `<div class="eyebrow">${escapeHtml(activeCareer.title || 'Village role')}</div><div class="attribute-value">${escapeHtml(activeCareer.experience || 0)} XP</div><p class="card-copy">Promotion thresholds and pay are driven by the Naruto pack. Work when you are at the job location.</p>${workButton}` : '<div class="empty-state"><strong>No role yet</strong>Meet people and ask about work. A position opens when you meet its requirements.</div>')}${card('Village positions', jobCards || '<div class="empty-state">No positions are defined in this pack.</div>')}</div></div>`;
}

function renderMarket() {
  const shop = state.world_shop || {};
  const here = state.world_location === shop.location;
  const items = shop.items || [];
  return `${pageHeading('Trade & supplies', 'Market', `${shop.name || 'Village market'} · ${here ? 'you are here' : `visit ${locationName(shop.location)} to purchase`}`)}
    <div class="combat-banner" style="margin-bottom:16px"><div><div class="combat-label">Your funds</div><div class="card-copy">${escapeHtml(shop.economy?.prosperity ?? 50)} regional prosperity shapes local prices; wages respond to the same economy.</div></div><div class="combat-number">${escapeHtml(state.world_wallet || 0)} <span style="font-size:13px;color:var(--muted)">Ryo</span></div></div>
    ${!here ? `<div class="notice" style="margin-bottom:14px"><button class="button small" data-travel-location="${escapeHtml(shop.location)}">Travel to ${escapeHtml(shop.name || 'market')}</button> Local travel does not spend an action.</div>` : ''}
    <div class="grid three">${items.map((item) => `<article class="technique-card"><div class="tech-head"><div><div class="tech-name">${escapeHtml(item.name)}</div><div class="tech-rank">${escapeHtml(item.category || 'Supply')}</div></div><span class="action-icon">${item.category === 'Tool' ? '✣' : '◇'}</span></div><p class="tech-desc">${escapeHtml(item.description || 'A useful item for daily village life.')}</p><div class="tech-footer"><span class="combat-number" style="font-size:17px">${escapeHtml(item.price)} <small style="font-size:10px;color:var(--muted)">Ryo</small>${item.base_price !== item.price ? `<small class="market-base"> · base ${escapeHtml(item.base_price)}</small>` : ''}</span><button class="button small" data-buy-item="${escapeHtml(item.id)}" ${here && state.world_wallet >= item.price ? '' : 'disabled'}>Purchase</button></div></article>`).join('')}</div>`;
}

function renderAbilities() {
  const trees = state.world_skill_trees || [];
  const modes = Object.entries(profile().modes || {});
  const modeCards = modes.map(([id, mode]) => `<div class="mode-card ${mode.active ? 'mode-active' : ''}"><div class="mode-emblem">${mode.tree === 'sage' ? '◉' : '眼'}</div><div class="mode-body"><div class="mode-title">${escapeHtml(mode.name)}${mode.variant ? ` · ${escapeHtml(label(mode.variant))}` : ''}</div><div class="mode-meta">Tier ${escapeHtml(mode.tier || 1)}/9 · ${mode.tree === 'sage' ? `Mastery ${escapeHtml(mode.mastery || 0)} / 300 to advanced form` : 'Clan bloodline transformation'} · ${escapeHtml(mode.chakra_cost || 0)} chakra</div><div class="mode-bonus">${Object.entries(mode.bonuses || {}).map(([key, value]) => `+${escapeHtml(value)} ${escapeHtml(label(key))}`).join(' · ') || 'No stat modifiers'}</div></div><button class="button small ${mode.active ? 'primary' : ''}" data-mode-toggle="${escapeHtml(id)}" data-active="${mode.active ? 'false' : 'true'}">${mode.active ? 'Deactivate' : 'Activate'}</button></div>`).join('');
  const treeCards = trees.map((tree) => {
    const nodes = (tree.nodes || []).map((node) => `<article class="tree-node ${node.unlocked ? 'unlocked' : node.available ? 'available' : 'locked'}"><div class="tree-node-mark">${node.unlocked ? '✓' : node.available ? '◇' : '⌑'}</div><div class="tree-node-main"><div class="tree-node-top"><strong>${escapeHtml(node.name)}</strong><span>${escapeHtml(node.kind || 'Ability')} · ${escapeHtml(node.point_cost || 0)} pt</span></div><p>${escapeHtml(node.description || '')}</p>${node.lock_reason && !node.unlocked ? `<div class="tree-lock">${escapeHtml(node.lock_reason)}</div>` : ''}</div>${node.unlocked ? '<span class="tree-status">LEARNED</span>' : `<button class="button small" data-skill-node="${escapeHtml(node.id)}" ${node.available ? '' : 'disabled'}>${node.available ? 'Unlock' : 'Locked'}</button>`}</article>`).join('');
    return `<section class="tree-panel"><div class="tree-heading"><div><div class="eyebrow">${tree.id === 'sage' ? 'NATURE ENERGY / SPECIAL PATH' : 'BLOODLINE / NATURE / CLAN'}</div><h2>${escapeHtml(tree.name)}</h2><p>${escapeHtml(tree.description)}</p></div><span class="tree-glyph">${tree.id === 'sage' ? '◉' : '✥'}</span></div><div class="tree-nodes">${nodes || '<div class="empty-state">No compatible nodes in this branch.</div>'}</div></section>`;
  }).join('');
  return `${pageHeading('Choose a path, earn its requirements', 'Skill Trees', 'Nodes are pack-authored and character-specific. Unlocks cost earned skill points and one personal action; bloodline branches only appear for clans that possess them.')}
    <div class="combat-banner tree-points"><div><div class="combat-label">Unspent path points</div><div class="card-copy">Earned through training, study, and Sage practice. You have ${escapeHtml(profile().skill_points || 0)} available.</div></div><div class="combat-number">${escapeHtml(profile().skill_points || 0)}</div></div>
    ${modeCards ? card('Transformations & modes', `<div class="mode-list">${modeCards}</div><p class="card-copy">Only one mode can be active at a time. Activation spends chakra; the resulting attributes and combat power update immediately.</p>`) : card('Transformations & modes', '<div class="empty-state">No mode is awakened. Bloodline and Sage modes unlock through the trees below, not at character creation.</div>')}
    <div class="tree-stack">${treeCards || '<div class="empty-state">This pack has no skill trees yet.</div>'}</div>`;
}

function renderEquipment() {
  const items = profile().inventory || [];
  const equipped = profile().equipped || {};
  const equippedIds = new Set(Object.values(equipped));
  const slots = ['weapon', 'armor', 'tool'];
  const slotCards = slots.map((slot) => {
    const item = items.find((entry) => entry.instance_id === equipped[slot]);
    return `<div class="equipment-slot"><span class="slot-mark">${slot === 'weapon' ? '⚔' : slot === 'armor' ? '⬡' : '✣'}</span><div><div class="slot-name">${escapeHtml(label(slot))}</div><div class="slot-item">${item ? `${escapeHtml(item.name)} · Tier ${escapeHtml(item.tier || 1)}` : 'Empty slot'}</div></div></div>`;
  }).join('');
  const gearCards = items.length ? items.map((item) => {
    const isGear = String(item.category || '').toLowerCase() === 'equipment';
    const tier = Number(item.tier || 1);
    const statMods = Object.entries(item.modifiers_per_tier || {}).map(([key, value]) => `+${Number(value) * tier} ${label(key)}`);
    const skillMods = Object.entries(item.skill_modifiers_per_tier || {}).map(([key, value]) => `+${Number(value) * tier} ${label(key)} skill`);
    const mods = [...statMods, ...skillMods].join(' · ');
    const isEquipped = equippedIds.has(item.instance_id);
    const forgeReady = state.world_location === 'blacksmith' && isGear && tier < 9 && items.some((entry) => entry.id === 'iron_ingot' && Number(entry.quantity || 1) > 0);
    return `<article class="gear-card ${isEquipped ? 'gear-equipped' : ''}"><div class="gear-top"><span class="gear-icon">${isGear ? '⚒' : item.category === 'Material' ? '◆' : '▤'}</span><div><div class="gear-name">${escapeHtml(item.name)}</div><div class="gear-sub">${escapeHtml(item.category || 'Item')}${isGear ? ` · ${escapeHtml(label(item.slot || 'tool'))} · Tier ${tier}/9` : ` · Qty ${escapeHtml(item.quantity || 1)}`}</div></div><span class="tier-seal">${isGear ? `T${tier}` : 'ITEM'}</span></div><p class="card-copy">${escapeHtml(item.description || '')}</p>${mods ? `<div class="gear-mods">${escapeHtml(mods)} · +${escapeHtml(Number(item.combat_power_per_tier || 0) * tier)} power</div>` : ''}<div class="gear-actions">${isGear && !isEquipped ? `<button class="button small" data-equip-item="${escapeHtml(item.instance_id)}">Equip ${escapeHtml(label(item.slot || 'tool'))}</button>` : isEquipped ? '<span class="tree-status">EQUIPPED</span>' : ''}${isGear && tier < 9 ? `<button class="button small" data-forge-item="${escapeHtml(item.instance_id)}" ${forgeReady ? '' : 'disabled'}>Forge · 1 action</button>` : ''}</div></article>`;
  }).join('') : '<div class="empty-state"><strong>Your pack is empty.</strong>Visit a regional market for equipment, supplies, and forging materials.</div>';
  const forgeNotice = state.world_location === 'blacksmith' ? `<div class="notice">Tetsu's forge is open. Tier upgrades use one personal action, Ryo, and one ingot; Smithing skill improves the success chance. Tier 9 is the cap.${state.world_last_forge ? `<br><strong>${escapeHtml(state.world_last_forge.result)}</strong> Last attempt odds: ${escapeHtml(state.world_last_forge.chance)}%.` : ''}</div>` : `<div class="notice">Forging is performed at a regional Village Forge. <button class="button small" data-travel-location="blacksmith">Travel to the forge</button></div>`;
  return `${pageHeading('Loadout & craftsmanship', 'Equipment', 'Tiered weapons, armor, and tools affect effective attributes and combat power. Each item is persistent and individually forgeable.')}
    <div class="equipment-slots">${slotCards}</div>${forgeNotice}<div class="gear-grid">${gearCards}</div>`;
}

function renderLegacy() {
  const legacy = state.world_legacy || { generation: 1, generations: [], heirs: [] };
  const heirs = legacy.heirs || [];
  const candidates = (state.world_people || []).filter((npc) => npc.location === state.world_location && npc.role !== 'Parent' && npc.role !== 'Blacksmith' && Number(npc.age || 0) >= 18);
  const relationships = candidates.length ? candidates.map((npc) => {
    const qualifies = Number(npc.affinity || 0) >= 25 && Number(npc.trust || 0) >= 25;
    return `<div class="legacy-person"><div><strong>${escapeHtml(npc.name)}</strong><span>${escapeHtml(npc.role)} · affinity ${escapeHtml(npc.affinity || 0)} · trust ${escapeHtml(npc.trust || 0)}</span></div><button class="button small" data-heir-npc="${escapeHtml(npc.id)}" ${qualifies && Number(player().age || 0) >= 18 && state.social_actions_remaining > 0 ? '' : 'disabled'}>Start a family</button></div>`;
  }).join('') : '<div class="empty-state">Meet adult characters, build trust and affinity, and revisit them here to begin a family.</div>';
  const heirCards = heirs.length ? heirs.map((heir) => `<div class="heir-card"><div class="heir-mark">${escapeHtml(String(heir.name || '?').slice(0, 1))}</div><div class="heir-info"><strong>${escapeHtml(heir.name)}</strong><span>${escapeHtml(heir.clan?.name || 'Civilian-born')} · ${escapeHtml(heir.village?.name || 'Village')} · born Year ${escapeHtml(heir.created_year || 1)}</span><span>Child of ${escapeHtml(heir.parent_name)} and ${escapeHtml(heir.partner_name)}</span></div>${heir.status === 'available' ? `<button class="button primary small" data-continue-heir="${escapeHtml(heir.id)}" ${Number(player().age || 0) >= 18 ? '' : 'disabled'}>Continue as child</button>` : `<span class="tree-status">${escapeHtml(heir.status)}</span>`}</div>`).join('') : '<div class="empty-state">No heirs recorded. Start a family as an adult with a trusted adult partner to create a child continuation.</div>';
  const generations = (legacy.generations || []).slice().reverse().map((life) => `<div class="legacy-line"><span class="generation-mark">${escapeHtml(life.generation || '?')}</span><div><strong>${escapeHtml(life.name)}</strong><span>Generation ${escapeHtml(life.generation)} · age ${escapeHtml(life.age)} · ${escapeHtml(life.clan)} · continued as ${escapeHtml(life.continued_as)}</span></div></div>`).join('');
  return `${pageHeading('Lives end; the world carries on', 'Legacy', 'Continue through a recorded child or be reborn into a different family. New lives start with fresh personal progression while the world, timeline, and NPC memories persist.')}
    <div class="combat-banner"><div><div class="combat-label">Generation ${escapeHtml(legacy.generation || 1)}</div><div class="card-copy">Your current life is ${escapeHtml(player().name)} of the ${escapeHtml(profile().clan?.name || 'unknown')} line. New-generation transitions are available after age 18.</div></div><div class="combat-number">${escapeHtml(legacy.generation || 1)}</div></div>
    <div class="grid two legacy-columns">${card('Continue as your child', `<p class="card-copy">Your heir inherits family, village, and chakra nature. They begin as a child with new stats and random birth traits; previous NPCs retain their memories.</p><div class="heir-list">${heirCards}</div>`)}${card('Begin a family', `<p class="card-copy">This costs one social action. Both characters must be adults, present together, and have at least 25 affinity and 25 trust.</p><div class="legacy-people">${relationships}</div>`)}</div>
    <div class="grid two" style="margin-top:16px">${card('Reincarnate into another family', `<p class="card-copy">Start a new life with a different randomly selected clan, village, and nature. The new save keeps the evolved world and generation archive but not the previous character's gear or abilities.</p><button class="button primary" data-reincarnate ${Number(player().age || 0) >= 18 ? '' : 'disabled'}>Choose reincarnation</button>`)}${card('Generation archive', generations ? `<div class="legacy-timeline">${generations}</div>` : '<div class="empty-state">Your archive begins when the first generation ends.</div>')}</div>`;
}

function renderChronicle() {
  const entries = state.world_chronicle || [];
  const memories = state.memories || [];
  const all = [...entries.map((entry) => ({ year: entry.year, text: entry.text })), ...memories.map((text) => ({ year: state.year || 1, text }))].slice(-80).reverse();
  return `${pageHeading('Consequences accumulate', 'Chronicle', 'The events, decisions, and relationships that this life will carry forward.')}
    ${card('A record of this life', all.length ? `<div class="chronicle">${all.map((entry) => `<div class="chronicle-item"><div class="chronicle-year">Year ${escapeHtml(entry.year)} · Age ${escapeHtml(player().age ?? 0)}</div><div class="chronicle-copy">${escapeHtml(entry.text)}</div></div>`).join('')}</div>` : '<div class="empty-state">Your chronicle begins with your first choice.</div>')}`;
}

function renderCodex() {
  const entries = state.world_lore || [];
  return `${pageHeading('Knowledge carried by this world', 'World codex', 'A concise reference loaded from the active world pack. Local dialogue receives only entries relevant to the current place and conversation.')}
    <div class="notice" style="margin-bottom:15px">Pack context is filtered before it reaches the local model. Rules, rewards, and state transitions remain deterministic and engine-owned.</div>
    <div class="lore-grid">${entries.map((entry) => `<article class="lore-card"><div class="lore-title">${escapeHtml(entry.title)}</div><div class="lore-copy">${escapeHtml(entry.summary)}</div><div class="traits-preview">${(entry.tags || []).map((tag) => `<span class="meta-chip">${escapeHtml(label(tag))}</span>`).join('')}</div></article>`).join('')}</div>`;
}

function renderSettings() {
  return `${pageHeading('Local model & simulation', 'Settings', 'Configure an OpenAI-compatible local endpoint such as LM Studio. Dialogue is optional; simulation rules always stay local and authoritative.')}
    <div class="grid two"><div class="grid">${card('LM Studio connection', `<form id="llm-form" class="grid"><div class="field"><label for="llm-base-url">Base URL</label><input id="llm-base-url" name="base_url" value="http://127.0.0.1:1234" placeholder="http://127.0.0.1:1234"></div><div class="field"><label for="llm-model">Model ID</label><input id="llm-model" name="model" placeholder="Leave blank to use the loaded model"></div><label class="notice"><input type="checkbox" id="llm-enabled" checked> Enable model-assisted NPC dialogue. Chat falls back to local responses if disconnected.</label><div style="display:flex;gap:8px"><button class="button primary" type="submit">Save settings</button><button class="button" type="button" data-test-llm>Test connection</button></div><div id="llm-status" class="card-copy"></div></form>`)}</div><div class="grid">${card('What the model can do', `<div class="pack-fact"><div class="pack-fact-icon">▣</div><div><strong>Write character dialogue</strong><small>The model receives one NPC, a short memory slice, selected player details, nearby lore, and eligible quest IDs.</small></div></div><div class="pack-fact"><div class="pack-fact-icon">⚑</div><div><strong>Suggest a pack quest</strong><small>It may select a pre-authored quest template. The engine checks NPC role, age, duplicates, objective, and reward.</small></div></div><div class="pack-fact"><div class="pack-fact-icon">⌑</div><div><strong>Never change game rules</strong><small>It cannot invent or directly apply stats, items, techniques, events, costs, or rewards.</small></div></div>`)}</div></div>`;
}

function renderCurrentPage() {
  switch (selectedPage) {
    case 'character': return renderCharacter();
    case 'stats': return renderStats();
    case 'skills': return renderSkills();
    case 'training': return renderTraining();
    case 'jutsu': return renderTechniques();
    case 'abilities': return renderAbilities();
    case 'combat': return renderCombat();
    case 'equipment': return renderEquipment();
    case 'map': return renderMap();
    case 'people': return renderPeople();
    case 'missions': return renderMissions();
    case 'village': return renderVillage();
    case 'market': return renderMarket();
    case 'legacy': return renderLegacy();
    case 'chronicle': return renderChronicle();
    case 'codex': return renderCodex();
    case 'settings': return renderSettings();
    default: return renderLife();
  }
}

function render() {
  if (!state || !state.world_pack) return renderSetup();
  app.innerHTML = `<div class="app-shell">${navMarkup()}<div class="main-area">${shellHeader()}<main class="page-wrap">${renderVitals()}${renderCurrentPage()}</main></div></div>`;
  if (selectedPage === 'settings') loadSettings();
  if (selectedPage === 'people') scrollChatToBottom();
}

function scrollChatToBottom() {
  const history = document.getElementById('chat-history');
  if (history) history.scrollTop = history.scrollHeight;
}

async function loadSettings() {
  try {
    const result = await request('/api/get_llm_settings');
    const base = document.getElementById('llm-base-url');
    const model = document.getElementById('llm-model');
    const enabled = document.getElementById('llm-enabled');
    if (!base || !model || !enabled) return;
    base.value = result.settings?.base_url || 'http://127.0.0.1:1234';
    model.value = result.settings?.model || '';
    enabled.checked = result.settings?.enabled !== false;
  } catch { /* Settings remain editable with the defaults. */ }
}

async function init() {
  try {
    const packData = await request('/api/world/packs');
    packs = packData.packs || [];
  } catch (error) {
    app.innerHTML = `<div class="boot-screen"><div class="seal-mark">A</div><p>${escapeHtml(error.message)}. Start the Anime Sim desktop app again.</p></div>`;
    return;
  }
  try {
    const current = await request('/api/public_state');
    if (current.state?.world_pack) state = current.state;
  } catch { /* No active life: show world-pack character creation. */ }
  render();
}

app.addEventListener('click', async (event) => {
  if (event.target.id === 'mobile-scrim') {
    document.getElementById('sidebar')?.classList.remove('open');
    event.target.classList.remove('open');
    return;
  }
  const target = event.target.closest('button, [data-page]');
  if (!target) return;
  if (target.dataset.page) {
    selectedPage = target.dataset.page;
    document.getElementById('sidebar')?.classList.remove('open');
    document.getElementById('mobile-scrim')?.classList.remove('open');
    render();
    return;
  }
  if (target.hasAttribute('data-menu-toggle')) {
    document.getElementById('sidebar')?.classList.toggle('open');
    document.getElementById('mobile-scrim')?.classList.toggle('open');
    return;
  }
  if (target.hasAttribute('data-save')) return mutate('/api/world/save', {}, 'Life saved.');
  if (target.hasAttribute('data-new-life')) {
    if (confirm('Start a new life? Your current life remains saved.')) { state = null; selectedPage = 'life'; render(); }
    return;
  }
  if (target.hasAttribute('data-advance')) return mutate('/api/world/advance', {}, 'A new year begins.');
  if (target.dataset.actionId) return mutate('/api/world/action', { action_id: target.dataset.actionId }, 'Choice recorded.');
  if (target.dataset.skillNode) return mutate('/api/world/skill-tree/unlock', { node_id: target.dataset.skillNode }, 'Skill path unlocked.');
  if (target.dataset.modeToggle) return mutate('/api/world/mode/toggle', { mode_id: target.dataset.modeToggle, active: target.dataset.active === 'true' }, 'Mode state updated.');
  if (target.dataset.passiveToggle) return mutate('/api/world/technique/toggle', { technique_id: target.dataset.passiveToggle, active: target.dataset.active === 'true' }, 'Passive technique updated.');
  if (target.dataset.travelRegion) return mutate('/api/world/region', { region_id: target.dataset.travelRegion }, 'You set out on the road.');
  if (target.dataset.travelLocation) return mutate('/api/world/location', { location_id: target.dataset.travelLocation }, `You went to ${label(target.dataset.travelLocation)}.`);
  if (target.dataset.encounterChoice) return mutate('/api/world/encounter', { choice_id: target.dataset.encounterChoice }, 'Encounter resolved.');
  if (target.dataset.opportunityChoice) return mutate('/api/world/opportunity/resolve', { opportunity_id: target.dataset.opportunity, choice_id: target.dataset.opportunityChoice }, 'The choice will shape what follows.');
  if (target.dataset.combatStart) {
    selectedPage = 'combat';
    return mutate('/api/world/combat/start', { opponent_id: target.dataset.combatStart }, 'Match started.');
  }
  if (target.dataset.combatMove) return mutate('/api/world/combat/turn', { move_id: target.dataset.combatMove }, 'Combat turn resolved.');
  if (target.dataset.selectChat) {
    selectedChatNpc = target.dataset.selectChat;
    selectedPage = 'people';
    render();
    return;
  }
  if (target.dataset.interact) return mutate('/api/world/interact', { npc_id: target.dataset.npc, interaction_id: target.dataset.interact }, 'They will remember this.');
  if (target.dataset.acceptQuest) return mutate('/api/world/quest/accept', { quest_id: target.dataset.acceptQuest }, 'Assignment accepted.');
  if (target.dataset.applyJob) return mutate('/api/world/career/apply', { job_id: target.dataset.applyJob }, 'You started the position.');
  if (target.dataset.meetNpc) {
    const npc = (state.world_people || []).find((person) => person.id === target.dataset.meetNpc);
    if (!npc) return toast('That contact is not present in this world pack.', true);
    if (state.world_location !== npc.location) {
      const moved = await request('/api/world/location', { location_id: npc.location });
      state = moved.state;
    }
    selectedChatNpc = npc.id;
    selectedPage = 'people';
    render();
    toast('You are at the mission desk. Ask about work in the conversation.');
    return;
  }
  if (target.hasAttribute('data-work-job')) return mutate('/api/world/career/work', {}, 'Shift complete.');
  if (target.dataset.buyItem) return mutate('/api/world/shop/purchase', { item_id: target.dataset.buyItem }, 'Item added to your pack.');
  if (target.dataset.equipItem) return mutate('/api/world/equipment/equip', { instance_id: target.dataset.equipItem }, 'Equipment loadout updated.');
  if (target.dataset.forgeItem) return mutate('/api/world/equipment/forge', { instance_id: target.dataset.forgeItem }, 'Forging attempt resolved.');
  if (target.dataset.heirNpc) {
    const childName = prompt('Name your child:');
    if (childName?.trim()) return mutate('/api/world/legacy/family', { npc_id: target.dataset.heirNpc, child_name: childName.trim() }, 'Your family record has a new heir.');
    return;
  }
  if (target.dataset.continueHeir) {
    if (confirm('Continue this save as the selected child? The current life will be archived and the shared world will persist.')) {
      selectedPage = 'life';
      return mutate('/api/world/legacy/continue', { heir_id: target.dataset.continueHeir }, 'A new generation begins.');
    }
    return;
  }
  if (target.hasAttribute('data-reincarnate')) {
    const name = prompt('Name your new life:');
    if (name?.trim() && confirm('Begin in a different family? This creates a new save while preserving the evolving world.')) {
      selectedPage = 'life';
      return mutate('/api/world/legacy/reincarnate', { name: name.trim() }, 'Reincarnation begins in a new family.');
    }
    return;
  }
  if (target.hasAttribute('data-test-llm')) {
    const status = document.getElementById('llm-status');
    status.innerHTML = '<span class="spinner"></span> Checking local endpoint...';
    try {
      const result = await request('/api/world/llm/test', { base_url: document.getElementById('llm-base-url').value, model: document.getElementById('llm-model').value });
      status.textContent = result.message;
      toast(result.message);
    } catch (error) { status.textContent = error.message; toast(error.message, true); }
  }
});

app.addEventListener('change', async (event) => {
  const select = event.target.closest('[data-assign-select]');
  if (!select || !select.value) return;
  const questId = select.dataset.assignSelect;
  const npcId = select.value;
  if (!confirm(`Delegate this quest to ${label(npcId)}? It uses one social action and they may not succeed.`)) { select.value = ''; return; }
  await mutate('/api/world/quest/assign', { quest_id: questId, npc_id: npcId }, 'Mission delegated.');
});

app.addEventListener('submit', async (event) => {
  const form = event.target;
  if (form.id === 'new-life-form') {
    event.preventDefault();
    const values = new FormData(form);
    const packId = packs.find((pack) => pack.id === 'naruto')?.id || 'naruto';
    try {
      const result = await request('/api/world/new_game', {
        name: values.get('name'), world_pack_id: packId,
        world_options: { age: Number(values.get('age')), village: values.get('village'), clan: values.get('clan') },
      });
      state = result.state;
      selectedPage = 'life';
      render();
      toast(`A new life begins for ${state.player.name}.`);
    } catch (error) { toast(error.message, true); }
  }
  if (form.id === 'chat-form') {
    event.preventDefault();
    const values = new FormData(form);
    const message = String(values.get('message') || '').trim();
    if (!message) return;
    selectedChatNpc = String(values.get('npc_id'));
    await mutate('/api/world/chat', { npc_id: selectedChatNpc, message }, 'Message sent. No action used.');
  }
  if (form.id === 'llm-form') {
    event.preventDefault();
    await saveLLMSettings();
  }
});

async function saveLLMSettings() {
  const body = {
    base_url: document.getElementById('llm-base-url').value.trim(),
    model: document.getElementById('llm-model').value.trim(),
    enabled: document.getElementById('llm-enabled').checked,
  };
  try {
    await request('/api/save_llm_settings', body);
    toast('Local model settings saved.');
  } catch (error) { toast(error.message, true); }
}

document.addEventListener('submit', (event) => {
  if (event.target.id === 'llm-form') return;
});

app.addEventListener('click', async (event) => {
  const loadButton = event.target.closest('[data-load-game]');
  if (!loadButton) return;
  try {
    const result = await request('/api/load_game', { folder: loadButton.dataset.loadGame });
    state = result.state;
    if (!state.world_pack) throw new Error('This save belongs to the earlier life-sim prototype, not an Anime Sim world pack.');
    selectedPage = 'life';
    render();
    toast('Saved life loaded.');
  } catch (error) { toast(error.message, true); }
});

init();
