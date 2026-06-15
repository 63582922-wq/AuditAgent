/** SSR/客户端一致的日期显示，避免 toLocale* hydration 差异 */
export function formatDate(iso: string): string {
  const [date] = iso.split("T");
  if (!date) return iso;
  const [y, m, d] = date.split("-");
  if (!y || !m || !d) return iso;
  return `${y}/${m}/${d}`;
}

export function formatTime(iso: string): string {
  const match = iso.match(/T(\d{2}):(\d{2}):(\d{2})/);
  if (match) return `${match[1]}:${match[2]}:${match[3]}`;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const h = String(d.getUTCHours()).padStart(2, "0");
  const m = String(d.getUTCMinutes()).padStart(2, "0");
  const s = String(d.getUTCSeconds()).padStart(2, "0");
  return `${h}:${m}:${s}`;
}
