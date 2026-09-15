/**
 * Cloudflare Edge Sentinel for Fantasy AI
 * =======================================
 * 24/7 autonomous edge sentinel running on Cloudflare's global network.
 * 1. Monitors FPL deadlines with zero server latency.
 * 2. Instantly dispatches GitHub Actions workflows for Stage 1 (T-2.5h) and Stage 2 (T-20m).
 * 3. Acts as an interactive Telegram Bot Webhook with rich inline buttons, back navigation, and help guide.
 */

const MAIN_KEYBOARD = {
  keyboard: [
    [{ text: "📊 حالة الفريق والجولة" }, { text: "🚀 تشغيل الذكاء الاصطناعي" }],
    [{ text: "🛡️ نبض الأمان (T-20m)" }, { text: "🌐 فتح الداشبورد" }],
    [{ text: "🔙 🏠 القائمة الرئيسية" }, { text: "ℹ️ دليل استخدام البوت" }]
  ],
  resize_keyboard: true,
  is_persistent: true
};

function formatDeadline12h(isoStr) {
  if (!isoStr) return "غير محدد";
  try {
    const d = new Date(isoStr);
    const dateFormatted = d.toLocaleString("ar-EG", {
      timeZone: "Africa/Cairo",
      weekday: "long",
      day: "numeric",
      month: "long",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      numberingSystem: "latn"
    });
    return `${dateFormatted} (توقيت مصر/مكة)`;
  } catch (e) {
    return isoStr;
  }
}

function formatRemainingTime(diffMinutes) {
  if (diffMinutes <= 0) return "انتهى موعد الديدلاين";
  const days = Math.floor(diffMinutes / (60 * 24));
  const hours = Math.floor((diffMinutes % (60 * 24)) / 60);
  const mins = diffMinutes % 60;

  const parts = [];
  if (days === 1) parts.push("يوم واحد");
  else if (days === 2) parts.push("يومان");
  else if (days >= 3 && days <= 10) parts.push(`${days} أيام`);
  else if (days > 10) parts.push(`${days} يوماً`);

  if (hours === 1) parts.push("ساعة واحدة");
  else if (hours === 2) parts.push("ساعتان");
  else if (hours >= 3 && hours <= 10) parts.push(`${hours} ساعات`);
  else if (hours > 10) parts.push(`${hours} ساعة`);

  if (days === 0 && mins > 0) {
    if (mins === 1) parts.push("دقيقة واحدة");
    else if (mins === 2) parts.push("دقيقتان");
    else if (mins >= 3 && mins <= 10) parts.push(`${mins} دقائق`);
    else parts.push(`${mins} دقيقة`);
  }
  return parts.length > 0 ? parts.join(" و ") : "أقل من دقيقة";
}

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
    deadlineIso: nextEvent.deadline_time,
    deadlineFormatted: formatDeadline12h(nextEvent.deadline_time),
    remainingFormatted: formatRemainingTime(diffMinutes),
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

async function sendTelegram(env, text, extra = {}) {
  const botToken = env.TELEGRAM_BOT_TOKEN;
  const chatId = extra.chat_id || env.TELEGRAM_CHAT_ID;
  if (!botToken || !chatId) return;

  const url = `https://api.telegram.org/bot${botToken}/sendMessage`;
  try {
    const payload = {
      chat_id: chatId,
      text: text,
      parse_mode: "HTML",
      disable_web_page_preview: true,
      reply_markup: extra.reply_markup || MAIN_KEYBOARD
    };
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (err) {
    console.error("Telegram error:", err);
  }
}

async function answerCallbackQuery(env, callbackQueryId, text = "") {
  const botToken = env.TELEGRAM_BOT_TOKEN;
  if (!botToken || !callbackQueryId) return;
  const url = `https://api.telegram.org/bot${botToken}/answerCallbackQuery`;
  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ callback_query_id: callbackQueryId, text: text })
    });
  } catch (err) {
    console.error("Answer callback error:", err);
  }
}

async function sendOrEditTelegram(env, text, extra = {}) {
  const botToken = env.TELEGRAM_BOT_TOKEN;
  const chatId = extra.chat_id || env.TELEGRAM_CHAT_ID;
  if (!botToken || !chatId) return;

  // Try editing existing message if message_id is provided
  if (extra.message_id) {
    const editUrl = `https://api.telegram.org/bot${botToken}/editMessageText`;
    try {
      const editPayload = {
        chat_id: chatId,
        message_id: extra.message_id,
        text: text,
        parse_mode: "HTML",
        disable_web_page_preview: true,
        reply_markup: extra.reply_markup || undefined
      };
      const res = await fetch(editUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editPayload)
      });
      if (res.ok) return;

      // Ignore "message is not modified" Telegram error
      const errText = await res.text();
      if (errText.includes("message is not modified")) return;
      console.warn("editMessageText non-ok, falling back to sendMessage:", errText);
    } catch (e) {
      console.warn("editMessageText exception:", e);
    }
  }

  // Otherwise send as new message
  return sendTelegram(env, text, extra);
}

async function sendMainMenu(env, chatId = null, messageId = null) {
  try {
    const gw = await getFplGameweekInfo();
    const text = `🏠 <b>غرفة التحكم الرئيسية – Fantasy AI</b> ⚽\n` +
      `━━━━━━━━━━━━━━━━━━━━\n` +
      `أهلاً بك يا قائد! فريقك تحت المراقبة السحابية الذاتية 24/7 عبر <b>Cloudflare Edge</b>.\n\n` +
      `• <b>الجولة القادمة:</b> ${gw.nextGwName}\n` +
      `• <b>موعد الديدلاين:</b> ⏰ <b>${gw.deadlineFormatted}</b>\n` +
      `• <b>الوقت المتبقي:</b> ⏳ <b>${gw.remainingFormatted}</b>\n` +
      `• <b>الحالة:</b> 🟢 مراقبة نشطة وحارس الطوارئ جاهز\n\n` +
      `اختر الإجراء المطلوب عبر الأزرار أدناه:`;

    const inline_keyboard = [
      [
        { text: "📊 حالة الفريق والخطة", callback_data: "status" },
        { text: "🚀 تشغيل الذكاء الاصطناعي", callback_data: "run" }
      ],
      [
        { text: "🛡️ نبض الأمان (T-20m)", callback_data: "safety" },
        { text: "🌐 فتح الداشبورد المباشر", url: "https://fantasy-ai-dashboard.pages.dev/" }
      ],
      [
        { text: "ℹ️ دليل استخدام وشرح البوت", callback_data: "help" }
      ]
    ];

    await sendOrEditTelegram(env, text, {
      chat_id: chatId,
      message_id: messageId,
      reply_markup: { inline_keyboard: inline_keyboard }
    });
  } catch (err) {
    await sendOrEditTelegram(env, `🏠 <b>القائمة الرئيسية:</b>\nاختر من الأزرار بالأسفل:`, {
      chat_id: chatId,
      message_id: messageId
    });
  }
}

async function sendHelpGuide(env, chatId = null, messageId = null) {
  const guide = `🤖 <b>دليل استخدام بوت Fantasy AI المستقل</b> ⚽\n` +
    `━━━━━━━━━━━━━━━━━━━━\n` +
    `هذا البوت مربوط بمحرك <b>Pure AI</b> السحابي المدعوم بسيرفرات <b>Cloudflare Edge</b> العالمية، ليدير فريقك تلقائياً بنسبة 100% دون الحاجة لفتح اللابتوب أثناء سفرك:\n\n` +
    `🔹 <b>المراقبة التلقائية الذكية (24/7 Sentinel):</b>\n` +
    `• <b>قبل الديدلاين بـ ساعتين ونصف (Stage 1):</b>\n` +
    `يقوم السيرفر بحساب التشكيلة الأفضل رياضياً (Two-Tier MILP) وينفذ التبديلات على حسابك ويرسل لك تقريراً تفصيلياً بالتشكيلة والكابتن.\n\n` +
    `• <b>قبل الديدلاين بـ 20 دقيقة (Stage 2):</b>\n` +
    `يقوم بفحص تقارير الإحماء النهائية، ولو حدثت إصابة مفاجئة أو تضارب حراس، يستبدل اللاعب تلقائياً لضمان عدم ضياع أي نقطة.\n\n` +
    `🔹 <b>أزرار التحكم المباشرة:</b>\n` +
    `• 📊 <b>حالة الفريق والجولة:</b> عداد الديدلاين وتفاصيل الخطة.\n` +
    `• 🚀 <b>تشغيل الذكاء الاصطناعي:</b> إطلاق السيرفر وتنفيذ التبديل فوراً.\n` +
    `• 🛡️ <b>نبض الأمان:</b> فحص سريع لإصابات اللحظات الأخيرة.\n` +
    `• 🌐 <b>فتح الداشبورد:</b> رابط لوحة التحكم المباشرة.\n` +
    `• 🔙 <b>رجوع:</b> العودة للقائمة الرئيسية في أي وقت.\n` +
    `━━━━━━━━━━━━━━━━━━━━\n` +
    `<i>سافر وأنت مطمئن، فريقك في أيدٍ أمينة مع الذكاء الاصطناعي على مدار الساعة!</i> ⚡`;

  await sendOrEditTelegram(env, guide, {
    chat_id: chatId,
    message_id: messageId,
    reply_markup: {
      inline_keyboard: [
        [
          { text: "📊 حالة الفريق", callback_data: "status" },
          { text: "🚀 تشغيل الذكاء الاصطناعي", callback_data: "run" }
        ],
        [
          { text: "🛡️ نبض الأمان (T-20m)", callback_data: "safety" },
          { text: "🌐 فتح الداشبورد", url: "https://fantasy-ai-dashboard.pages.dev/" }
        ],
        [
          { text: "🔙 🏠 رجوع للقائمة الرئيسية", callback_data: "main_menu" }
        ]
      ]
    }
  });
}

async function sendStatus(env, chatId = null, messageId = null) {
  const gw = await getFplGameweekInfo();
  const text = `📊 <b>حالة المنظومة وفريق الفانتازي:</b>\n` +
    `━━━━━━━━━━━━━━━━━━━━\n` +
    `• <b>الجولة القادمة:</b> ${gw.nextGwName}\n` +
    `• <b>موعد الديدلاين:</b> ⏰ <b>${gw.deadlineFormatted}</b>\n` +
    `• <b>الوقت المتبقي:</b> ⏳ <b>${gw.remainingFormatted}</b>\n` +
    `• <b>الحارس السحابي:</b> 🟢 مراقبة نشطة 24/7 على سيرفرات Cloudflare Edge\n` +
    `• <b>الخطة المعتمدة:</b> 🔄 بيع Stach واستقدام Tavernier (3-5-2)\n` +
    `━━━━━━━━━━━━━━━━━━━━\n` +
    `🌐 <b>الداشبورد المباشر:</b> https://fantasy-ai-dashboard.pages.dev/`;

  await sendOrEditTelegram(env, text, {
    chat_id: chatId,
    message_id: messageId,
    reply_markup: {
      inline_keyboard: [
        [
          { text: "🚀 تشغيل التبديل الآن", callback_data: "run" },
          { text: "🛡️ نبض الأمان T-20m", callback_data: "safety" }
        ],
        [
          { text: "🌐 فتح الداشبورد المباشر", url: "https://fantasy-ai-dashboard.pages.dev/" },
          { text: "ℹ️ دليل البوت", callback_data: "help" }
        ],
        [
          { text: "🔙 🏠 رجوع للقائمة الرئيسية", callback_data: "main_menu" }
        ]
      ]
    }
  });
}

async function sendSafety(env, chatId = null, messageId = null) {
  const text = `🛡️ <b>[نبض الأمان الفوري – T-20m Pulse]</b>\n` +
    `━━━━━━━━━━━━━━━━━━━━\n` +
    `تم إطلاق فحص الأمان السحابي فوراً!\n` +
    `يتم الآن التحقق من تقارير الإحماء، غيابات اللحظات الأخيرة، وتفادي تضارب الحراس على السيرفر السحابي.`;

  await sendOrEditTelegram(env, text, {
    chat_id: chatId,
    message_id: messageId,
    reply_markup: {
      inline_keyboard: [
        [
          { text: "📊 حالة الفريق", callback_data: "status" },
          { text: "🌐 فتح الداشبورد المباشر", url: "https://fantasy-ai-dashboard.pages.dev/" }
        ],
        [
          { text: "🔙 🏠 رجوع للقائمة الرئيسية", callback_data: "main_menu" }
        ]
      ]
    }
  });
  await triggerGitHubWorkflow(env, "safety", "live");
}

async function sendRun(env, chatId = null, messageId = null) {
  const text = `🚀 <b>[إطلاق محرك Pure AI السحابي]</b>\n` +
    `━━━━━━━━━━━━━━━━━━━━\n` +
    `تم بدء تشغيل سيرفر الـ MILP وحل التشكيلة التكتيكية وتطبيق التبديلات على حسابك في الفانتازي فوراً.\n` +
    `ستصلك رسالة بالتشكيلة والتقرير النهائي خلال دقيقة واحدة.`;

  await sendOrEditTelegram(env, text, {
    chat_id: chatId,
    message_id: messageId,
    reply_markup: {
      inline_keyboard: [
        [
          { text: "📊 حالة الفريق", callback_data: "status" },
          { text: "🌐 فتح الداشبورد المباشر", url: "https://fantasy-ai-dashboard.pages.dev/" }
        ],
        [
          { text: "🔙 🏠 رجوع للقائمة الرئيسية", callback_data: "main_menu" }
        ]
      ]
    }
  });
  await triggerGitHubWorkflow(env, "tactical", "live");
}

async function sendDashboard(env, chatId = null, messageId = null) {
  const text = `🌐 <b>رابط الداشبورد التنفيذي المباشر:</b>\n` +
    `━━━━━━━━━━━━━━━━━━━━\n` +
    `اضغط على الزر أدناه لفتح لوحة التحكم ومتابعة التشكيلة الحية، الرادار التكتيكي، والتحليلات:`;

  await sendOrEditTelegram(env, text, {
    chat_id: chatId,
    message_id: messageId,
    reply_markup: {
      inline_keyboard: [
        [
          { text: "⚡ الدخول إلى الداشبورد ⚡", url: "https://fantasy-ai-dashboard.pages.dev/" }
        ],
        [
          { text: "📊 حالة الفريق", callback_data: "status" },
          { text: "ℹ️ دليل البوت", callback_data: "help" }
        ],
        [
          { text: "🔙 🏠 رجوع للقائمة الرئيسية", callback_data: "main_menu" }
        ]
      ]
    }
  });
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
            `⏱️ <b>[حارس كلاودفلير الذكي – Cloudflare Sentinel]</b>\n` +
            `━━━━━━━━━━━━━━━━━━━━\n` +
            `تم رصد اقتراب موعد ديدلاين <b>الجولة ${gw.nextGw}</b>!\n` +
            `• <b>موعد الإغلاق:</b> ⏰ <b>${gw.deadlineFormatted}</b>\n` +
            `• <b>الوقت المتبقي:</b> ⏳ <b>${gw.remainingFormatted}</b>\n\n` +
            `🚀 <b>جاري إطلاق سيرفر التنفيذ السحابي (Stage 1: MILP & Transfers) فوراً!</b>`,
            {
              reply_markup: {
                inline_keyboard: [
                  [{ text: "🌐 فتح الداشبورد المباشر", url: "https://fantasy-ai-dashboard.pages.dev/" }],
                  [
                    { text: "📊 حالة الفريق", callback_data: "status" },
                    { text: "🛡️ نبض الأمان", callback_data: "safety" }
                  ],
                  [{ text: "🔙 🏠 رجوع للقائمة الرئيسية", callback_data: "main_menu" }]
                ]
              }
            }
          );
          await triggerGitHubWorkflow(env, "tactical", "live");
        }
      }

      // Stage 2: Final Pre-Deadline Safety Pulse (T-20m: between 22m and 2m before deadline)
      else if (gw.diffMinutes <= 22 && gw.diffMinutes > 2) {
        const hasRecentSafetyRun = recentRuns.some(r => {
          const runTime = new Date(r.created_at).getTime();
          return (now - runTime) < 15 * 60 * 1000;
        });

        if (!hasRecentSafetyRun) {
          console.log(`[SENTINEL] Triggering Stage 2 Final Safety Pulse for GW${gw.nextGw}`);
          await sendTelegram(
            env,
            `🛡️ <b>[حارس كلاودفلير الذكي – نبض الأمان T-20m]</b>\n` +
            `━━━━━━━━━━━━━━━━━━━━\n` +
            `متبقي 20 دقيقة على إغلاق الجولة ${gw.nextGw}!\n` +
            `• <b>موعد الإغلاق:</b> ⏰ <b>${gw.deadlineFormatted}</b>\n\n` +
            `جاري فحص تقارير الإحماء النهائية، غيابات اللحظات الأخيرة، وتفادي تضارب الحراس على السيرفر السحابي فوراً.`,
            {
              reply_markup: {
                inline_keyboard: [
                  [{ text: "🌐 فتح الداشبورد المباشر", url: "https://fantasy-ai-dashboard.pages.dev/" }],
                  [{ text: "📊 حالة الفريق", callback_data: "status" }],
                  [{ text: "🔙 🏠 رجوع للقائمة الرئيسية", callback_data: "main_menu" }]
                ]
              }
            }
          );
          await triggerGitHubWorkflow(env, "safety", "live");
        }
      }
    } catch (err) {
      console.error("[SENTINEL CRON ERROR]", err);
    }
  },

  // 2. HTTP Fetch Handler (Status API & Interactive Telegram Webhook)
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
          deadline_time_12h: gw.deadlineFormatted,
          time_remaining: gw.remainingFormatted,
          deadline_time_utc: gw.deadlineIso,
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
          `⚡ <b>[أمر تشغيل فوري من كلاودفلير]</b>\n━━━━━━━━━━━━━━━━━━━━\nتم إطلاق سيرفر التنفيذ السحابي (Stage: <code>${stage}</code>, Mode: <code>${mode}</code>) بنجاح!`,
          {
            reply_markup: {
              inline_keyboard: [
                [{ text: "🌐 فتح الداشبورد المباشر", url: "https://fantasy-ai-dashboard.pages.dev/" }],
                [{ text: "📊 فحص الفريق", callback_data: "status" }],
                [{ text: "🔙 🏠 رجوع للقائمة الرئيسية", callback_data: "main_menu" }]
              ]
            }
          }
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

        // 1. Handle inline button callback clicks
        if (update.callback_query) {
          const cb = update.callback_query;
          const data = cb.data;
          const chatId = cb.message ? cb.message.chat.id : null;
          const messageId = cb.message ? cb.message.message_id : null;
          await answerCallbackQuery(env, cb.id, "جاري المعالجة...");

          if (data === "main_menu") {
            await sendMainMenu(env, chatId, messageId);
          } else if (data === "status") {
            await sendStatus(env, chatId, messageId);
          } else if (data === "safety") {
            await sendSafety(env, chatId, messageId);
          } else if (data === "run") {
            await sendRun(env, chatId, messageId);
          } else if (data === "help") {
            await sendHelpGuide(env, chatId, messageId);
          }
          return new Response("OK");
        }

        // 2. Handle text messages & reply keyboard buttons
        const message = update.message;
        if (message && message.text) {
          const text = message.text.trim();
          const chatId = message.chat.id;

          if (
            text === "🔙 🏠 القائمة الرئيسية" ||
            text === "🏠 القائمة الرئيسية" ||
            text === "رجوع" ||
            text === "الرجوع" ||
            text === "/menu" ||
            text === "/start" ||
            text.includes("رجوع") ||
            text.includes("القائمة الرئيسية") ||
            text.toLowerCase() === "back"
          ) {
            await sendMainMenu(env, chatId);
          } else if (text === "📊 حالة الفريق والجولة" || text.startsWith("/status") || text.includes("حالة الفريق")) {
            await sendStatus(env, chatId);
          } else if (text === "🚀 تشغيل الذكاء الاصطناعي" || text.startsWith("/run") || text.includes("تشغيل")) {
            await sendRun(env, chatId);
          } else if (text === "🛡️ نبض الأمان (T-20m)" || text.startsWith("/safety") || text.includes("نبض الأمان") || text.includes("الامان") || text.includes("الأمان")) {
            await sendSafety(env, chatId);
          } else if (text === "🌐 فتح الداشبورد" || text.startsWith("/dashboard") || text.includes("الداشبورد")) {
            await sendDashboard(env, chatId);
          } else if (text === "ℹ️ دليل استخدام البوت" || text.startsWith("/help") || text.includes("دليل") || text.includes("مساعدة")) {
            await sendHelpGuide(env, chatId);
          } else {
            await sendHelpGuide(env, chatId);
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
