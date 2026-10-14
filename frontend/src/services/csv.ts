// CSV 导出：正确处理引号、换行、中文与外部文本公式前缀（= + - @ 开头转义）
// 与后端 s8_report.py text_cell 对齐：先去起始空白再判定公式前缀，并清理控制字符

export function csvEscape(value: unknown): string {
  let s = value == null ? "" : String(value);
  // 清理不可见控制字符（\x00-\x08 \x0b \x0c \x0e-\x1f），与后端一致
  // eslint-disable-next-line no-control-regex
  s = s.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, "");
  // 防止表格软件将单元格解释为公式：先 lstrip 起始空白再判定
  const stripped = s.replace(/^\s+/, "");
  if (/^[=+\-@]/.test(stripped)) s = "'" + s;
  if (/[",\r\n]/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
  return s;
}

export function toCsv(headers: string[], rows: unknown[][]): string {
  const lines = [headers.map(csvEscape).join(",")];
  for (const r of rows) lines.push(r.map(csvEscape).join(","));
  // 前置 BOM 保证 Excel 正确识别中文
  return "\uFEFF" + lines.join("\r\n");
}

export function downloadCsv(filename: string, csv: string) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
