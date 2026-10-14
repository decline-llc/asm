# 前端核心交互冒烟脚本（仅开发期使用，非交付物）
# 覆盖验收链路：概览 → 复核 → 证据透镜 → 资产筛选 → 导出 → 任务向导 → 图谱
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:6100"
errors = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        errors.append(name)


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(accept_downloads=True)
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)

    # 1. 概览
    pg.goto(BASE, wait_until="networkidle")
    check("概览标题", "项目概览" in pg.locator("h2").first.inner_text())
    stats = [pg.locator(".stat-card .value").nth(i).inner_text() for i in range(4)]
    check("四项指标渲染", all(s.isdigit() for s in stats), ",".join(stats))

    # 2. 从待核对项进入复核
    pg.locator(".lead-item").first.click()
    pg.wait_for_selector("text=证据复核")
    check("进入证据复核", "证据复核" in pg.locator("h2").first.inner_text())
    check("工作台展示观测事实", "观测事实" in pg.content())

    # 3. 打开关联资产详情 → 证据透镜
    btn = pg.locator("button", has_text="打开关联资产详情")
    if btn.count() > 0:
        btn.first.click()
        pg.wait_for_selector(".drawer")
        pg.locator(".drawer .tabs button", has_text="证据").click()
        check("证据透镜三栏", pg.locator(".lens-col").count() == 3)
        pg.locator(".drawer .tabs button", has_text="DNS").click()
        check("DNS 页签 fake-IP 标注", "fake-IP" in pg.locator(".drawer").inner_text())
        pg.locator(".drawer .tabs button", has_text="Web 与截图").click()
        check(
            "截图状态展示",
            pg.locator(".drawer .shot, .drawer .shot-state").count() >= 1,
        )
        pg.keyboard.press("Escape")
        check("Esc 关闭抽屉", pg.locator(".drawer").count() == 0)
    else:
        check("首条线索含关联资产", False, "未找到按钮")

    # 4. 资产探索筛选
    pg.locator(".nav-item", has_text="资产探索").click()
    pg.wait_for_selector("table.data")
    before = pg.locator(".count-note").first.inner_text()
    pg.locator('select[aria-label="按公司筛选"]').select_option(label="澄川科技")
    pg.wait_for_timeout(200)
    after = pg.locator(".count-note").first.inner_text()
    check("公司筛选生效", before != after, f"{before} -> {after}")
    check("筛选芯片数量正确", "已筛选" in after)

    # 4b. 导出 CSV（真实下载）
    with pg.expect_download() as dl:
        pg.locator("button", has_text="导出当前结果 CSV").click()
    f = dl.value
    path = f.path()
    content = open(path, "rb").read().decode("utf-8-sig")
    check("CSV 下载成功", "资产" in content.splitlines()[0], content.splitlines()[0][:40])
    check("CSV BOM 处理中文", content.startswith("序号"))

    # 5. 隔离候选不出现在可信总表
    pg.locator(".tabs button", has_text="隔离候选").click()
    pg.wait_for_timeout(150)
    check("隔离区警示文案", "永不进入可信资产统计" in pg.content())

    # 6. 证据复核添加备注
    pg.locator(".nav-item", has_text="证据复核").click()
    pg.wait_for_selector(".lead-item")
    pg.locator('input[aria-label="添加备注"]').fill("已与网络组确认上游链路异常（冒烟测试备注）")
    pg.locator("button", has_text="添加").first.click()
    pg.wait_for_timeout(200)
    check("备注添加成功", "冒烟测试备注" in pg.content())
    pg.locator("button", has_text="已复核").first.click()
    pg.wait_for_timeout(150)
    check("状态标记已复核", pg.locator(".lead-item .badge", has_text="已复核").count() >= 1)

    # 7. 任务向导四步创建 + 模拟推进
    pg.locator(".nav-item", has_text="调查任务").click()
    pg.wait_for_selector("text=新建调查")
    pg.locator("button", has_text="新建调查").first.click()
    pg.wait_for_selector(".wizard-steps")
    pg.locator("button", has_text="下一步").click()
    pg.locator("button", has_text="下一步").click()
    pg.locator("button", has_text="下一步").click()
    pg.locator("button", has_text="创建演示任务").click()
    pg.wait_for_selector("text=阶段流程")
    check("演示任务创建", "DEMO-" in pg.content())
    pg.locator("button", has_text="模拟推进一阶段").click()
    pg.wait_for_timeout(200)
    check("模拟推进生效", "演示任务已创建" in pg.content() or "等待" in pg.content())

    # 8. 历史任务重试失败子任务
    pg.locator("button", has_text="返回任务列表").click()
    pg.locator(".lead-item", has_text="RUN-20261009-01").click()
    pg.wait_for_selector("text=工具子任务")
    retry = pg.locator("button", has_text="重试（模拟）")
    if retry.count() > 0:
        retry.first.click()
        pg.wait_for_timeout(200)
        check("失败项重试成功", "重试成功" in pg.content())
    else:
        check("失败项重试成功", False, "无重试按钮")

    # 9. 关系图谱
    pg.locator(".nav-item", has_text="关系图谱").click()
    pg.wait_for_selector(".graph-wrap svg")
    check("图谱渲染节点", pg.locator(".gnode").count() >= 20, str(pg.locator(".gnode").count()))
    pg.locator(".gnode").nth(6).click()
    pg.wait_for_timeout(200)
    check("节点聚焦邻域卡", "邻域关系" in pg.content())

    # 10. 数据来源与报告
    pg.locator(".nav-item", has_text="数据来源").click()
    pg.wait_for_timeout(150)
    check("来源能力分级", "主流程已接入" in pg.content() and "未配置凭据" in pg.content())
    pg.locator(".nav-item", has_text="报告中心").click()
    pg.wait_for_selector("text=汇报视图")
    pg.locator("button", has_text="工程明细").click()
    pg.wait_for_timeout(150)
    check("总表预览", "等级标注" in pg.content())
    check("隔离候选不进总表", "chengchuan-pay" not in pg.content())
    with pg.expect_download() as dl2:
        pg.locator("button", has_text="下载本表 CSV").click()
    check("报告 CSV 下载", dl2.value.suggested_filename.endswith(".csv"))

    # 11. 全局搜索 Ctrl+K
    pg.keyboard.press("Control+k")
    pg.wait_for_selector(".search-modal input")
    pg.locator(".search-modal input").fill("lab.example.com")
    pg.wait_for_timeout(250)
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(300)
    check("搜索跳转资产", pg.locator(".drawer, table.data").count() >= 1)

    # 12. localStorage 持久化
    saved = pg.evaluate("localStorage.getItem('asm-workbench-local-v1')")
    check("本地状态持久化", saved is not None and "leadNotes" in saved)

    # 13. 窄屏（390px）布局检查
    pg2 = b.new_page(viewport={"width": 390, "height": 844})
    pg2.goto(BASE, wait_until="networkidle")
    check("窄屏渲染", pg2.locator(".stat-card").count() >= 4)
    check("窄屏筛选入口不消失", pg2.locator(".nav-item").count() >= 6)

    b.close()

print()
if errors:
    print("FAILURES:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("ALL SMOKE TESTS PASSED")
