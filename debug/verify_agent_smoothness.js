const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  await page.goto("http://127.0.0.1:8789/agent_viewer.html", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__sim && window.__sim.step === 0, null, { timeout: 5000 });
  await page.click("#playBtn");
  await page.waitForFunction(() => window.__sim && window.__sim.step >= 1, null, { timeout: 5000 });

  const samples = [];
  const start = Date.now();
  while (Date.now() - start < 3200) {
    const sample = await page.evaluate(() => {
      const agent = (window.__sim?.agents || []).find((item) => item.context?.phase === "MOVING")
        || (window.__sim?.agents || [])[0];
      if (!agent) return null;
      const point = window.agentRenderPoint(agent, performance.now());
      const animation = window.__agentAnimations?.get(String(agent.id));
      return {
        t: performance.now(),
        step: window.__sim.step,
        id: agent.id,
        phase: agent.context.phase,
        x: point?.x,
        y: point?.y,
        duration: animation?.duration,
        remaining: animation ? Math.max(0, animation.startTime + animation.duration - performance.now()) : null,
      };
    });
    samples.push(sample);
    await page.waitForTimeout(100);
  }

  await page.click("#playBtn");
  await browser.close();

  let zeroMoves = 0;
  let maxZeroRun = 0;
  let currentZeroRun = 0;
  const rows = [];
  for (let index = 1; index < samples.length; index += 1) {
    const prev = samples[index - 1];
    const next = samples[index];
    const move = prev && next && Number.isFinite(prev.x) && Number.isFinite(next.x)
      ? Math.hypot(next.x - prev.x, next.y - prev.y)
      : 0;
    if (move < 0.05) {
      zeroMoves += 1;
      currentZeroRun += 1;
      maxZeroRun = Math.max(maxZeroRun, currentZeroRun);
    } else {
      currentZeroRun = 0;
    }
    rows.push({
      index,
      step: next?.step,
      move,
      duration: next?.duration || 0,
      remaining: next?.remaining || 0,
      x: next?.x || 0,
      y: next?.y || 0,
    });
  }

  console.log(`samples=${samples.length} zero_moves=${zeroMoves} max_zero_run=${maxZeroRun}`);
  for (const row of rows) {
    console.log(
      `${String(row.index).padStart(2, "0")} step=${row.step} move=${row.move.toFixed(2)} `
      + `duration=${row.duration.toFixed(0)} remaining=${row.remaining.toFixed(0)} `
      + `x=${row.x.toFixed(1)} y=${row.y.toFixed(1)}`
    );
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
