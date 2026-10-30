/* Private multi-symbol structure module. Render only after the weekly report's existing gate unlocks. */
(function () {
  'use strict';

  const PROFILE_LABELS = {
    day_2h_30m_5m: '波段链 · 日线 → 2H → 30m → 5m',
    day_1h_15m_3m: '战术链 · 日线 → 1H → 15m → 3m',
  };
  const NAV_ITEMS = [
    ['sns-overview', '总览 / 合成策略'],
    ['sns-macd', 'MACD 循环'],
    ['sns-chan', '缠论 / 素论'],
    ['sns-chanbang', '缠邦 AMA'],
    ['sns-strength', '有色强弱'],
  ];
  const CYCLE_PLAYBOOK = {
    '1': '高级别 DIF / DEA 所在零轴一侧是方向门槛；低级别同向交叉才列为触发，逆高级别零轴的交叉只按反弹或回撤处理。',
    '2': '背离必须先由价格高低点与 DIF / DEA 动能共同确认，再等待低级别分型、笔或真交叉落地；只有背离，不提前猜反转。',
    '3': '极端区只提供“可能修复”的环境。低级别出现真交叉并完成结构确认后才试单；重新跌回极端区或结构低点失效即退出。',
    '4': 'DIF 修复过半是指标位置，不等于价格完成一半涨幅。等待修复后的再次同向交叉；若修复演变成反向破位，撤销原计划。',
    '5': '持续背离可能延续很久，不凭“油条”形态摸顶抄底。顺着高级别方向等回抽，只有结构失效与低级别反向确认同时出现才转向。',
    '6': '不规则背离降低信号权重，只保留观察资格。必须等中枢、分型与相邻级别交叉给出更清楚的一致性，不把它作为独立入场依据。',
  };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const fmt = (value, digits) => {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
    const number = Number(value);
    const d = digits ?? (Math.abs(number) >= 1000 ? 0 : 2);
    return number.toLocaleString('zh-CN', { maximumFractionDigits: d, minimumFractionDigits: 0 });
  };
  const shortTime = value => value ? String(value).replace('T', ' ').slice(0, 16) : '—';
  const directionClass = value => String(value).includes('多') ? 'long' : String(value).includes('空') ? 'short' : 'neutral';
  const directionPill = value => `<span class="sns-direction ${directionClass(value)}"><i></i>${esc(value)}</span>`;
  const statusClass = value => value === '已联动' ? 'linked' : value === '候选' ? 'candidate' : 'waiting';

  function linePath(bars, key, x, y) {
    let started = false;
    return bars.map((bar, index) => {
      if (!Number.isFinite(Number(bar[key]))) return '';
      const command = started ? 'L' : 'M'; started = true;
      return `${command}${x(index).toFixed(1)},${y(Number(bar[key])).toFixed(1)}`;
    }).join(' ');
  }

  function chartSvg(bars, level, structure = {}) {
    if (!bars?.length) return '<div class="sns-empty">当前级别没有图表数据</div>';
    const W = 960, H = 456, left = 74, right = 20, top = 36, priceH = 232, macdTop = 325, macdH = 64;
    const strokes = structure.strokes || [], zones = structure.zones || [], fractals = structure.fractals || [];
    const plotW = W - left - right, step = plotW / bars.length, bodyW = Math.max(2, Math.min(6, step * .62));
    const priceValues = bars.flatMap(bar => [Number(bar.h), Number(bar.l), Number(bar.ma21), Number(bar.ma55)]).filter(Number.isFinite);
    let high = Math.max(...priceValues), low = Math.min(...priceValues);
    const padding = (high - low) * .06 || 1; high += padding; low -= padding;
    const x = index => left + step * (index + .5), y = value => top + (high - value) / (high - low) * priceH;
    const macdMax = Math.max(...bars.flatMap(bar => [Math.abs(Number(bar.dif) || 0), Math.abs(Number(bar.dea) || 0), Math.abs(Number(bar.hist) || 0)]), 1);
    const my = value => macdTop + macdH / 2 - value / macdMax * (macdH / 2 - 3);
    const grid = Array.from({ length: 5 }, (_, index) => {
      const gy = top + priceH * index / 4, value = high - (high - low) * index / 4;
      return `<line x1="${left}" y1="${gy}" x2="${W - right}" y2="${gy}" class="sns-grid"/><text x="${left - 9}" y="${gy + 4}" text-anchor="end" class="sns-axis">${fmt(value)}</text>`;
    }).join('');
    const zoneMarkup = zones.map((zone, index) => {
      const zx = left + step * zone.from_i, zw = Math.max(step, (zone.to_i - zone.from_i + 1) * step);
      const zy = y(Number(zone.high)), zh = Math.max(2, y(Number(zone.low)) - zy);
      return `<rect data-chan-zone x="${zx}" y="${zy}" width="${zw}" height="${zh}" class="sns-chan-zone"/>${index === zones.length - 1 ? `<text x="${Math.min(zx + zw - 4, W - right - 4)}" y="${zy + 15}" text-anchor="end" class="sns-zone-label">中枢候选</text>` : ''}`;
    }).join('');
    const candles = bars.map((bar, index) => {
      const up = Number(bar.c) >= Number(bar.o), cls = up ? 'up' : 'down';
      const yo = y(Number(bar.o)), yc = y(Number(bar.c));
      return `<line x1="${x(index)}" y1="${y(Number(bar.h))}" x2="${x(index)}" y2="${y(Number(bar.l))}" class="sns-wick ${cls}"/><rect x="${x(index) - bodyW / 2}" y="${Math.min(yo, yc)}" width="${bodyW}" height="${Math.max(1, Math.abs(yc - yo))}" class="sns-candle ${cls}"/>`;
    }).join('');
    const strokeMarkup = strokes.map(stroke => `<line data-chan-stroke data-direction="${esc(stroke.direction)}" x1="${x(stroke.from_i)}" y1="${y(stroke.from_p)}" x2="${x(stroke.to_i)}" y2="${y(stroke.to_p)}" class="sns-chan-stroke"/><circle cx="${x(stroke.from_i)}" cy="${y(stroke.from_p)}" r="2.6" class="sns-chan-point"/><circle cx="${x(stroke.to_i)}" cy="${y(stroke.to_p)}" r="2.6" class="sns-chan-point"/>`).join('');
    const fractalMarkup = fractals.map(fractal => {
      const fx = x(fractal.i), fy = y(fractal.price), topFractal = fractal.kind === 'top';
      const points = topFractal ? `${fx},${fy - 6} ${fx - 4},${fy + 1} ${fx + 4},${fy + 1}` : `${fx},${fy + 6} ${fx - 4},${fy - 1} ${fx + 4},${fy - 1}`;
      return `<polygon data-fractal="${topFractal ? 'top' : 'bottom'}" points="${points}" class="sns-fractal ${topFractal ? 'top' : 'bottom'}"/>`;
    }).join('');
    const hist = bars.map((bar, index) => {
      const value = Number(bar.hist) || 0, zero = my(0), vy = my(value);
      return `<rect x="${x(index) - bodyW / 2}" y="${Math.min(zero, vy)}" width="${bodyW}" height="${Math.max(1, Math.abs(vy - zero))}" class="sns-hist ${value >= 0 ? 'up' : 'down'}"/>`;
    }).join('');
    const crosses = bars.slice(1).map((bar, index) => {
      const previous = bars[index], before = Number(previous.dif) - Number(previous.dea), now = Number(bar.dif) - Number(bar.dea);
      if (!Number.isFinite(before) || !Number.isFinite(now) || before === 0 || before * now > 0) return '';
      return `<circle data-macd-cross="${now > 0 ? 'gold' : 'dead'}" cx="${x(index + 1)}" cy="${my(Number(bar.dif))}" r="3.4" class="sns-macd-cross ${now > 0 ? 'gold' : 'dead'}"/>`;
    }).join('');
    const firstDate = String(bars[0].t || '').slice(5, 10), lastDate = String(bars.at(-1).t || '').slice(5, 16), latest = bars.at(-1);
    return `<svg class="sns-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(level.label)} K线、缠论笔、中枢、均线与MACD图">
      <text x="${left}" y="19" class="sns-chart-title">${esc(level.label)} · 最近 ${bars.length} 根已收盘K线</text><text x="${W - right}" y="19" text-anchor="end" class="sns-chart-title">原算法坐标 · ${strokes.length} 笔 · ${zones.length} 个中枢候选</text>
      <g>${grid}</g><g>${zoneMarkup}</g><g>${candles}</g>
      <path d="${linePath(bars, 'ma21', x, y)}" class="sns-ma21"/><path d="${linePath(bars, 'ma55', x, y)}" class="sns-ma55"/>
      <g>${strokeMarkup}</g><g>${fractalMarkup}</g>
      <text x="${left}" y="${top + priceH + 20}" class="sns-axis">${esc(firstDate)}</text><text x="${W - right}" y="${top + priceH + 20}" text-anchor="end" class="sns-axis">${esc(lastDate)}</text>
      <text x="${left}" y="${macdTop - 8}" class="sns-chart-title">MACD (12,26,9)</text><text x="${W - right}" y="${macdTop - 8}" text-anchor="end" class="sns-axis">DIF ${fmt(latest.dif, 1)} · DEA ${fmt(latest.dea, 1)} · 柱 ${fmt(latest.hist, 1)}</text>
      <line x1="${left}" y1="${my(0)}" x2="${W - right}" y2="${my(0)}" class="sns-grid"/>
      <g>${hist}</g><path d="${linePath(bars, 'dif', x, my)}" class="sns-dif"/><path d="${linePath(bars, 'dea', x, my)}" class="sns-dea"/><g>${crosses}</g>
      <g class="sns-legend"><text x="${left}" y="422" class="sns-ma21-text">MA21</text><text x="${left + 58}" y="422" class="sns-ma55-text">MA55</text><text x="${left + 116}" y="422" class="sns-chan-text">━ 缠论笔</text><text x="${left + 202}" y="422" class="sns-zone-text">▧ 中枢候选</text><text x="${left + 304}" y="422" class="sns-fractal-text">△▽ 顶底分型</text><text x="${W - right}" y="422" text-anchor="end">笔与中枢沿用分析引擎原坐标，不作盘中预测</text>
      <text x="${left}" y="445" class="sns-dif-text">DIF</text><text x="${left + 46}" y="445" class="sns-dea-text">DEA</text><text x="${left + 98}" y="445" class="sns-macd-text">MACD柱</text><text x="${left + 180}" y="445" class="sns-macd-text">○ 交叉点</text><text x="${W - right}" y="445" text-anchor="end">红涨绿跌 · 图表只使用已收盘快照K线</text></g>
    </svg>`;
  }

  function chartTimeframeTabs(report, focused) {
    return `<div class="sns-chart-timeframes" aria-label="四级图表切换">${report.levels.map((level, index) => `<button type="button" data-chart-timeframe="${esc(level.timeframe)}" class="${focused.timeframe === level.timeframe ? 'active' : ''}"><span>0${index + 1} · ${['方向', '结构', '区域', '执行'][index]}</span><b>${esc(level.label)}</b></button>`).join('')}</div>`;
  }

  function chainMarkup(report, focused) {
    return `<div class="sns-chain">${report.levels.map((level, index) => `
      <button type="button" data-timeframe="${esc(level.timeframe)}" class="sns-chain-node ${focused.timeframe === level.timeframe ? 'active' : ''}">
        <span class="sns-node-role">0${index + 1} · ${['方向', '结构', '区域', '执行'][index]}</span>
        <span class="sns-node-title"><b>${esc(level.label)}</b>${directionPill(level.direction)}</span>
        <strong>${fmt(level.last_close)}</strong><span class="sns-node-structure">${esc(level.structure)}</span>
        <span class="sns-node-macd">${esc(String(level.macd).split('，')[0])}</span>
      </button>`).join('')}</div>`;
  }

  function macdStrategyPanel(report, focused) {
    const options = report.options_macd;
    if (!options) return '';
    const current = options.levels.find(level => level.timeframe === focused.timeframe) || options.levels.at(-1);
    const higher = options.levels[1] || options.levels[0];
    const linked = options.cycles.filter(cycle => cycle.status === '已联动').length;
    const candidates = options.cycles.filter(cycle => cycle.status === '候选').length;
    const direction = report.plan.direction;
    const trigger = direction === '多'
      ? `价格收盘突破观察触发 ${fmt(report.plan.entry)}，同时 ${focused.label} 出现有效金叉或金叉后的第一次回抽不破；若 MACD 仍在零轴下方，只按反弹仓处理，不升级为趋势仓。`
      : direction === '空'
        ? `价格收盘跌破观察触发 ${fmt(report.plan.entry)}，同时 ${focused.label} 出现有效死叉或死叉后的第一次反抽不过；若 MACD 仍在零轴上方，只按回撤仓处理，不升级为趋势仓。`
        : `高级别方向尚未统一。即使 ${focused.label} 出现交叉，也只记录为候选，等待价格与高级别零轴方向共同确认。`;
    const steps = [
      ['01 · 高级别方向过滤', `${higher.label}：${higher.zero_state}；${higher.cross_state}。零轴决定允许交易的性质，交叉只负责节奏。高级别与价格结构冲突时，不用低级别金叉 / 死叉强行反手。`],
      ['02 · 六循环联立确认', `当前 ${linked} 组已联动、${candidates} 组候选。至少要求相关循环的高级前提成立，再由相邻低级别给触发；“候选”不计入确认数量，也不代表统计胜率。`],
      ['03 · 当前级别前提', `${current.label}：${current.zero_state}；${current.cross_state}；${current.ma_state}。真交叉、风洞、推土机等形态必须服从此前提，不能脱离均线环境单独使用。`],
      ['04 · 入场触发', trigger],
      ['05 · 失效与纠错', `结构失效参考 ${fmt(report.plan.stop)}；收盘回到原结构区间、反向真交叉证伪，或右侧跟进消失，均撤销原预判。不得用下一次交叉摊平，也不把指标修复过半当成价格必然回归。`],
      ['06 · 目标与退出', `目标 1 ${fmt(report.plan.target1)}、目标 2 ${fmt(report.plan.target2)}。到目标 1 后检查中级别笔与 DIF 是否继续延伸；若动能衰减或价格回到触发区，先收缩风险。六循环互相冲突、只有低级别信号或尚未收盘确认时，处理都是不交易。`],
    ];
    return `<section class="sns-panel sns-macd-strategy" data-macd-strategy>
      <div class="sns-panel-heading"><div><span>MACD EXECUTION PLAYBOOK</span><h3>MACD 独立策略 · 从零轴过滤到纠错退出</h3></div>${directionPill(direction)}</div>
      <p class="sns-intro">MACD 不单独预测价格：零轴和高级别结构决定“能不能做”，六循环决定“是否联动”，低级别真交叉与价格收盘共同决定“何时做”。</p>
      <div class="sns-playbook-grid">${steps.map(([title, text]) => `<article><h4>${esc(title)}</h4><p>${esc(text)}</p></article>`).join('')}</div>
    </section>`;
  }

  function macdPanel(report, focused) {
    const options = report.options_macd;
    if (!options) return '';
    const current = options.levels.find(level => level.timeframe === focused.timeframe);
    return `<section class="sns-panel sns-macd-panel" id="sns-macd" data-private-theory="macd">
      <div class="sns-panel-heading"><div><span>MACD CYCLE · SIX LINKED LOOPS</span><h3>MACD 循环 · 六组多级别联立</h3></div><b>六循环</b></div>
      <p class="sns-intro">零轴传导看方向，背离共振看动能衰减，AV 与过半修复看反转节奏，油条与茄子看特殊背离。逐对检查相邻级别；高级别前提未成立时，低级别形态只列为候选。</p>
      <div class="sns-cycle-grid">${options.cycles.map(cycle => `<article class="sns-cycle-card">
        <div><span>循环 ${esc(cycle.id)} · ${esc(cycle.higher)} → ${esc(cycle.lower)}</span><b class="sns-cycle-status ${statusClass(cycle.status)}">${esc(cycle.status)}</b></div>
        <h4>${esc(cycle.title)}</h4><p>${esc(cycle.evidence)}</p>
        <div class="sns-cycle-action"><b>策略含义</b><p>${esc(CYCLE_PLAYBOOK[String(cycle.id)] || '仅在高级别前提与低级别触发同时成立时使用；冲突则等待。')}</p></div>
        <details><summary>原规则与三组级别证据</summary><p>${esc(cycle.original_rule)}</p>${cycle.links.map(link => `<div class="sns-cycle-link"><b>${esc(link.higher)} → ${esc(link.lower)} · ${esc(link.status)}</b><p>${esc(link.evidence)}</p></div>`).join('')}</details>
      </article>`).join('')}</div>
      ${current ? `<div class="sns-special-grid"><article><span>AV / 1/2</span><b>${esc(current.overbought_oversold)}</b><p>${esc(current.half_position)}</p></article><article><span>风洞</span><b>${esc(current.wind_tunnel.kind || current.wind_tunnel.state || '等待形态')}</b><p>${esc(current.wind_tunnel.text)}</p></article><article><span>推土机</span><b>${esc(current.bulldozer.kind || current.bulldozer.state || '等待均线环境')}</b><p>${esc(current.bulldozer.text)}</p></article><article><span>真交叉与纠错</span><b>${esc(current.true_cross)}</b><p>${esc(current.correction)}</p></article></div>` : ''}
      <p class="sns-method-note">${esc(options.proxy_note)} ${esc(options.source_note)}</p>
    </section>${macdStrategyPanel(report, focused)}`;
  }

  function theoryManual(kind, report, focused) {
    const execution = report.levels.at(-1);
    const zone = focused.zone ? `${fmt(focused.zone[0])}–${fmt(focused.zone[1])}` : '尚未形成稳定中枢';
    const items = kind === 'chan' ? [
      ['① 先定高级别笔的方向', `先读日线与中级别，不用 ${execution.label} 的一笔逆转直接推断大级别反转。高级别向上时优先等向下笔结束后的多头机会，高级别向下时反之。`],
      ['② 用中枢界定战场', `${focused.label} 当前中枢候选为 ${zone}。中枢是多空反复成交区，不是必然支撑或压力；先等价格有效离开，再观察第一次回抽是否重新回到中枢。`],
      ['③ 分型、笔与素论动力确认', `离开中枢后，等顶 / 底分型完成和新笔形成；素论动力用于检查离开段是否仍有延伸力量。分型未完成、回抽重回中枢或动能明显反向时，只保留候选。`],
      ['④ 低级别执行与退出', `最终由 ${execution.label} 收盘确认，观察触发 ${fmt(report.plan.entry)}、结构失效 ${fmt(report.plan.stop)}。到目标后看中级别笔是否延伸；若回抽失败、收盘回到原区间或止损被穿越，退出而不补仓。`],
    ] : [
      ['① 先判断 AMA 环境', `当前 ${focused.ama_context || 'AMA 环境仍待确认'}。AMA 向上且价格保持其上，只优先寻找类二买；AMA 向下且价格保持其下，只优先寻找类二卖；缠绕时降低仓位预期或不交易。`],
      ['② 等类一 / 类二买卖位置', `类一信号负责提示原有趋势可能衰竭，类二信号负责确认回测试错位置。没有高低点、分型与 AMA 配合时，不把单次碰线当成买卖点。`],
      ['③ 上下级共同触发', `中级别负责环境，${execution.label} 负责入场。当前执行提示：${focused.entry_signal || '等待上下级确认'}。只有低级别收盘突破观察位且 AMA 未反向破坏，信号才从候选升级为可执行。`],
      ['④ 撤销与退出', `若价格重新穿越 AMA 并收回原结构、类二回抽失败或触及 ${fmt(report.plan.stop)}，撤销信号。目标 1 / 目标 2 分别为 ${fmt(report.plan.target1)} / ${fmt(report.plan.target2)}，到达后仍需看中级别环境，不机械猜顶底。`],
    ];
    return `<div class="sns-theory-manual" data-theory-manual="${kind}"><h4>${kind === 'chan' ? '缠论 / 素论 · 四步执行手册' : '缠邦 AMA · 四步执行手册'}</h4><div>${items.map(([title, text]) => `<article><b>${esc(title)}</b><p>${esc(text)}</p></article>`).join('')}</div></div>`;
  }

  function theoryPanel(report, focused, kind) {
    const isChan = kind === 'chan';
    const blocks = focused.structure_blocks.filter(block => isChan ? /^(③|④|⑤|⑨)/.test(block.title) : /^⑧/.test(block.title));
    return `<section class="sns-panel" id="${isChan ? 'sns-chan' : 'sns-chanbang'}" data-private-theory="${kind}">
      <div class="sns-panel-heading"><div><span>${isChan ? 'CHAN × SU · RECURSIVE STRUCTURE' : 'CHANBANG · AMA ENVIRONMENT'}</span><h3>${isChan ? '缠论 / 素论 · 结构与动力' : '缠邦 · AMA 六零线与类一 / 类二买卖'}</h3></div><b>${esc(focused.label)}</b></div>
      <p class="sns-intro">${isChan ? '缠论用分型—笔—中枢递归描述价格结构，素论补充动力与延续性判断。本页笔和中枢直接沿用分析引擎坐标；先确认结构完成，再讨论交易，不用未完成分型预测未来。' : '缠邦以 AMA 六零线识别趋势环境，再用类一 / 类二买卖组织回测试错。它解决的是“在哪种环境下做、回抽失败在哪里退出”，不是用一条均线替代全部结构。'}</p>
      <div class="sns-theory-focus"><div><span>${isChan ? '当前结构' : 'AMA 环境'}</span><h4>${esc(isChan ? focused.structure : focused.ama_context || '等待 AMA 环境确认')}</h4><p>${esc(isChan ? focused.chan : focused.entry_signal || '等待上下级确认')}</p></div><div class="sns-theory-facts"><span>最近${focused.latest_fractal_kind === 'top' ? '顶' : '底'}分型 <b>${fmt(focused.latest_fractal_price)}</b></span><span>中枢候选 <b>${focused.zone ? `${fmt(focused.zone[0])} – ${fmt(focused.zone[1])}` : '暂未形成'}</b></span><span>AMA <b>${fmt(focused.ama)}</b></span></div></div>
      ${theoryManual(kind, report, focused)}
      <div class="sns-evidence-grid">${blocks.map(block => `<article><h4>${esc(block.title)}</h4><ul>${block.items.map(item => `<li>${esc(item)}</li>`).join('')}</ul></article>`).join('') || '<p class="sns-empty">该级别暂无可展开证据。</p>'}</div>
    </section>`;
  }

  function signedPercent(value) {
    return `<span class="${Number(value) > 0 ? 'sns-positive' : Number(value) < 0 ? 'sns-negative' : ''}">${Number(value) > 0 ? '+' : ''}${fmt(value, 2)}%</span>`;
  }

  function unifiedStrategyPanel(report) {
    const [higher, middle, setup, execution] = report.levels;
    const linked = report.options_macd?.cycles.filter(cycle => cycle.status === '已联动').length || 0;
    const candidates = report.options_macd?.cycles.filter(cycle => cycle.status === '候选').length || 0;
    const sameDirection = higher.direction === middle.direction && ['多', '空'].includes(higher.direction);
    const posture = sameDirection
      ? `${higher.label}与${middle.label}同为${higher.direction}头，只顺着高级别方向等待低级别触发。`
      : '高低级别尚未形成同向过滤，不把次级别信号直接升级为趋势交易。';
    const risk = Math.abs(Number(report.plan.entry) - Number(report.plan.stop));
    const theories = [
      ['道氏 · 高级别定势', higher.dow, `方向过滤采用${higher.label}与${middle.label}；当前结论为${higher.direction} / ${middle.direction}。`],
      ['价格行为 · 区域确认', setup.price_action, `执行前必须等待${execution.label}收盘确认，盘中穿越不单独构成入场。`],
      ['缠论 / 素论 · 中枢与分型', setup.structure, setup.zone ? `当前中枢候选 ${fmt(setup.zone[0])}–${fmt(setup.zone[1])}；离开与回抽共同确认，不凭单一分型预测。` : '当前没有稳定中枢候选，降低结构信号权重。'],
      ['MACD 六循环 · 动能过滤', report.options_macd?.summary || report.alignment, `六循环中 ${linked} 组已联动、${candidates} 组候选；候选不当作已确认。`],
      ['缠邦 · AMA 环境', middle.ama_context || '等待 AMA 环境确认', setup.entry_signal || '等待类一 / 类二与上下级共同确认。'],
      ['KDJ / ATR · 节奏与风控', `${execution.kdj}；执行级别 ATR ${fmt(execution.atr)}。`, '止损由结构失效与波动共同约束，失效后不摊平，不把小级别逆势信号当作加仓理由。'],
    ];
    return `<section class="sns-panel sns-plan-panel sns-unified-strategy" id="sns-overview" data-unified-strategy>
      <div class="sns-panel-heading"><div><span>UNIFIED THEORY STRATEGY</span><h3>全理论合成策略 · 先过滤，再触发</h3></div>${directionPill(report.plan.direction)}</div>
      <div class="sns-strategy-call"><div><span>当前操作状态</span><h4>${esc(report.plan.status)}</h4><p>${esc(posture)} ${esc(report.plan.why)}</p></div><div class="sns-strategy-bias"><span>合成方向</span><b>${esc(report.plan.direction)}</b><small>规则合成 · 非胜率</small></div></div>
      <div class="sns-theory-votes">${theories.map(([name, evidence, action]) => `<article><h4>${esc(name)}</h4><p>${esc(evidence)}</p><span>${esc(action)}</span></article>`).join('')}</div>
      <div class="sns-execution-box"><div><h4>执行条件 · 未触发就等待</h4><ol>${report.plan.conditions.map(item => `<li>${esc(item)}</li>`).join('')}</ol></div><div class="sns-price-plan"><span>观察触发 <b>${fmt(report.plan.entry)}</b></span><span>结构失效 <b>${fmt(report.plan.stop)}</b></span><span>目标1 · 1R <b>${fmt(report.plan.target1)}</b></span><span>目标2 · 2R <b>${fmt(report.plan.target2)}</b></span></div></div>
      <div class="sns-risk-box"><h4>风险预算与三种后续处理</h4><p><b>1R = |观察触发 − 结构失效| = ${fmt(risk)} 个报价单位。</b>在不知道合约乘数与你的单笔风险预算前，不换算具体手数；计算时应使用“单笔可承受亏损 ÷（1R × 合约乘数＋单手交易成本）”，并向下取整。</p><ol>${report.scenarios.map(item => `<li>${esc(item)}</li>`).join('')}</ol><p class="sns-untriggered">若价格从未触发、信号在收盘前消失，或六循环与结构方向冲突，本策略保持未执行状态；不因为“快到了”而提前入场。</p></div>
      <p class="sns-method-note">合成原则：高级别方向 > 中枢与价格区域 > MACD / AMA 过滤 > 低级别收盘触发。任何单一理论与其他证据冲突时，以等待和缩小风险为默认处理。</p>
    </section>`;
  }

  function strengthGroup(rows, kind, title) {
    const strongest = rows[0], weakest = rows.at(-1);
    const maxAbs = Math.max(...rows.map(row => Math.abs(row.score)), 1);
    const positives = rows.filter(row => row.score > 0).length, negatives = rows.filter(row => row.score < 0).length;
    return `<div class="sns-relative-group" data-strength-group="${kind}">
      <div class="sns-relative-group-title"><h4>${esc(title)}</h4><span>${esc(shortTime(strongest.as_of))} 截止</span></div>
      <div class="sns-relative-summary"><b>${esc(strongest.name)}相对最强 · ${esc(weakest.name)}相对最弱</b><p>正动量 ${positives} 个、负动量 ${negatives} 个；${negatives === rows.length ? '组内全部为负，排名第一不等于绝对做多信号。' : '排名只描述相对动量，仍需回到各自结构确认方向。'}</p></div>
      <div class="sns-relative-bars">${rows.map(row => {
        const width = Math.abs(row.score) / maxAbs * 50;
        const style = row.score >= 0 ? `left:50%;width:${width}%` : `left:${50 - width}%;width:${width}%`;
        return `<div class="sns-relative-row"><span><b>${row.rank}</b>${esc(row.name)}<small>${esc(row.group)}</small></span><div class="sns-relative-track"><i></i><em class="${row.score >= 0 ? 'positive' : 'negative'}" style="${style}"></em></div><strong>${signedPercent(row.score)}</strong></div>`;
      }).join('')}</div>
      <div class="sns-relative-table-wrap"><table class="sns-relative-table"><thead><tr><th>排名 / 品种</th><th>5根日K</th><th>20根日K</th><th>60根日K</th><th>综合动量</th><th>均线环境</th><th>结构参考</th></tr></thead><tbody>${rows.map(row => `<tr><td><b>${row.rank} · ${esc(row.name)}</b><small>${esc(row.group)}</small></td><td>${signedPercent(row.returns['5'])}</td><td>${signedPercent(row.returns['20'])}</td><td>${signedPercent(row.returns['60'])}</td><td><b>${signedPercent(row.score)}</b></td><td>${esc(row.trend)}</td><td>${esc(row.structure)}</td></tr>`).join('')}</tbody></table></div>
      <p class="sns-group-source">来源：${esc(strongest.source)} · 截止 ${esc(shortTime(strongest.as_of))}</p>
    </div>`;
  }

  function relativeStrengthPanel() {
    const data = window.TIN_RELATIVE_STRENGTH;
    if (!data?.nonferrous_rows?.length) return '';
    return `<section class="sns-panel sns-relative-panel" id="sns-strength" data-relative-strength>
      <div class="sns-panel-heading"><div><span>NONFERROUS UNIVERSE × PRECIOUS REFERENCE</span><h3>有色整体强弱 · 六大基本金属主连</h3></div><b>6 个有色 + 2 个贵金属</b></div>
      <p class="sns-intro">先比较铜、铝、锌、铅、镍、锡的有色内部动量，再把黄金、白银单独作为跨板块参照；不同分组不混排名。</p>
      ${strengthGroup(data.nonferrous_rows, 'nonferrous', '有色整体 · 铜 / 铝 / 锌 / 铅 / 镍 / 锡')}
      ${strengthGroup(data.precious_rows, 'precious', '贵金属参考 · 黄金 / 白银')}
      <p class="sns-method-note">${esc(data.formula)}。${esc(data.note)} 强弱比较不使用不同品种的价格、ATR 或 MACD 原始值直接相比。</p>
    </section>`;
  }

  function refreshFeedback(root, message, kind = '') {
    const element = root.querySelector('[data-refresh-feedback]');
    if (!element) return;
    element.hidden = !message;
    element.className = `sns-refresh-feedback ${kind}`;
    element.textContent = message;
  }

  async function refreshData(root, state) {
    const button = root.querySelector('[data-refresh-data]');
    if (!button || button.disabled) return;
    if (!['localhost', '127.0.0.1', '::1'].includes(location.hostname)) {
      refreshFeedback(root, '线上静态页不能读取你电脑中的通达信文件。请打开本机预览，再点击“更新盘后数据”。', 'warning');
      return;
    }
    button.disabled = true;
    button.textContent = '正在更新…';
    refreshFeedback(root, '正在复算主连双链并生成网页快照，通常需要几分钟；请勿重复点击。', 'running');
    try {
      const response = await fetch('/api/refresh-structures', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Tin-Refresh': 'after-hours' },
        body: '{}',
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || '更新接口未成功返回');
      await new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = `./tin_structure_data.js?refresh=${Date.now()}`;
        script.onload = resolve;
        script.onerror = () => reject(new Error('新数据已生成，但网页脚本加载失败；请刷新页面重试。'));
        document.head.appendChild(script);
      });
      render(root, state);
      refreshFeedback(root, `${result.message} 图表与策略已切换到新快照。`, 'success');
    } catch (error) {
      refreshFeedback(root, `${error.message || '更新失败'}；当前页面保留上一成功数据。`, 'error');
    } finally {
      const currentButton = root.querySelector('[data-refresh-data]');
      if (currentButton) { currentButton.disabled = false; currentButton.textContent = '↻ 更新盘后数据'; }
    }
  }

  function payloadFor(state) {
    return window.TIN_MARKET_DATA?.[`${state.symbol}__${state.profile}`]
      || (state.symbol === '30_SNL8' ? window.TIN_STRUCTURE_DATA?.[state.profile] : null);
  }

  function render(root, state) {
    const catalog = window.TIN_MARKET_CATALOG || [];
    const selected = catalog.find(item => item.symbol === state.symbol) || catalog[0];
    if (selected && !selected.profiles.includes(state.profile)) state.profile = selected.profiles[0];
    const payload = payloadFor(state);
    if (!payload) { root.innerHTML = '<div class="sns-error">当前主连快照未加载，请重新运行盘后数据嵌入。</div>'; return; }
    const report = payload.report;
    if (!report.levels.some(level => level.timeframe === state.timeframe)) state.timeframe = report.levels.at(-1).timeframe;
    const focused = report.levels.find(level => level.timeframe === state.timeframe) || report.levels.at(-1);
    const bars = payload.charts[focused.timeframe] || [];
    const symbolName = selected?.name || '沪锡';
    const availableProfiles = selected?.profiles || Object.keys(PROFILE_LABELS);
    root.innerHTML = `<div class="sns-shell">
      <nav class="sns-section-nav" aria-label="技术分析板块导航">${NAV_ITEMS.map(([id, label]) => `<button type="button" data-nav="${id}">${label}</button>`).join('')}<button type="button" class="sns-all-market" data-workspace="${state.workspace === 'market' ? 'tin' : 'market'}">${state.workspace === 'market' ? '返回沪锡主报告' : `全品种技术分析 · ${catalog.length}`}</button></nav>
      <section class="sns-hero"><div><span class="sns-kicker">PRIVATE · TDX AFTER-HOURS STRUCTURE</span><h3>${esc(symbolName)}主连 · 结构联立</h3><p>高级别定方向，低级别找触发；价格结构先行，指标只做验证。${state.workspace === 'market' ? ' 全品种仅展示已就绪主连快照，不混入具体月份合约。' : ''}</p></div><div class="sns-private-stamp"><b>私享</b><span>${esc(report.data_source.mode === 'local_only' ? '通达信本地K线' : '本地＋补线')}</span></div></section>
      ${state.workspace === 'market' ? `<section class="sns-market-workspace" data-market-workspace><div><span>MULTI-SYMBOL MAIN CONTINUOUS</span><h3>全品种主连工作台</h3><p>${catalog.length} 个已就绪主连 · 每个品种只显示实际可用的联立链和四级图表</p></div><div class="sns-market-tabs">${catalog.map(item => `<button type="button" data-symbol="${esc(item.symbol)}" class="${state.symbol === item.symbol ? 'active' : ''}"><b>${esc(item.name)}</b><span>${item.profiles.length} 条链</span></button>`).join('')}</div></section>` : `<button type="button" class="sns-market-entry" data-workspace="market"><span>独立入口</span><b>全品种技术分析</b><em>${catalog.length} 个已就绪主连 →</em></button>`}
      <div class="sns-toolbar"><div class="sns-profile-tabs">${availableProfiles.map(key => `<button type="button" data-profile="${key}" class="${state.profile === key ? 'active' : ''}">${PROFILE_LABELS[key]}</button>`).join('')}</div><div class="sns-data-actions"><button type="button" class="sns-refresh-data" data-refresh-data title="读取已下载的通达信K线，复算主连并刷新本页">↻ 更新盘后数据</button><span>快照截至 <b>${shortTime(report.data_cutoff)}</b></span></div></div>
      <div class="sns-refresh-feedback" data-refresh-feedback hidden></div>
      <div class="sns-warning">这是已收盘K线生成的结构快照，不是实时交易指令。更新按钮只读取已下载数据，不会替你启动通达信下载。</div>
      ${chainMarkup(report, focused)}
      <section class="sns-panel sns-chart-panel"><div class="sns-panel-heading"><div><span>PRICE × CHAN × MACD</span><h3>${esc(symbolName)}主连 · ${esc(focused.label)} K线 / 缠论笔 / 中枢 / MACD</h3></div>${directionPill(focused.direction)}</div>${chartTimeframeTabs(report, focused)}<div class="sns-chart-wrap">${chartSvg(bars, focused, payload.structures?.[focused.timeframe])}</div></section>
      ${unifiedStrategyPanel(report)}
      ${macdPanel(report, focused)}
      ${theoryPanel(report, focused, 'chan')}
      ${theoryPanel(report, focused, 'chanbang')}
      ${relativeStrengthPanel()}
      <section class="sns-panel"><div class="sns-panel-heading"><div><span>SOURCE & LIMITS</span><h3>数据来源与使用边界</h3></div><b>非胜率</b></div><div class="sns-source-grid"><div><p>${esc(report.data_source.message)}</p><span>本地分钟截止 <b>${shortTime(report.data_source.local_latest)}</b></span><span>远端补线截止 <b>${shortTime(report.data_source.remote_latest)}</b></span></div><div class="sns-source-rules"><b>盘后使用顺序</b><p>先刷新主连数据，再复算两条联立链，最后嵌入私享页。具体月份合约不进入本工作台；缺少快照的品种不会被伪装成已覆盖。</p></div></div><p class="sns-method-note">${esc(report.warning)}</p></section>
      <div class="sns-legacy-divider"><span>以下保留原锡研究日报指标体系</span></div>
    </div>`;
  }

  function mount(root) {
    if (!root || root.dataset.mounted === 'true') return;
    if (!window.TIN_STRUCTURE_DATA || !window.TIN_MARKET_CATALOG?.length) {
      root.innerHTML = '<div class="sns-error">主连联立快照未加载，请检查 tin_structure_data.js。</div>'; return;
    }
    const state = { symbol: '30_SNL8', profile: 'day_2h_30m_5m', timeframe: '5m', workspace: 'tin' };
    root.dataset.mounted = 'true';
    root.addEventListener('click', event => {
      const refresh = event.target.closest('[data-refresh-data]');
      const workspace = event.target.closest('[data-workspace]');
      const nav = event.target.closest('[data-nav]');
      const symbol = event.target.closest('[data-symbol]');
      const profile = event.target.closest('[data-profile]');
      const timeframe = event.target.closest('[data-timeframe], [data-chart-timeframe]');
      if (refresh) {
        refreshData(root, state);
      } else if (workspace) {
        state.workspace = workspace.dataset.workspace;
        render(root, state);
        root.querySelector('.sns-section-nav')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else if (symbol) {
        state.symbol = symbol.dataset.symbol;
        const selected = window.TIN_MARKET_CATALOG.find(item => item.symbol === state.symbol);
        state.profile = selected.profiles.includes(state.profile) ? state.profile : selected.profiles[0];
        state.timeframe = payloadFor(state).report.levels.at(-1).timeframe;
        render(root, state);
      } else if (profile) {
        state.profile = profile.dataset.profile;
        state.timeframe = payloadFor(state).report.levels.at(-1).timeframe;
        render(root, state);
      } else if (timeframe) {
        state.timeframe = timeframe.dataset.chartTimeframe || timeframe.dataset.timeframe;
        render(root, state);
        root.querySelector('.sns-chart-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else if (nav) {
        root.querySelector(`#${nav.dataset.nav}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
    render(root, state);
  }

  window.TinStructure = { mount };
})();
