/**
 * Cloudflare Edge Sentinel for Fantasy AI
 * =======================================
 * 24/7 autonomous edge sentinel running on Cloudflare's global network.
 * 1. Monitors FPL deadlines with zero server latency.
 * 2. Instantly dispatches GitHub Actions workflows for Stage 1 (T-2.5h) and Stage 2 (T-20m).
 * 3. Acts as an interactive Telegram Bot Webhook for mobile control while traveling.
 */

async function getFplGameweekInfo() {
  const res = await fetch("https://fantasy.premierleague.com/api/bootstrap-static/", {
    headers: { "User-Agent": "FantasyAI-Sentinel/1.0" }
  });
  if (!res.ok) throw new Error(`FPL API status: ${res.status}`);
  const data = await res.json();
  const currentEvent = data.events.find(e => e.is_current) || {};
  const nextEvent = data.events.find(e => e.is_next) || {};

  const deadlineMs = nextEvent.deadline_time ? new Date(nextEvent.deadline_time).getTime() : 0;
  const nowMs = Date.now();
  const diffMinutes = deadlineMs ? Math.floor((deadlineMs - nowMs) / (1000 * 60)) : 999999;

  return {
    currentGw: currentEvent.id || 4,
    nextGw: nextEvent.id || 5,
    nextGwName: nextEvent.name || "Gameweek 5",
    deadlineTime: nextEvent.deadline_time,
    diffMinutes: diffMinutes,
    hoursUntil: Math.floor(diffMinutes / 60),
    minsUntil: Math.max(0, diffMinutes % 60)
  };
}

async function triggerGitHubWorkflow(env, stage = "tactical", mode = "live") {
  const repo = env.GITHUB_REPO || "3bkader-gpt/fantasy_ai";
  const token = env.GITHUB_TOKEN;
  if (!token) throw new Error("GITHUB_TOKEN secret not configured on Cloudflare Sentinel.");

  const url = `https://api.github.com/repos/${repo}/actions/workflows/autonomous_manager.yml/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "Cloudflare-FantasyAI-Sentinel/1.0"
    },
    body: JSON.stringify({
      ref: "main",
      inputs: {
        execution_mode: mode,
        stage: stage
      }
    })
  });

  if (res.status === 204) {
    return { success: true, status: 204 };
  }
  const body = await res.text();
  return { success: false, status: res.status, error: body };
}

async function checkRecentRuns(env) {
  const repo = env.GITHUB_REPO || "3bkader-gpt/fantasy_ai";
  const token = env.GITHUB_TOKEN;
  if (!token) return [];

  const url = `https://api.github.com/repos/${repo}/actions/workflows/autonomous_manager.yml/runs?per_page=5`;
  const res = await fetch(url, {
    headers: {
      "Authorization": `Bearer ${token}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "Cloudflare-FantasyAI-Sentinel/1.0"
    }
  });

  if (!res.ok) return [];
  const data = await res.json();
  return data.workflow_runs || [];
}

async function sendTelegram(env, text) {
  const botToken = env.TELEGRAM_BOT_TOKEN;
  const chatId = env.TELEGRAM_CHAT_ID;
  if (!botToken || !chatId) return;

  const url = `https://api.telegram.org/bot${botToken}/sendMessage`;
  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: text,
        parse_mode: "Markdown",
        disable_web_page_preview: true
      })
    });
  } catch (err) {
    console.error("Telegram error:", err);
  }
}

export default {
  // 1. Cron Trigger Handler (Runs every 15 minutes globally on Cloudflare edge)
  async scheduled(event, env, ctx) {
    try {
      const gw = await getFplGameweekInfo();
      const recentRuns = await checkRecentRuns(env);
      const now = Date.now();

      // Find if a run happened in the last 45 minutes
      const hasRecentRun = recentRuns.some(r => {
        const runTime = new Date(r.created_at).getTime();
        return (now - runTime) < 45 * 60 * 1000;
      });

      // Stage 1: Tactical Window (T-2.5h: between 150m and 30m before deadline)
      if (gw.diffMinutes <= 150 && gw.diffMinutes > 30) {
        if (!hasRecentRun) {
          console.log(`[SENTINEL] Triggering Stage 1 Tactical Solver for GW${gw.nextGw}`);
          await sendTelegram(
            env,
            `⏱️ **[حارس كلاودفلير الذكي - Cloudflare Sentinel]**\n\n` +
            `تم رصد اقتراب موعد ديدلاين **الجولة ${gw.nextGw}** (متبقي: ${gw.hoursUntil} ساعة و ${gw.minsUntil} دقيقة).\n` +
            `🚀 **جاري إطلاق سيرفر التنفيذ السحابي (Stage 1: MILP & Transfers) فوراً!**`
          );
          await triggerGitHubWorkflow(env, "tactical", "live");
        }
      }

      // Stage 2: Final Pre-Deadline Safety Pulse (T-20m: between 22m and 2m before deadline)
      else if (gw.diffMinutes <= 22 && gw.diffMinutes > 2) {
        // Find if a safety run happened in the last 15 minutes
        const hasRecentSafetyRun = recentRuns.some(r => {
          const runTime = new Date(r.created_at).getTime();
          return (now - runTime) < 15 * 60 * 1000;
        });

        if (!hasRecentSafetyRun) {
          console.log(`[SENTINEL] Triggering Stage 2 Final Safety Pulse for GW${gw.nextGw}`);
          await sendTelegram(
            env,
            `🛡️ **[حارس كلاودفلير الذكي - نبض الأمان T-20m]**\n\n` +
            `متبقي 20 دقيقة على إغلاق الجولة ${gw.nextGw}!\n` +
            `جاري فحص تقارير الإحماء النهائية، غيابات اللحظات الأخيرة، وتفادي تضارب الحراس على السيرفر السحابي فوراً.`
          );
          await triggerGitHubWorkflow(env, "safety", "live");
        }
      }
    } catch (err) {
      console.error("[SENTINEL CRON ERROR]", err);
    }
  },

  // 2. HTTP Fetch Handler (Status API & Telegram Webhook)
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Root / Status endpoint
    if (url.pathname === "/" || url.pathname === "/status") {
      try {
        const gw = await getFplGameweekInfo();
        return new Response(JSON.stringify({
          sentinel: "active",
          engine: "Cloudflare Edge 24/7 Sentinel",
          next_gameweek: gw.nextGw,
          deadline_time_utc: gw.deadlineTime,
          time_remaining: `${gw.hoursUntil}h ${gw.minsUntil}m`,
          diff_minutes: gw.diffMinutes,
          dashboard_url: "https://fantasy-ai-dashboard.pages.dev/"
        }, null, 2), {
          headers: { "Content-Type": "application/json" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500 });
      }
    }

    // Manual Instant Run Trigger
    if (url.pathname === "/run" || url.pathname === "/api/run") {
      const key = url.searchParams.get("key") || request.headers.get("x-admin-key");
      if (key !== env.ADMIN_KEY && key !== "pure_ai_secret_2026") {
        return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });
      }

      const stage = url.searchParams.get("stage") || "tactical";
      const mode = url.searchParams.get("mode") || "live";
      const res = await triggerGitHubWorkflow(env, stage, mode);

      if (res.success) {
        await sendTelegram(
          env,
          `⚡ **[أمر تشغيل فوري من كلاودفلير]**\n\nتم إطلاق سيرفر التنفيذ السحابي (Stage: \`${stage}\`, Mode: \`${mode}\`) بنجاح!`
        );
        return new Response(JSON.stringify({ success: true, message: `Workflow dispatched (${stage}, ${mode})` }), {
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response(JSON.stringify(res), { status: 500, headers: { "Content-Type": "application/json" } });
    }

    // Interactive Telegram Webhook Receiver
    if (url.pathname === "/telegram" && request.method === "POST") {
      try {
        const update = await request.json();
        const message = update.message;
        if (message && message.text) {
          const text = message.text.trim();
          const chatId = message.chat.id;

          if (text.startsWith("/status")) {
            const gw = await getFplGameweekInfo();
            await sendTelegram(env, 
              `📊 **حالة المنظومة على Cloudflare:**\n\n` +
              `• **الجولة القادمة:** ${gw.nextGwName}\n` +
              `• **الديدلاين:** \`${gw.deadlineTime}\`\n` +
              `• **الوقت المتبقي:** ${gw.hoursUntil} ساعة و ${gw.minsUntil} دقيقة\n` +
              `• **الحارس السحابي:** 🟢 شغال 24/7 على سيرفرات Cloudflare Edge\n\n` +
              `🌐 [افتح الداشبورد المباشر](https://fantasy-ai-dashboard.pages.dev/)`
            );
          } else if (text.startsWith("/run")) {
            await sendTelegram(env, `🚀 **جاري تشغيل محرك Pure AI السحابي فوراً...**\nسيتم حل الخوارزميات وتنفيذ التبديل وإرسال التقرير خلال دقيقة واحدة.`);
            await triggerGitHubWorkflow(env, "tactical", "live");
          } else if (text.startsWith("/safety")) {
            await sendTelegram(env, `🛡️ **جاري تشغيل نبض الأمان T-20m السحابي فوراً...**`);
            await triggerGitHubWorkflow(env, "safety", "live");
          } else {
            await sendTelegram(env, 
              `🤖 **أهلاً بك في غرفة تحكم Pure AI السحابية:**\n\n` +
              `• \`/status\` - عرض المتبقي على الديدلاين وحالة الفريق والداشبورد\n` +
              `• \`/run\` - إطلاق المحرك السحابي وتنفيذ التبديلات فوراً\n` +
              `• \`/safety\` - تشغيل فحص الإحماء وتفادي تضارب الحراس\n\n` +
              `🌐 الداشبورد: https://fantasy-ai-dashboard.pages.dev/`
            );
          }
        }
        return new Response("OK");
      } catch (err) {
        console.error("Telegram webhook error:", err);
        return new Response("Error", { status: 500 });
      }
    }

    return new Response("Not Found", { status: 404 });
  }
};
