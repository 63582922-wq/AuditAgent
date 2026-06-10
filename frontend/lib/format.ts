/** SSR/客户端一致的日期显示，避免 toLocale* hydration 差异 */
export function formatDate(iso: string): string {
  const [date] = iso.split("T");
  if (!date) return iso;
  const [y, m, d] = date.split("-");
  if (!y || !m || !d) return iso;
  return `${y}/${m}/${d}`;
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  const s = String(d.getSeconds()).padStart(2, "0");
  return `${h}:${m}:${s}`;
}
