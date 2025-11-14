# -*- coding: utf-8 -*-
import asyncio
from typing import Any, Coroutine

from patchright.async_api import Playwright, async_playwright

from social_auto_upload.utils.base_social_media import set_init_script


async def del_task(playwright: Playwright) -> None:
    # 使用 Chromium 浏览器启动一个浏览器实例
    browser = await playwright.chromium.launch(
        headless=False,
        args=['--start-maximized']  # 添加启动参数以最大化窗口
    )

    # 创建一个浏览器上下文，使用指定的 cookie 文件
    context = await browser.new_context(storage_state=r"E:\IDEA\workspace\ctm\src\publish\cookies\douyin_uploader\1225_0221_爱吃水果的妈妈_account.json")
    context = await set_init_script(context)
    # 创建一个新的页面
    page = await context.new_page()
    await page.goto('https://www.xingtu.cn/sup/creator/user/task', timeout=5000000)
    await page.click('#tab-2')
    await asyncio.sleep(5)

    # 等待元素可见
    # await page.wait_for_selector('text="查看详情"', state='visible', timeout=30000)

    # 获取所有符合条件的元素
    view_detail_elements = await page.locator('text="查看详情"').all()
    print(f"找到 {len(view_detail_elements)} 个'查看详情'元素")

    for i, element in enumerate(view_detail_elements):
        try:
            print(f"正在处理第 {i+1} 个任务")

            # 确保元素可见并可交互
            await element.scroll_into_view_if_needed()
            await page.wait_for_timeout(1000)  # 等待滚动完成

            # 检查元素是否可见和可用
            # is_visible = await element.is_visible()
            # if not is_visible:
            #     print(f"第 {i+1} 个元素不可见，跳过")
            #     continue

            # 点击元素
            async with page.expect_popup() as popup_info:
                await element.evaluate('el => el.click()')
            detail_page = await popup_info.value
            print(f"已点击第 {i+1} 个'查看详情'元素")

            # 等待详情页面加载
            await detail_page.wait_for_timeout(2000)

            # 尝试点击"退出任务"
            try:
                exit_btn = detail_page.locator('text="退出任务"').first
                await exit_btn.evaluate('el => el.click()')
                print("已点击退出任务")
            except Exception as e:
                print(f"点击退出任务失败: {e}")
                # 继续尝试其他方式
                continue

            # 尝试勾选同意复选框
            try:
                agree_checkbox = detail_page.locator('.el-checkbox__inner').first
                await agree_checkbox.wait_for(state='visible', timeout=3000)
                await agree_checkbox.click()
                print("已勾选同意复选框")
            except Exception as e:
                print(f"勾选同意复选框失败: {e}")
                # 可能不需要勾选或者元素不存在
                pass

            # 尝试点击确认退出按钮
            try:
                confirm_exit_btn = detail_page.locator('button:has-text("退出任务"):visible').first
                await confirm_exit_btn.wait_for(state='visible', timeout=5000)
                await confirm_exit_btn.click()
                print("已确认退出任务")
            except Exception as e:
                print(f"确认退出任务失败: {e}")
                # 尝试其他可能的选择器
                try:
                    confirm_btn = detail_page.locator('button:has-text("确定"), button:has-text("确认"), button:has-text("退出")').first
                    await confirm_btn.wait_for(state='visible', timeout=3000)
                    await confirm_btn.click()
                    print("已通过其他按钮确认退出")
                except:
                    print("无法找到确认退出按钮")

                await detail_page.close()
                print(f"已关闭第 {i+1} 个任务的详情页面")

                # 回到主页面并刷新
                await page.bring_to_front()
                await page.reload()
                await asyncio.sleep(3)

                # 重新点击"进行中"选项卡
                await page.click('div:has-text("进行中 ")')
                await asyncio.sleep(3)

                # 重新获取"查看详情"元素列表
                view_detail_elements = await page.locator('text="查看详情"').all()
                print(f"剩余 {len(view_detail_elements)} 个任务待处理")
        except Exception as e:
            print(f"处理第 {i+1} 个任务时出错: {e}")
            # 如果出错，尝试返回任务列表页面
            try:
                if not page.url.endswith('/task'):
                    await page.goto('https://www.xingtu.cn/sup/creator/user/task')
                    await page.click('div:has-text("#tab-2")')
                    await asyncio.sleep(3)
            except:
                print("无法返回任务列表页面")

            continue  # 继续处理下一个任务

    # 关闭浏览器
    await browser.close()


async def main():
    async with async_playwright() as playwright:
        await del_task(playwright)

# Run the async function
if __name__ == "__main__":
    asyncio.run(main())