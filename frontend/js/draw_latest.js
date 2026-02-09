async function fetchLatestDraw(lotoType) {
  const base = window.LOTO_ENGINE_BASE || "http://127.0.0.1:8010";
  const url = `${base}/draw/latest?loto_type=${encodeURIComponent(lotoType)}`;
  const res = await fetch(url);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`draw/latest failed: ${res.status} ${txt}`);
  }
  return await res.json(); // {loto_type, round, draw_date, weekday}
}
