import { useEffect, useRef } from "react";

/**
 * 弹层焦点管理（抽屉 / 模态 / 向导共用）：
 * - 打开时记录触发元素，初始聚焦弹层内首个可聚焦元素（延迟一帧，
 *   避免同一次按键的 keyup 合成 click 落在刚获得焦点的关闭按钮上 —— 问题 R4）
 * - Tab / Shift+Tab 在弹层内循环圈定（焦点不出弹层）
 * - Esc 统一关闭；关闭后焦点恢复到触发元素
 */
export function useFocusTrap<T extends HTMLElement = HTMLElement>(opts: {
  active?: boolean;
  onClose: () => void;
}) {
  const { active = true, onClose } = opts;
  const ref = useRef<T>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // 记录 opener + 初始聚焦（延迟一帧）+ Esc + Tab 圈定
  useEffect(() => {
    if (!active) return;
    const el = ref.current;
    if (!el) return;
    if (openerRef.current === null) {
      openerRef.current = document.activeElement as HTMLElement | null;
    }

    const focusables = (): HTMLElement[] =>
      Array.from(
        el.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
        )
      ).filter((n) => n.offsetParent !== null || n === document.activeElement);

    // 延迟到下一帧再聚焦，躲开 Enter keyup 合成 click
    const raf = requestAnimationFrame(() => {
      const first = focusables()[0];
      (first ?? el).focus();
    });

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const list = focusables();
      if (list.length === 0) {
        e.preventDefault();
        el.focus();
        return;
      }
      const first = list[0];
      const last = list[list.length - 1];
      const cur = document.activeElement as HTMLElement | null;
      if (e.shiftKey) {
        if (cur === first || cur === el || !el.contains(cur)) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (cur === last || !el.contains(cur)) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    // 捕获阶段监听，确保圈定优先于页面其它 Tab 处理
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("keydown", onKeyDown, true);
      // 关闭后焦点恢复触发元素（若仍在文档中）
      const opener = openerRef.current;
      openerRef.current = null;
      if (opener && document.contains(opener)) {
        // 同样延迟一帧，避免与关闭动画/卸载时序竞争
        requestAnimationFrame(() => opener.focus());
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  return ref;
}
