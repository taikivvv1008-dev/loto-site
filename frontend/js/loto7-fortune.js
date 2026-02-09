/**
 * loto7-fortune.js
 * - 生年月日 + 発行数を選択 → 運勢(description) + tickets を count 口表示
 * - APIは1回だけ叩く（単発JSONで tickets が入ってくる前提）
 */

document.addEventListener("DOMContentLoaded", () => {
  const yearSelect = document.getElementById("birthYear");
  const monthSelect = document.getElementById("birthMonth");
  const daySelect = document.getElementById("birthDay");
  const issueSelect = document.getElementById("issueSelect");
  const issueButton = document.getElementById("issueButton");

  const fortuneState = document.getElementById("fortuneState");
  const fortuneStateText = document.getElementById("fortuneStateText");
  const fortuneText = document.getElementById("fortuneText");
  const predictionCards = document.getElementById("predictionCards");

  if (
    !yearSelect || !monthSelect || !daySelect || !issueSelect || !issueButton ||
    !fortuneState || !fortuneStateText || !fortuneText || !predictionCards
  ) {
    console.log("❌ loto7-fortune.js: 必須要素が見つかりません");
    return;
  }

  const ENGINE_BASE = window.LOTO_ENGINE_BASE || "";
  const LOTO_TYPE = "loto7";
  const MODEL = "fortune";
  const USER_ID = "user001";

  initBirthSelects();
  initIssueSelect(issueSelect, 100);

  issueButton.addEventListener("click", async () => {
    const y = yearSelect.value;
    const m = monthSelect.value;
    const d = daySelect.value;
    const count = clampInt(Number(issueSelect.value || 1), 1, 100);

    if (!y || !m || !d) {
      showFortuneError("生年月日をすべて選択してください。");
      return;
    }

    const birthDate = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;

    try {
      setButtonLoading(true);
      showFortuneLoading(`占い中…（${count}口）`);
      clearPrediction();

      const body = document.body;
      const round = Number(body.dataset.round);
      const drawDate = body.dataset.drawDate;

      const json = await fetchFortuneOnce({
        birthDateStr: birthDate,
        count,
        round,
        drawDate,
      });

      renderFortune(json);
      renderTickets(json?.prediction?.tickets || []);

      setButtonLoading(false);
      issueButton.textContent = "もう一度占う";
    } catch (e) {
      console.error(e);
      setButtonLoading(false);
      if (e.message === "PREMIUM_REQUIRED") {
        showPremiumWall();
      } else {
        showFortuneError("取得に失敗しました。時間をおいて再度お試しください。");
      }
    }
  });

  function showPremiumWall() {
    fortuneState.hidden = true;
    fortuneText.hidden = false;
    fortuneText.innerHTML = `
      <div style="padding:24px;border-radius:16px;text-align:center;background:linear-gradient(135deg,rgba(59,130,246,.06),rgba(147,51,234,.06));border:1px solid rgba(59,130,246,.2);">
        <p style="font-weight:900;font-size:18px;margin-bottom:8px;">有料プラン限定コンテンツです</p>
        <p style="color:rgba(15,23,42,.6);margin-bottom:16px;">予想番号を閲覧するには、有料プラン（月額550円）への登録が必要です。</p>
        <a class="btn btn--primary" href="login.html">プランに登録する</a>
      </div>
    `;
    setButtonLoading(false);
  }

  function setButtonLoading(isLoading) {
    issueButton.disabled = isLoading;
    if (isLoading) issueButton.textContent = "占い中…";
  }

  function showFortuneLoading(message) {
    fortuneText.hidden = true;
    fortuneText.innerHTML = "";
    fortuneState.hidden = false;
    fortuneStateText.textContent = message;
  }

  function showFortuneError(message) {
    fortuneText.hidden = true;
    fortuneText.innerHTML = "";
    fortuneState.hidden = false;
    fortuneStateText.textContent = message;
  }

  function renderFortune(json) {
    const d = json?.description || {};
    const lines = [d.stars, d.line1, d.line2].filter(Boolean);
    const text = dedupeLines(lines).join("\n");

    const fortuneCard = document.getElementById("fortuneCard");
    if (fortuneCard) fortuneCard.classList.add("fortune-card--bg");

    fortuneState.hidden = true;
    fortuneText.hidden = false;

    fortuneText.innerHTML = `
      <p style="white-space:pre-wrap;line-height:1.9;font-weight:800;">
        ${escapeHtml(text || "今日は穏やかな運気。焦らず丁寧にいきましょう。")}
      </p>
    `;
  }

  function clearPrediction() {
    predictionCards.innerHTML = "";
  }

  function renderTickets(tickets) {
    predictionCards.innerHTML = (tickets || [])
      .map((nums, idx) => renderPredictionCardFromNumbers(nums, idx))
      .join("");
  }

  function renderPredictionCardFromNumbers(numbers, index) {
    const balls = (numbers || [])
      .map((n) => `
        <li class="num-ball">
          ${String(n).padStart(2, "0")}
        </li>
      `)
      .join("");

    return `
      <div class="card prediction-card" style="margin-top:${index === 0 ? "0" : "12px"};">
        <div class="prediction-card__head" style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
          <div style="font-weight:900;">${index + 1}口目</div>
        </div>
        <ul class="prediction-numbers" style="margin-top:10px;">
          ${balls}
        </ul>
      </div>
    `;
  }

  async function fetchLatestDraw(lotoType) {
    const url = new URL(`${ENGINE_BASE}/draw/latest`, location.origin);
    url.searchParams.set("loto_type", lotoType);

    const res = await fetch(url.toString(), { method: "GET" });
    if (!res.ok) throw new Error(`draw/latest error: ${res.status}`);
    return await res.json();
  }

  async function fetchFortuneOnce({ birthDateStr, count, round, drawDate }) {
    const url = new URL(`${ENGINE_BASE}/engine/prediction`, location.origin);
    url.searchParams.set("user_id", USER_ID);
    url.searchParams.set("loto_type", LOTO_TYPE);
    url.searchParams.set("model", MODEL);
    url.searchParams.set("birthdate", birthDateStr);
    url.searchParams.set("count", String(count));
    url.searchParams.set("round", String(round));
    url.searchParams.set("draw_date", String(drawDate));

    const res = await LotoAuth.fetchWithAuth(url.toString(), { method: "GET" });
    if (res.status === 403) {
      throw new Error("PREMIUM_REQUIRED");
    }
    if (!res.ok) throw new Error(`Engine error: ${res.status}`);

    const data = await res.json();
    if (!Array.isArray(data?.prediction?.tickets)) {
      throw new Error("Invalid response: prediction.tickets is missing");
    }
    return data;
  }

  function initBirthSelects() {
    addPlaceholder(yearSelect, "----年");
    addPlaceholder(monthSelect, "--月");
    addPlaceholder(daySelect, "--日");

    const currentYear = new Date().getFullYear();
    for (let y = 1930; y <= currentYear; y++) yearSelect.appendChild(new Option(`${y}年`, String(y)));
    for (let m = 1; m <= 12; m++) monthSelect.appendChild(new Option(`${m}月`, String(m)));
    for (let d = 1; d <= 31; d++) daySelect.appendChild(new Option(`${d}日`, String(d)));
  }

  function addPlaceholder(selectEl, label) {
    selectEl.innerHTML = "";
    const opt = new Option(label, "", true, true);
    opt.disabled = true;
    selectEl.appendChild(opt);
  }

  function initIssueSelect(selectEl, max) {
    selectEl.innerHTML = "";
    for (let i = 1; i <= max; i++) selectEl.appendChild(new Option(`${i}口`, String(i)));
    selectEl.value = "1";
  }

  function clampInt(n, min, max) {
    if (!Number.isFinite(n)) return min;
    return Math.max(min, Math.min(max, Math.trunc(n)));
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function dedupeLines(lines) {
    const seen = new Set();
    const out = [];
    for (const line of lines) {
      const key = String(line).trim();
      if (!key) continue;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(key);
    }
    return out;
  }
});
