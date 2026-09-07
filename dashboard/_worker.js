/**
 * Cloudflare Pages Advanced Mode Worker
 * Routes /api/chat directly to Google Gemini while serving static assets via env.ASSETS.
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Handle AI Copilot Chat endpoint
    if (url.pathname === "/api/chat") {
      if (request.method === "OPTIONS") {
        return new Response(null, {
          status: 204,
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
          }
        });
      }

      if (request.method !== "POST") {
        return new Response(JSON.stringify({ error: "Method not allowed" }), {
          status: 405,
          headers: { "Content-Type": "application/json" }
        });
      }

      try {
        const body = await request.json();
        const userMessage = body.message || "";
        const history = body.history || [];
        const squadContext = body.squadContext || {};

        const apiKey = env.GEMINI_API_KEY || body.clientApiKey;

        if (!apiKey) {
          // Provide intelligent tactical mock reply if no API key is set in environment
          return new Response(
            JSON.stringify({
              reply: generateTacticalFallback(userMessage, squadContext)
            }),
            {
              status: 200,
              headers: {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
              }
            }
          );
        }

        const systemInstruction = `You are Pep GPT (ببيب جي بي تي), the autonomous AI Tactical Director and FPL Manager for the squad '${squadContext.team_name || "هبد اصطناعي"}'.
Current Squad State (GW4):
- Formation: ${squadContext.formation || "3-5-2"}
- Captain: ${squadContext.captain_name || "Gakpo"} (xP: ${squadContext.captain_xp || "9.7"})
- Vice Captain: ${squadContext.vc_name || "B.Fernandes"} (xP: ${squadContext.vc_xp || "9.0"})
- In Bank: £${squadContext.bank ?? "1.2"}m
- Free Transfers: ${squadContext.free_transfers ?? 1} (Roll transfer recommended)
- Total Projected xP: ${squadContext.total_xp || "87.2"}
- Mini-League Rank: 1st place in Primary League. Biggest rival threat: Haaland (138% EO).

Persona: Sharp, analytical, witty, confident, elite Premier League tactician.
Respond in the language of the user's message (Arabic if asked in Arabic, English if asked in English). Keep replies tactical, concise (2-4 paragraphs), punchy, and highlight exact numbers, xP, and risk assessment.`;

        // Format conversation for Gemini
        const contents = [];
        for (const msg of history.slice(-6)) {
          contents.push({
            role: msg.role === "user" ? "user" : "model",
            parts: [{ text: msg.content }]
          });
        }
        contents.push({
          role: "user",
          parts: [{ text: userMessage }]
        });

        const modelName = env.GEMINI_MODEL || "gemini-3.8-flash";
        const geminiUrl = `https://generativelanguage.googleapis.com/v1beta/models/${modelName}:generateContent?key=${apiKey}`;
        const response = await fetch(geminiUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            systemInstruction: {
              parts: [{ text: systemInstruction }]
            },
            contents: contents,
            generationConfig: {
              temperature: 0.7,
              maxOutputTokens: 600
            }
          })
        });

        if (!response.ok) {
          const errText = await response.text();
          console.error("Gemini API error:", errText);
          return new Response(
            JSON.stringify({
              reply: generateTacticalFallback(userMessage, squadContext)
            }),
            {
              status: 200,
              headers: {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
              }
            }
          );
        }

        const data = await response.json();
        const reply =
          data.candidates?.[0]?.content?.parts?.[0]?.text ||
          "عذراً، حدث خطأ في معالجة الرد التكتيكي. حاول مرة أخرى.";

        return new Response(JSON.stringify({ reply }), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
          }
        });
      } catch (err) {
        console.error("Worker catch error:", err);
        return new Response(
          JSON.stringify({
            reply: "واجهت مشكلة في الاتصال بمحرك التكتيك. جرب ثانية!"
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Access-Control-Allow-Origin": "*"
            }
          }
        );
      }
    }

    // Default: Serve static assets
    return env.ASSETS.fetch(request);
  }
};

function generateTacticalFallback(msg, ctx) {
  const lower = (msg || "").toLowerCase();
  if (lower.includes("captain") || lower.includes("كابتن")) {
    return `🎯 **توصية الكابتنة للجولة الرابعة:**\n\nنوصي بالإبقاء على **كودي جاكبو (Gakpo)** بشارة القيادة (xP: 9.7) أمام فولهام في أنفيلد. الأرقام ترشحه بقوة بفضل مؤشرات xG داخل الصندوق بمعدل 0.82 لكل 90 دقيقة.\n\nالنائب المباشر هو **برونو فيرنانديز (Bruno)** (xP: 9.0) أمام السيتي كخيار ذو سقف عالي للكرات الثابتة.`;
  }
  if (lower.includes("threat") || lower.includes("خطر") || lower.includes("مدافع") || lower.includes("منافس")) {
    return `⚠️ **رادار التهديد والمنافسين:**\n\nالتهديد الأكبر لترتيبك حالياً هو **إرلينج هالاند (Haaland)** بنسبة ملكية فعالة تتجاوز **138%** بين متصدري الدوريات. إذا سجل هاتريك سيتراجع الترتيب مؤقتاً، لكن خط وسطك الخماسي (Saka, Palmer, Gakpo, Bruno, Stach) مصمم لتعويض هذا الفارق التراكمي.`;
  }
  if (lower.includes("transfer") || lower.includes("تبديل") || lower.includes("roll")) {
    return `🔄 **القرار الاستراتيجي للتبديلات:**\n\nالقرار الرياضي المعتمد من محرك MILP هو **ترحيل التبديل (Roll Transfer)** إلى الجولة الخامسة. هذا يمنحنا مرونة قصوى (2 FTs) مع فائض مالي قدره £1.2m، وتجنب الـ Hits في هذه المرحلة الحساسة.`;
  }
  return `🤖 **Pep GPT التكتيكي:**\n\nالفريق جاهز بنسبة 100% لخوض الجولة الرابعة بتشكيل 3-5-2 ومجموع نقاط متوقعة **87.2 xP**. تم تأمين المداورة الدفاعية، وخط الوسط يتمتع بأعلى سقف هجومي ممكن. هل لديك استفسار محدد حول لاعب معين أو خيار بديل؟`;
}
