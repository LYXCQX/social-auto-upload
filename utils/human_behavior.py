import asyncio
import random
import math
from typing import Optional

class HumanBehaviorSimulator:
    """人类行为模拟器，用于模拟真实用户行为避免被检测"""
    
    def __init__(self):
        self.typing_speed = random.uniform(0.1, 0.3)  # 打字间隔时间
        self.mouse_movement_variance = 0.1  # 鼠标移动变异度
        self.scroll_speed = random.uniform(100, 300)  # 滚动速度
        
    async def human_type(self, page, selector: str, text: str, delay_range: tuple = (50, 150)):
        """模拟人类打字行为"""
        element = page.locator(selector)
        await element.click()
        
        # 随机延迟开始打字
        await asyncio.sleep(random.uniform(0.2, 0.8))
        
        for char in text:
            await element.type(char)
            # 随机打字间隔
            delay = random.randint(delay_range[0], delay_range[1])
            await asyncio.sleep(delay / 1000)
            
            # 偶尔暂停思考
            if random.random() < 0.1:
                await asyncio.sleep(random.uniform(0.5, 2.0))
    
    async def human_click(self, page, selector: str, delay_before: tuple = (100, 500), 
                         offset_variance: int = 5):
        """模拟人类点击行为"""
        # 点击前的随机延迟
        await asyncio.sleep(random.randint(delay_before[0], delay_before[1]) / 1000)
        
        element = page.locator(selector)
        
        # 获取元素位置并添加随机偏移
        box = await element.bounding_box()
        if box:
            x = box['x'] + box['width'] / 2 + random.randint(-offset_variance, offset_variance)
            y = box['y'] + box['height'] / 2 + random.randint(-offset_variance, offset_variance)
            
            # 先移动鼠标到附近位置
            await self.human_mouse_move(page, x + random.randint(-20, 20), y + random.randint(-20, 20))
            await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # 再移动到目标位置并点击
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.05, 0.15))
            await page.mouse.click(x, y)
        else:
            # 如果无法获取位置，使用普通点击
            await element.click()
    
    async def human_mouse_move(self, page, x: float, y: float, steps: int = None):
        """模拟人类鼠标移动轨迹"""
        if steps is None:
            steps = random.randint(10, 30)
        
        # 获取当前鼠标位置（模拟）
        current_x = random.randint(100, 800)
        current_y = random.randint(100, 600)
        
        # 计算移动路径
        for i in range(steps):
            progress = i / steps
            # 使用贝塞尔曲线模拟自然鼠标移动
            intermediate_x = current_x + (x - current_x) * progress
            intermediate_y = current_y + (y - current_y) * progress
            
            # 添加随机抖动
            jitter_x = random.uniform(-self.mouse_movement_variance, self.mouse_movement_variance)
            jitter_y = random.uniform(-self.mouse_movement_variance, self.mouse_movement_variance)
            
            await page.mouse.move(
                intermediate_x + jitter_x,
                intermediate_y + jitter_y
            )
            
            # 随机延迟
            await asyncio.sleep(random.uniform(0.01, 0.03))
    
    async def human_scroll(self, page, direction: str = "down", amount: int = None, 
                          smooth: bool = True):
        """模拟人类滚动行为"""
        if amount is None:
            amount = random.randint(200, 800)
        
        scroll_direction = 1 if direction == "down" else -1
        
        if smooth:
            # 平滑滚动
            steps = random.randint(5, 15)
            step_amount = amount / steps
            
            for _ in range(steps):
                await page.mouse.wheel(0, scroll_direction * step_amount)
                await asyncio.sleep(random.uniform(0.1, 0.2))
        else:
            # 一次性滚动
            await page.mouse.wheel(0, scroll_direction * amount)
        
        # 滚动后随机停顿
        await asyncio.sleep(random.uniform(0.5, 2.0))
    
    async def random_page_interaction(self, page, duration: float = 30):
        """随机页面交互，增加真实性"""
        end_time = asyncio.get_event_loop().time() + duration
        
        interactions = [
            self._random_mouse_movement,
            self._random_scroll,
            self._random_pause,
            self._random_focus_change
        ]
        
        while asyncio.get_event_loop().time() < end_time:
            interaction = random.choice(interactions)
            try:
                await interaction(page)
            except Exception as e:
                print(f"随机交互异常: {e}")
            
            await asyncio.sleep(random.uniform(2, 8))
    
    async def _random_mouse_movement(self, page):
        """随机鼠标移动"""
        x = random.randint(100, 1200)
        y = random.randint(100, 800)
        await self.human_mouse_move(page, x, y)
    
    async def _random_scroll(self, page):
        """随机滚动"""
        direction = random.choice(["up", "down"])
        await self.human_scroll(page, direction, random.randint(100, 400))
    
    async def _random_pause(self, page):
        """随机暂停"""
        await asyncio.sleep(random.uniform(1, 5))
    
    async def _random_focus_change(self, page):
        """随机焦点变化"""
        try:
            # 随机点击页面某个位置
            x = random.randint(200, 1000)
            y = random.randint(200, 600)
            await page.mouse.click(x, y)
        except:
            pass
    
    async def simulate_reading_behavior(self, page, min_time: float = 5, max_time: float = 15):
        """模拟阅读行为"""
        reading_time = random.uniform(min_time, max_time)
        end_time = asyncio.get_event_loop().time() + reading_time
        
        while asyncio.get_event_loop().time() < end_time:
            # 模拟阅读中的随机行为
            action = random.choice([
                'scroll_read',
                'pause_think', 
                'micro_movement',
                'focus_change'
            ])
            
            if action == 'scroll_read':
                # 慢速阅读滚动
                await self.human_scroll(page, "down", random.randint(50, 200), smooth=True)
            elif action == 'pause_think':
                # 思考暂停
                await asyncio.sleep(random.uniform(2, 8))
            elif action == 'micro_movement':
                # 微小鼠标移动
                current_pos = await page.mouse.move(
                    random.randint(400, 800), 
                    random.randint(300, 600)
                )
            elif action == 'focus_change':
                # 焦点变化
                await page.mouse.click(random.randint(200, 1000), random.randint(200, 600))
            
            await asyncio.sleep(random.uniform(0.5, 3))
    
    async def add_behavior_script(self, context):
        """添加浏览器行为脚本"""
        behavior_script = """
        // 人类行为模拟脚本
        (function() {
            'use strict';
            
            // === 1. 鼠标移动轨迹伪装 ===
            let lastMouseMove = Date.now();
            const mouseHistory = [];
            
            // 记录真实鼠标移动
            document.addEventListener('mousemove', function(e) {
                const now = Date.now();
                mouseHistory.push({
                    x: e.clientX,
                    y: e.clientY,
                    time: now,
                    timeDiff: now - lastMouseMove
                });
                lastMouseMove = now;
                
                // 保持最近100个移动记录
                if (mouseHistory.length > 100) {
                    mouseHistory.shift();
                }
            });
            
            // === 2. 键盘输入行为伪装 ===
            const keyTimings = [];
            let lastKeyTime = 0;
            
            document.addEventListener('keydown', function(e) {
                const now = Date.now();
                keyTimings.push({
                    key: e.key,
                    time: now,
                    interval: now - lastKeyTime
                });
                lastKeyTime = now;
                
                if (keyTimings.length > 50) {
                    keyTimings.shift();
                }
            });
            
            // === 3. 滚动行为伪装 ===
            let scrollHistory = [];
            let lastScrollTime = 0;
            
            window.addEventListener('scroll', function(e) {
                const now = Date.now();
                scrollHistory.push({
                    scrollY: window.scrollY,
                    time: now,
                    interval: now - lastScrollTime
                });
                lastScrollTime = now;
                
                if (scrollHistory.length > 30) {
                    scrollHistory.shift();
                }
            });
            
            // === 4. 焦点变化行为 ===
            let focusHistory = [];
            
            ['focus', 'blur', 'click'].forEach(eventType => {
                document.addEventListener(eventType, function(e) {
                    focusHistory.push({
                        type: eventType,
                        target: e.target.tagName,
                        time: Date.now()
                    });
                    
                    if (focusHistory.length > 20) {
                        focusHistory.shift();
                    }
                });
            });
            
            // === 5. 页面可见性变化 ===
            let visibilityChanges = [];
            
            document.addEventListener('visibilitychange', function() {
                visibilityChanges.push({
                    hidden: document.hidden,
                    time: Date.now()
                });
            });
            
            // === 6. 模拟人类行为统计 ===
            window.getHumanBehaviorStats = function() {
                return {
                    mouseMovements: mouseHistory.length,
                    averageMouseSpeed: mouseHistory.length > 1 ? 
                        mouseHistory.reduce((acc, curr, idx) => {
                            if (idx === 0) return acc;
                            const prev = mouseHistory[idx - 1];
                            const distance = Math.sqrt(Math.pow(curr.x - prev.x, 2) + Math.pow(curr.y - prev.y, 2));
                            const time = curr.time - prev.time;
                            return acc + (distance / time);
                        }, 0) / (mouseHistory.length - 1) : 0,
                    keystrokes: keyTimings.length,
                    scrollEvents: scrollHistory.length,
                    focusChanges: focusHistory.length,
                    visibilityChanges: visibilityChanges.length,
                    totalInteractionTime: Date.now() - (mouseHistory[0]?.time || Date.now())
                };
            };
            
            // === 7. 随机微动作 ===
            setInterval(function() {
                if (Math.random() < 0.1) { // 10%概率
                    // 模拟轻微鼠标抖动
                    const event = new MouseEvent('mousemove', {
                        clientX: Math.random() * window.innerWidth,
                        clientY: Math.random() * window.innerHeight,
                        bubbles: true
                    });
                    document.dispatchEvent(event);
                }
            }, Math.random() * 5000 + 2000);
            
            console.log('🤖 人类行为模拟脚本已激活');
        })();
        """
        
        await context.add_init_script(behavior_script)

# 创建全局实例
human_behavior = HumanBehaviorSimulator() 