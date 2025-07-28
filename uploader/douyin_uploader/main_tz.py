from playwright.async_api import Page
from social_auto_upload.utils.log import douyin_logger


async def add_declaration(parent_, page: Page):
    """添加声明"""
    try:
        # 检查info中是否有declaration且不为"不声明"
        if not parent_.info:
            douyin_logger.info('[-] 没有info信息，跳过声明添加')
            return

        declaration = parent_.info.get('declaration', '')
        if not declaration or declaration == '不声明':
            douyin_logger.info('[-] 没有声明内容或选择不声明，跳过声明添加')
            return

        douyin_logger.info(f'[+] 开始添加声明: {declaration}')

        # 点击"添加声明"按钮
        add_declaration_button = page.locator('p:has-text("添加声明")')
        if await add_declaration_button.count() > 0:
            await add_declaration_button.click()
            douyin_logger.info('[+] 点击了添加声明按钮')

            # 等待弹出框出现
            await page.wait_for_selector('.semi-sidesheet-content', timeout=10000)
            douyin_logger.info('[+] 声明选择弹出框已出现')

            # 在弹出框中查找对应的声明选项，尝试多种选择器
            declaration_selected = False

            # 方法1: 尝试点击包含文本的radio标签
            try:
                radio_label = page.locator(f'.semi-sidesheet-content .semi-radio:has-text("{declaration}")')
                if await radio_label.count() > 0:
                    await radio_label.click()
                    declaration_selected = True
                    douyin_logger.info(f'[+] 通过radio标签成功选择声明: {declaration}')
            except Exception as e:
                douyin_logger.warning(f'[!] 通过radio标签点击失败: {str(e)}')

            # 方法2: 如果方法1失败，尝试点击span的父级label元素
            if not declaration_selected:
                try:
                    parent_label = page.locator(f'.semi-sidesheet-content label:has(span:has-text("{declaration}"))')
                    if await parent_label.count() > 0:
                        await parent_label.click()
                        declaration_selected = True
                        douyin_logger.info(f'[+] 通过父级label成功选择声明: {declaration}')
                except Exception as e:
                    douyin_logger.warning(f'[!] 通过父级label点击失败: {str(e)}')

            # 方法3: 如果前面都失败，尝试强制点击span元素
            if not declaration_selected:
                try:
                    declaration_span = page.locator(f'.semi-sidesheet-content span:has-text("{declaration}")')
                    if await declaration_span.count() > 0:
                        await declaration_span.click(force=True)
                        declaration_selected = True
                        douyin_logger.info(f'[+] 通过强制点击span成功选择声明: {declaration}')
                except Exception as e:
                    douyin_logger.warning(f'[!] 强制点击span失败: {str(e)}')

            if declaration_selected:
                # 等待一下让选择生效
                await page.wait_for_timeout(500)

                # 点击确定按钮关闭弹出框
                confirm_button = page.locator('.semi-sidesheet-content button:has-text("确定")')
                if await confirm_button.count() > 0:
                    await confirm_button.click()
                    douyin_logger.info('[+] 点击确定按钮关闭弹出框')
                else:
                    # 尝试其他可能的确定按钮选择器
                    confirm_button = page.locator('.semi-sidesheet-content .semi-button-primary')
                    if await confirm_button.count() > 0:
                        await confirm_button.click()
                        douyin_logger.info('[+] 点击确定按钮关闭弹出框')
                    else:
                        douyin_logger.warning('[!] 未找到确定按钮')

                # 等待弹出框关闭
                await page.wait_for_timeout(1000)
                douyin_logger.info('[+] 声明添加完成')
            else:
                douyin_logger.warning(f'[!] 所有方法都无法选择声明选项: {declaration}')
        else:
            douyin_logger.warning('[!] 未找到添加声明按钮')

    except Exception as e:
        douyin_logger.error(f'[!] 添加声明失败: {str(e)}')


async def add_goods(parent_, page):
    if parent_.goods:
        await page.click('text="位置"')
        await page.click('text="购物车"')
        await page.locator('input[placeholder="粘贴商品链接"]').fill(parent_.goods.itemLinkUrl)
        await page.click('text="添加链接"')
        await page.locator('input[placeholder="请输入商品短标题"]').fill(parent_.goods.itemTitle)
        await page.click('text="完成编辑"')


async def get_title_tag(self, page):
    # 等待硬性要求标签出现
    await page.wait_for_timeout(1000)
    hard_req_element = page.locator('text="硬性要求"')
    if await hard_req_element.count() > 0:
        # 获取硬性要求的内容
        hard_req_content = await hard_req_element.locator("..").text_content()
        douyin_logger.info(f'[+] 获取到硬性要求原始内容: {hard_req_content}')

        # 按照规则提取硬性要求：以每个"#"和"@"符号及其后续的空格作为独立要求的分隔标识
        hard_requirements = self.extract_hard_requirements(hard_req_content)

        if hard_requirements:
            # 将所有硬性要求按原有结构和顺序组合到标题前
            requirements_text = " ".join(hard_requirements)
            self.title = f"{requirements_text.replace('！', '！！')} {self.title}"
            douyin_logger.info(f'[+] 提取到 {len(hard_requirements)} 个硬性要求')
            douyin_logger.info(f'[+] 硬性要求列表: {hard_requirements}')
            douyin_logger.info(f'[+] 最终标题: {self.title}')
        else:
            douyin_logger.info("[-] 硬性要求中没有找到以#或@开头的要求项")
    else:
        douyin_logger.info("[-] 没有找到硬性要求标签")


def extract_hard_requirements(self, content):
    """
    提取硬性要求，按照规则处理：
    1. 不要将所有内容都提前处理或合并
    2. 以每个"#"和"@"符号作为独立标签进行提取
    3. 支持从行内提取多个#和@标签
    4. 保持每个标签的独立性，按原有的结构和顺序进行提取
    5. 确保在提取过程中不丢失或合并任何以"#"或"@"标识的标签
    """
    if not content:
        return []

    requirements = []
    import re
    line = content.strip()

    # 方法1: 查找以"#"或"@"开头的行（保持原有逻辑）
    if line.startswith('#') or line.startswith('@'):
        requirements.append(line)
        douyin_logger.info(f'[+] 提取硬性要求条目（整行）: {line}')
    else:
        # 方法2: 从行内提取所有#和@标签
        # 使用正则表达式匹配 #标签 和 @用户
        hash_tags = re.findall(r'#[^\s#@]+', line)
        at_tags = re.findall(r'@[^\s#@]+', line)

        # 添加找到的#标签，去除标点符号
        for tag in hash_tags:
            cleaned_tag = self.clean_tag_punctuation(tag)
            if cleaned_tag:  # 只添加非空的清理后标签
                requirements.append(cleaned_tag)
                if cleaned_tag != tag:
                    douyin_logger.info(f'[+] 提取硬性要求条目（#标签）: {tag} -> {cleaned_tag}')
                else:
                    douyin_logger.info(f'[+] 提取硬性要求条目（#标签）: {tag}')

        # 添加找到的@标签，去除标点符号
        for tag in at_tags:
            cleaned_tag = self.clean_tag_punctuation(tag)
            if cleaned_tag:  # 只添加非空的清理后标签
                requirements.append(cleaned_tag)
                if cleaned_tag != tag:
                    douyin_logger.info(f'[+] 提取硬性要求条目（@标签）: {tag} -> {cleaned_tag}')
                else:
                    douyin_logger.info(f'[+] 提取硬性要求条目（@标签）: {tag}')

    return requirements


def clean_tag_punctuation(self, tag):
    """
    清理标签中的标点符号
    保留标签开头的#或@符号，去除其他标点符号
    """
    if not tag:
        return tag

    import string

    # 保存开头的#或@符号
    prefix = ''
    content = tag
    if tag.startswith('#'):
        prefix = '#'
        content = tag[1:]
    elif tag.startswith('@'):
        prefix = '@'
        content = tag[1:]

    # 定义要去除的标点符号（保留一些常用字符）
    # 去除常见的中英文标点符号，但保留下划线、连字符等
    punctuation_to_remove = '！？。，、；：""''（）【】《》〈〉「」『』〔〕…—–-·•'
    punctuation_to_remove += string.punctuation.replace('_', '').replace('-', '')

    # 去除标点符号
    cleaned_content = ''.join(char for char in content if char not in punctuation_to_remove)

    # 如果清理后内容为空，返回空字符串
    if not cleaned_content.strip():
        return ''

    # 返回清理后的标签
    cleaned_tag = prefix + cleaned_content

    return cleaned_tag
