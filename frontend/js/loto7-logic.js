/** 
 * loto7-logic.js
 * ロト7ロジック予想ページ専用
 * ① 発行数ダイアログ（1〜100）
 * ② 発行→生成中表示→（ダミー or API）で番号表示
 *
 * 期待するHTMLのID:
 * - issueButton, issueDialog, issueSelect, issueConfirm
 * - predictionState, predictionStateText
 * - predictionCards （※ここに発行結果を描画）
 */

document.addEventListener("DOMContentLoaded", () => {
  // ====== 必須DOM ======
  const issueButton = document.getElementById("issueButton");
  const issueSelect = document.getElementById("issueSelect");

  const predictionState = document.getElementById("predictionState");
  const predictionStateText = document.getElementById("predictionStateText");
  const predictionCards = document.getElementById("predictionCards");

  // どれか欠けてたら何もしない（落ちないように）
  if (
    !issueButton ||
    !issueSelect ||
    !predictionState ||
    !predictionStateText ||
    !predictionCards
  ) {
    console.log("❌ loto7-logic.js: 必須要素が見つかりません", {
      issueButton,
      issueDialog,
      issueSelect,
      issueConfirm,
      predictionState,
      predictionStateText,
      predictionCards,
    });
    return;
  }

  // ====== 設定（AのAPIができたらここだけ差し替え） ======
  // APIを使う場合: window.LOTO_ENGINE_BASE = "https://xxxx" のようにHTMLで定義してもOK
  const ENGINE_BASE = window.LOTO_ENGINE_BASE || ""; // 空なら同一オリジン想定
  const USE_MOCK = false;

  // このページは固定でロト7ロジック
  const LOTO_TYPE = "loto7";
  const MODEL = "logic";
  const USER_ID = "user001";

  // round/draw_date は運用で差し替える想定
  let round = 0;
  let drawDate = "";

  // 最新回をAPIから取得して画面と内部パラメータに反映
  async function fetchLatestDraw() {
    const url = new URL(`${ENGINE_BASE}/draw/latest`, location.origin);
    url.searchParams.set("loto_type", LOTO_TYPE);

    const res = await fetch(url.toString(), { method: "GET" });
    if (!res.ok) throw new Error(`draw/latest error: ${res.status}`);

    const d = await res.json();

    round = Number(d.round || 0);
    drawDate = String(d.draw_date || "");

    // 画面表示も更新（HTML側に#roundと#drawDateがある）
    const roundEl = document.getElementById("round");
    const drawEl = document.getElementById("drawDate");
    if (roundEl) roundEl.textContent = String(round || "-");
    if (drawEl) drawEl.textContent = drawDate || "-";
  }

  // ====== 発行数select 1〜100 ======
  initIssueSelect(issueSelect, 100);

  fetchLatestDraw().catch((e) => {
    console.error(e);
    // 最新回が取れないと予想発行できないのでエラー表示
    showError("開催情報の取得に失敗しました。バックエンドが起動しているか確認してください。");
  });

  // ====== UIユーティリティ ======
  function setButtonLoading(isLoading) {
    issueButton.disabled = isLoading;
    issueButton.textContent = isLoading ? "発行中…" : "予想番号を発行する";
  }

  function showLoading(message) {
    predictionCards.innerHTML = "";
    predictionCards.hidden = true;

    predictionState.hidden = false;
    predictionStateText.textContent = message;

    setButtonLoading(true);
  }

  function showError(message) {
    predictionState.hidden = true;
    predictionCards.hidden = false;
    predictionCards.innerHTML = `
      <div class="card" style="padding:14px;border-radius:16px;border:1px solid rgba(239,68,68,.2);background:rgba(239,68,68,.08);font-weight:800;">
        ${escapeHtml(message)}
      </div>
    `;
    setButtonLoading(false);
  }

  function showPredictions(payload, count) {
    predictionState.hidden = true;
    predictionCards.hidden = false;

    // payload が配列ならそのまま（将来用）
    // payload が単体JSONなら tickets を count 分だけ展開してカード化
    let list = [];

    if (Array.isArray(payload)) {
      list = payload;
    } else {
      const json = payload || {};
      const pred = json.prediction || {};
      const tickets = Array.isArray(pred.tickets) ? pred.tickets : [];
      const fixed = Array.isArray(pred.fixed_numbers) ? pred.fixed_numbers : [];

      // ticketsが無い場合はnumbers1口だけ表示
      const baseTickets = tickets.length ? tickets : [pred.numbers || []];
      const slice = baseTickets.slice(0, count);

      // 1口ずつ “numbers差し替え版” のjsonを作る
      list = slice.map((nums) => ({
        ...json,
        prediction: {
          ...pred,
          numbers: nums,
          fixed_numbers: fixed,
        },
      }));
    }

    predictionCards.innerHTML = list
      .map((p, idx) => renderPredictionCard(p, idx))
      .join("");

    setButtonLoading(false);
    issueButton.textContent = "予想番号を再発行する";
  }

    issueButton.addEventListener("click", async () => {
        const count = clampInt(Number(issueSelect.value || 1), 1, 100);

        try {
            showLoading(`予想番号生成中…（${count}口）`);

            const predictions = USE_MOCK
            ? await mockFetchPredictions(count)
            : await fetchPredictionsFromEngine(count);

            showPredictions(predictions, count);
        } catch (e) {
            console.error(e);
            if (e.message === "PREMIUM_REQUIRED") {
              showPremiumWall();
            } else {
              showError("取得に失敗しました。時間をおいて再度お試しください。");
            }
        }
    });

  function showPremiumWall() {
    predictionState.hidden = true;
    predictionCards.hidden = false;
    predictionCards.innerHTML = `
      <div class="card" style="padding:24px;border-radius:16px;text-align:center;background:linear-gradient(135deg,rgba(59,130,246,.06),rgba(147,51,234,.06));border:1px solid rgba(59,130,246,.2);">
        <p style="font-weight:900;font-size:18px;margin-bottom:8px;">有料プラン限定コンテンツです</p>
        <p style="color:rgba(15,23,42,.6);margin-bottom:16px;">予想番号を閲覧するには、有料プラン（月額550円）への登録が必要です。</p>
        <a class="btn btn--primary" href="login.html">プランに登録する</a>
      </div>
    `;
    setButtonLoading(false);
  }


  // ====== API接続（Aができたらここを使う） ======
  async function fetchPredictionsFromEngine(count) {
    // 例: GET /engine/prediction?loto_type=loto7&model=logic&round=xxxx&draw_date=yyyy-mm-dd&count=10
    const url = new URL(`${ENGINE_BASE}/engine/prediction`, location.origin);
    url.searchParams.set("user_id", USER_ID);
    url.searchParams.set("loto_type", LOTO_TYPE);
    url.searchParams.set("model", MODEL);
    if (round) url.searchParams.set("round", String(round));
    if (drawDate) url.searchParams.set("draw_date", drawDate);
    url.searchParams.set("count", String(count));

    const res = await LotoAuth.fetchWithAuth(url.toString(), { method: "GET" });
    if (res.status === 403) {
      throw new Error("PREMIUM_REQUIRED");
    }
    if (!res.ok) throw new Error(`Engine error: ${res.status}`);

    const data = await res.json();

    // - Aが配列を返す: { predictions:[{...},{...}] }
    // - Aが1件を返す: {...}
    if (Array.isArray(data?.predictions)) return data.predictions;
    if (data?.prediction?.numbers) {
      return data; // ←複製しない
    }

    throw new Error("Invalid response shape");
  }

  // ====== ダミー（A未接続でもUI完成させる） ======
  async function mockFetchPredictions(count) {
    // 生成っぽい待機
    await wait(700);

    // ロト7: 1〜37、重複なし。固定数字（例）を入れる
    // ※固定数字は仮。A側決定後に差し替え
    const fixed = [7, 17];

    const predictions = [];
    for (let i = 0; i < count; i++) {
      const nums = generateUniqueNumbersWithFixed({
        min: 1,
        max: 37,
        total: 7,
        fixedNumbers: fixed,
      });

      predictions.push({
        meta: {
          loto_type: "loto7",
          model: "logic",
          prediction_id: `mock_loto7_logic_${Date.now()}_${i + 1}`,
          engine_version: "engine-mock",
        },
        draw: {
          round: round || 0,
          draw_date: drawDate || "",
          weekday: "",
        },
        prediction: {
          numbers: nums,
          fixed_numbers: fixed,
          number_source: { fixed: "global_fixed_v1", random: "uniform" },
        },
        description: {
          headline: "",
          main: "",
          one_word: "",
        },
        system: {
          generated_at: new Date().toISOString(),
          regenerated: false,
          data_source: "mock",
          public: true,
        },
      });
    }

    return predictions;
  }

  // ====== 描画 ======
  function renderPredictionCard(json, index) {
    const numbers = json?.prediction?.numbers || [];
    const fixedNums = new Set(json?.prediction?.fixed_numbers || []);

    const balls = numbers
      .map((n) => {
        const isFixed = fixedNums.has(n);
        return `
          <li class="num-ball${isFixed ? " is-fixed" : ""}">
            ${String(n).padStart(2, "0")}
          </li>
        `;
      })
      .join("");

    // 口数表示（1口ごとにカード）
    return `
      <div class="card prediction-card" style="margin-top:${index === 0 ? "0" : "12px"};">
        <div class="prediction-card__head" style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
          <div style="font-weight:900;">${index + 1}口目</div>
          <div style="color:rgba(15,23,42,.6);font-size:12px;">
            ${escapeHtml(json?.draw?.draw_date || "")}${json?.draw?.round ? ` / 第${escapeHtml(String(json.draw.round))}回` : ""}
          </div>
        </div>

        <ul class="prediction-numbers" style="margin-top:10px;">
          ${balls}
        </ul>

        ${
          fixedNums.size
            ? `<div style="margin-top:10px;color:rgba(15,23,42,.7);font-size:12px;font-weight:800;">
                 固定数字：${Array.from(fixedNums).map((n) => String(n).padStart(2, "0")).join("・")}
               </div>`
            : ""
        }
      </div>
    `;
  }

  // ====== 便利関数 ======
  function initIssueSelect(selectEl, max) {
    if (selectEl.options.length > 0) return;
    for (let i = 1; i <= max; i++) {
      const opt = document.createElement("option");
      opt.value = String(i);
      opt.textContent = `${i}口`;
      selectEl.appendChild(opt);
    }
    selectEl.value = "1";
  }

  function generateUniqueNumbersWithFixed({ min, max, total, fixedNumbers }) {
    const set = new Set(fixedNumbers || []);
    while (set.size < total) {
      set.add(randInt(min, max));
    }
    return Array.from(set).sort((a, b) => a - b);
  }

  function randInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
  }

  function clampInt(n, min, max) {
    if (!Number.isFinite(n)) return min;
    return Math.max(min, Math.min(max, Math.trunc(n)));
  }

  function wait(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
});
