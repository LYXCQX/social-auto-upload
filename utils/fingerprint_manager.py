import pickle
import sqlite3
import json
import random
import os
from datetime import datetime

from browserforge.fingerprints import FingerprintGenerator
from social_auto_upload.conf import BASE_DIR
from social_auto_upload.utils.log import douyin_logger

class FingerprintManager:
    def __init__(self):
        db_dir = os.path.join(BASE_DIR, 'db')
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = os.path.join(db_dir, 'ctm.db')
        self.init_db()
    
    def init_db(self):
        """初始化指纹数据库"""
        # 确保数据库目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # 浏览器指纹表
        c.execute('''CREATE TABLE IF NOT EXISTS fingerprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cookie_name TEXT UNIQUE NOT NULL,
            fingerprint_data TEXT NOT NULL,
            created_time TEXT DEFAULT CURRENT_TIMESTAMP,
            last_used TEXT
        )''')
        
        conn.commit()
        conn.close()
    
    def generate_random_fingerprint(self):
        """生成随机浏览器指纹 - 确保各参数一致性"""
        
        # 定义操作系统配置组合，确保User-Agent与平台一致
        os_configs = [
            {
                "type": "windows",
                "user_agents": [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ],
                "platform": "Win32",
                "os_name": "Windows",
                "fonts": [
                    "Arial", "Helvetica", "Times New Roman", "Courier New", "Verdana",
                    "Georgia", "Palatino", "Garamond", "Bookman", "Tahoma",
                    "Comic Sans MS", "Impact", "Arial Black", "Segoe UI", "Calibri",
                    "Microsoft YaHei", "SimSun", "SimHei"
                ],
                "plugins": [
                    {"name": "Chrome PDF Plugin", "filename": "internal-pdf-viewer", "description": "Portable Document Format"},
                    {"name": "Chrome PDF Viewer", "filename": "mhjfbmdgcfjbbpaeojofohoefgiehjai", "description": "Chrome PDF Viewer"},
                    {"name": "Native Client", "filename": "internal-nacl-plugin", "description": "Native Client Executable"},
                    {"name": "Widevine Content Decryption Module", "filename": "widevinecdmadapter.dll", "description": "Enables Widevine licenses"}
                ]
            },
            {
                "type": "macos",
                "user_agents": [
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ],
                "platform": "MacIntel",
                "os_name": "Mac OS",
                "fonts": [
                    "Arial", "Helvetica", "Times New Roman", "Courier New", "Verdana",
                    "Georgia", "Palatino", "Garamond", "Bookman", "Tahoma",
                    "Helvetica Neue", "Lucida Grande", "Monaco", "Menlo", "SF Pro Display",
                    "PingFang SC", "Hiragino Sans GB"
                ],
                "plugins": [
                    {"name": "Chrome PDF Plugin", "filename": "internal-pdf-viewer", "description": "Portable Document Format"},
                    {"name": "Chrome PDF Viewer", "filename": "mhjfbmdgcfjbbpaeojofohoefgiehjai", "description": "Chrome PDF Viewer"},
                    {"name": "Native Client", "filename": "internal-nacl-plugin", "description": "Native Client Executable"},
                    {"name": "Widevine Content Decryption Module", "filename": "libwidevinecdm.dylib", "description": "Enables Widevine licenses"}
                ]
            },
            # {
            #     "type": "linux",
            #     "user_agents": [
            #         "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            #         "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            #         "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            #         "Mozilla/5.0 (X11; Fedora; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            #     ],
            #     "platform": "Linux x86_64",
            #     "os_name": "Linux",
            #     "fonts": [
            #         "Arial", "Helvetica", "Times New Roman", "Courier New", "Verdana",
            #         "Georgia", "Palatino", "Garamond", "Bookman", "Tahoma",
            #         "Roboto", "Ubuntu", "Cantarell", "DejaVu Sans", "Liberation Sans",
            #         "Noto Sans CJK SC", "WenQuanYi Micro Hei"
            #     ],
            #     "plugins": [
            #         {"name": "Chrome PDF Plugin", "filename": "internal-pdf-viewer", "description": "Portable Document Format"},
            #         {"name": "Chrome PDF Viewer", "filename": "mhjfbmdgcfjbbpaeojofohoefgiehjai", "description": "Chrome PDF Viewer"},
            #         {"name": "Native Client", "filename": "internal-nacl-plugin", "description": "Native Client Executable"},
            #         {"name": "Widevine Content Decryption Module", "filename": "libwidevinecdm.so", "description": "Enables Widevine licenses"}
            #     ]
            # }
        ]
        
        # 定义地区配置，确保时区、语言、IP地理位置一致
        region_configs = [
            {
                "region": "china",
                "timezones": ["Asia/Shanghai", "Asia/Hong_Kong"],
                "languages": [
                    ["zh-CN", "zh", "en"],
                    ["zh-CN", "en-US", "en"],
                    ["zh-Hans-CN", "zh", "en-US"]
                ],
                "locale": "zh-CN"
            },
            {
                "region": "taiwan",
                "timezones": ["Asia/Taipei"],
                "languages": [
                    ["zh-TW", "zh", "en"],
                    ["zh-Hant-TW", "zh", "en-US"]
                ],
                "locale": "zh-TW"
            },
            {
                "region": "japan",
                "timezones": ["Asia/Tokyo"],
                "languages": [
                    ["ja-JP", "ja", "en"],
                    ["ja", "en-US", "zh"]
                ],
                "locale": "ja-JP"
            },
            {
                "region": "korea",
                "timezones": ["Asia/Seoul"],
                "languages": [
                    ["ko-KR", "ko", "en"],
                    ["ko", "en-US", "zh"]
                ],
                "locale": "ko-KR"
            },
            {
                "region": "us",
                "timezones": ["America/New_York", "America/Los_Angeles", "America/Chicago"],
                "languages": [
                    ["en-US", "en"],
                    ["en-US", "en", "es"],
                    ["en", "zh-CN"]
                ],
                "locale": "en-US"
            },
            {
                "region": "uk",
                "timezones": ["Europe/London"],
                "languages": [
                    ["en-GB", "en"],
                    ["en-GB", "en", "fr"]
                ],
                "locale": "en-GB"
            }
        ]
        
        # 屏幕分辨率配置（主流分辨率）
        screen_configs = [
            {"width": 1920, "height": 1080, "viewport": {"width": 1920, "height": 937}},  # 1080p
            {"width": 1366, "height": 768, "viewport": {"width": 1366, "height": 625}},   # 常见笔记本
            {"width": 1440, "height": 900, "viewport": {"width": 1440, "height": 757}},   # MacBook Air
            {"width": 1536, "height": 864, "viewport": {"width": 1536, "height": 721}},   # Surface
            {"width": 1680, "height": 1050, "viewport": {"width": 1680, "height": 907}},  # 20寸
            {"width": 2560, "height": 1440, "viewport": {"width": 2560, "height": 1297}}, # 2K
            {"width": 1600, "height": 900, "viewport": {"width": 1600, "height": 757}},   # 16:9
            {"width": 2880, "height": 1800, "viewport": {"width": 2880, "height": 1657}}, # MacBook Pro
            {"width": 3840, "height": 2160, "viewport": {"width": 3840, "height": 2017}}  # 4K
        ]
        
        # 硬件配置（符合实际设备规格）
        hardware_configs = [
            {"cores": 4, "memory": 8, "gpu": "Intel", "gpu_detail": "Intel(R) UHD Graphics 620"},
            {"cores": 6, "memory": 16, "gpu": "NVIDIA", "gpu_detail": "NVIDIA GeForce GTX 1660"},
            {"cores": 8, "memory": 16, "gpu": "AMD", "gpu_detail": "AMD Radeon RX 580"},
            {"cores": 4, "memory": 8, "gpu": "Intel", "gpu_detail": "Intel(R) Iris Xe Graphics"},
            {"cores": 8, "memory": 32, "gpu": "NVIDIA", "gpu_detail": "NVIDIA GeForce RTX 3060"},
            {"cores": 12, "memory": 32, "gpu": "AMD", "gpu_detail": "AMD Radeon RX 6600 XT"},
            {"cores": 16, "memory": 64, "gpu": "NVIDIA", "gpu_detail": "NVIDIA GeForce RTX 4070"}
        ]
        
        # 随机选择配置组合
        os_config = random.choice(os_configs)
        region_config = random.choice(region_configs)
        screen_config = random.choice(screen_configs)
        hardware_config = random.choice(hardware_configs)
        selected_language = random.choice(region_config["languages"])
        
        # 生成WebGL渲染器信息（与GPU匹配）
        webgl_renderers = {
            "Intel": [
                f"ANGLE (Intel, {hardware_config['gpu_detail']} Direct3D11 vs_5_0 ps_5_0, D3D11)",
                f"Intel {hardware_config['gpu_detail'].split('Intel(R) ')[-1]}",
            ],
            "NVIDIA": [
                f"ANGLE (NVIDIA, {hardware_config['gpu_detail']} Direct3D11 vs_5_0 ps_5_0, D3D11)",
                f"NVIDIA {hardware_config['gpu_detail'].split('NVIDIA GeForce ')[-1]}/PCIe/SSE2",
            ],
            "AMD": [
                f"ANGLE (AMD, {hardware_config['gpu_detail']} Direct3D11 vs_5_0 ps_5_0, D3D11)",
                f"AMD {hardware_config['gpu_detail'].split('AMD Radeon ')[-1]} (0x00007300)",
            ]
        }
        
        # 构建一致性指纹
        fingerprint = {
            "userAgent": random.choice(os_config["user_agents"]),
            "viewport": screen_config["viewport"],
            "screen": {
                "width": screen_config["width"],
                "height": screen_config["height"],
                "colorDepth": random.choice([24, 32]),
                "pixelDepth": random.choice([24, 32])
            },
            "timezone": random.choice(region_config["timezones"]),
            "language": selected_language[0],
            "languages": selected_language,
            "platform": os_config["platform"],
            "os_name": os_config["os_name"],
            "cookiesEnabled": True,
            "doNotTrack": random.choice([None, "1"]),
            "hardwareConcurrency": hardware_config["cores"],
            "deviceMemory": hardware_config["memory"],
            "webdriver": False,
            "permissions": {
                "notifications": random.choice(["granted", "denied", "prompt"]),
                "geolocation": random.choice(["granted", "denied", "prompt"])
            },
            "canvas": {
                "enabled": True,
                "noise": random.uniform(0.0001, 0.001)
            },
            "webgl": {
                "vendor": f"Google Inc. ({hardware_config['gpu']})",
                "renderer": random.choice(webgl_renderers[hardware_config["gpu"]])
            },
            "fonts": random.sample(os_config["fonts"], k=random.randint(12, len(os_config["fonts"]))),
            "plugins": os_config["plugins"],
            "creation_time": datetime.now().isoformat(),
            # 新增一致性标识
            "consistency": {
                "os_type": os_config["type"],
                "region": region_config["region"],
                "hardware_class": f"{hardware_config['cores']}C{hardware_config['memory']}G"
            }
        }
        
        return fingerprint
    

    
    def get_or_create_fingerprint(self, cookie_name):
        """获取或创建Cookie对应的指纹"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # 查询现有指纹
        c.execute('SELECT fingerprint_data FROM fingerprints WHERE cookie_name = ?', (cookie_name,))
        row = c.fetchone()
        
        if row:
            # 更新最后使用时间
            c.execute('UPDATE fingerprints SET last_used = ? WHERE cookie_name = ?', 
                     (datetime.now().isoformat(), cookie_name))
            conn.commit()
            conn.close()
            return pickle.loads(row[0])
        else:
            # 生成新指纹
            fg = FingerprintGenerator(browser='firefox', os=('windows', 'macos'),
                                      device='desktop')
            fingerprint = fg.generate()
            fingerprint_json = pickle.dumps(fingerprint)

            # 保存到数据库
            c.execute('''INSERT INTO fingerprints (cookie_name, fingerprint_data, last_used) 
                        VALUES (?, ?, ?)''',
                     (cookie_name, fingerprint_json, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            
            print(f"生成新浏览器指纹: {cookie_name}")
            return fingerprint
    
    def delete_fingerprint(self, cookie_name):
        """删除指纹"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute('DELETE FROM fingerprints WHERE cookie_name = ?', (cookie_name,))
            conn.commit()
            conn.close()
            
            print(f"删除浏览器指纹: {cookie_name}")
            return True, "删除成功"
        except Exception as e:
            douyin_logger.error(f"删除浏览器指纹失败: {str(e)}")
            return False, str(e)
    
    def get_all_fingerprints(self):
        """获取所有指纹信息"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''SELECT cookie_name, created_time, last_used 
                    FROM fingerprints ORDER BY created_time DESC''')
        
        fingerprints = []
        for row in c.fetchall():
            fingerprints.append({
                'cookie_name': row[0],
                'created_time': row[1],
                'last_used': row[2]
            })
        
        conn.close()
        return fingerprints
    
    def regenerate_all_fingerprints(self):
        """重新生成所有指纹（修复不一致问题）"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # 获取所有cookie名称
            c.execute('SELECT cookie_name FROM fingerprints')
            cookie_names = [row[0] for row in c.fetchall()]
            
            updated_count = 0
            for cookie_name in cookie_names:
                # 生成新的一致性指纹
                new_fingerprint = self.generate_random_fingerprint()
                fingerprint_json = json.dumps(new_fingerprint, ensure_ascii=False)
                
                # 更新数据库
                c.execute('''UPDATE fingerprints 
                           SET fingerprint_data = ?, last_used = ? 
                           WHERE cookie_name = ?''',
                         (fingerprint_json, datetime.now().isoformat(), cookie_name))
                updated_count += 1
            
            conn.commit()
            conn.close()
            
            print(f"成功重新生成 {updated_count} 个浏览器指纹")
            return True, f"成功重新生成 {updated_count} 个指纹"
            
        except Exception as e:
            douyin_logger.error(f"重新生成指纹失败: {str(e)}")
            return False, str(e)
    
    def check_fingerprint_consistency(self, cookie_name):
        """检查指纹一致性"""
        try:
            fingerprint = self.get_or_create_fingerprint(cookie_name)
            
            issues = []
            
            # 检查User-Agent与平台一致性
            user_agent = fingerprint.get('userAgent', '')
            platform = fingerprint.get('platform', '')
            
            if 'Windows' in user_agent and platform != 'Win32':
                issues.append(f"User-Agent显示Windows但平台为{platform}")
            elif 'Macintosh' in user_agent and platform != 'MacIntel':
                issues.append(f"User-Agent显示Mac但平台为{platform}")
            elif 'Linux' in user_agent and platform != 'Linux x86_64':
                issues.append(f"User-Agent显示Linux但平台为{platform}")
            
            # 检查时区与语言一致性
            timezone = fingerprint.get('timezone', '')
            language = fingerprint.get('language', '')
            
            if timezone.startswith('Asia/') and not language.startswith(('zh', 'ja', 'ko')):
                issues.append(f"亚洲时区{timezone}但语言为{language}")
            elif timezone.startswith('Europe/') and language.startswith(('zh', 'ja', 'ko')):
                issues.append(f"欧洲时区{timezone}但语言为{language}")
            elif timezone.startswith('America/') and language.startswith(('zh', 'ja', 'ko')):
                issues.append(f"美洲时区{timezone}但语言为{language}")
            
            # 检查硬件信息一致性
            cores = fingerprint.get('hardwareConcurrency', 0)
            memory = fingerprint.get('deviceMemory', 0)
            
            if cores > 16 or memory > 64:
                issues.append(f"硬件配置过高: {cores}核{memory}GB")
            
            return len(issues) == 0, issues
            
        except Exception as e:
            return False, [f"检查失败: {str(e)}"]
    
    def get_playwright_config(self, cookie_name):
        """获取Playwright浏览器配置"""
        fingerprint = self.get_or_create_fingerprint(cookie_name)
        
        # 构建Playwright的浏览器上下文配置
        config = {
            "viewport": fingerprint["viewport"],
            "user_agent": fingerprint["userAgent"],
            "locale": fingerprint["language"],
            "timezone_id": fingerprint["timezone"],
            "permissions": list(fingerprint["permissions"].keys()),
            "extra_http_headers": {
                "Accept-Language": ", ".join(fingerprint["languages"]),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1"
            }
        }
        
        return config
    
    def inject_fingerprint_script(self, fingerprint):
        """生成增强指纹注入脚本"""
        script = f"""
        // 增强浏览器指纹伪装脚本
        (function() {{
            'use strict';
            const fingerprint = {json.dumps(fingerprint)};
            
            // === 1. 基础navigator属性伪装 ===
            const defineProperty = (obj, prop, value) => {{
                Object.defineProperty(obj, prop, {{
                    get: () => value,
                    configurable: true,
                    enumerable: true
                }});
            }};
            
            defineProperty(navigator, 'userAgent', fingerprint.userAgent);
            defineProperty(navigator, 'platform', fingerprint.platform);
            defineProperty(navigator, 'language', fingerprint.language);
            defineProperty(navigator, 'languages', fingerprint.languages);
            defineProperty(navigator, 'hardwareConcurrency', fingerprint.hardwareConcurrency);
            defineProperty(navigator, 'deviceMemory', fingerprint.deviceMemory);
            defineProperty(navigator, 'doNotTrack', fingerprint.doNotTrack);
            defineProperty(navigator, 'cookieEnabled', fingerprint.cookiesEnabled);
            defineProperty(navigator, 'webdriver', fingerprint.webdriver);
            defineProperty(navigator, 'vendor', 'Google Inc.');
            defineProperty(navigator, 'vendorSub', '');
            defineProperty(navigator, 'productSub', '20030107');
            defineProperty(navigator, 'appCodeName', 'Mozilla');
            defineProperty(navigator, 'appName', 'Netscape');
            defineProperty(navigator, 'appVersion', fingerprint.userAgent.replace('Mozilla/', ''));
            defineProperty(navigator, 'maxTouchPoints', Math.floor(Math.random() * 5));
            defineProperty(navigator, 'onLine', true);
            defineProperty(navigator, 'pdfViewerEnabled', true);
            
            // === 2. 高级navigator属性伪装 ===
            if (!navigator.connection) {{
                defineProperty(navigator, 'connection', {{
                    effectiveType: '4g',
                    downlink: Math.random() * 10 + 5,
                    downlinkMax: Infinity,
                    rtt: Math.floor(Math.random() * 100) + 50,
                    saveData: false,
                    type: 'wifi'
                }});
            }}
            
            // 重写getUserMedia
            if (navigator.mediaDevices) {{
                const originalGetUserMedia = navigator.mediaDevices.getUserMedia;
                navigator.mediaDevices.getUserMedia = function(constraints) {{
                    return originalGetUserMedia.call(this, constraints);
                }};
            }}
            
            // === 3. Screen属性伪装 ===
            defineProperty(screen, 'width', fingerprint.screen.width);
            defineProperty(screen, 'height', fingerprint.screen.height);
            defineProperty(screen, 'availWidth', fingerprint.screen.width);
            defineProperty(screen, 'availHeight', fingerprint.screen.height - 40);
            defineProperty(screen, 'colorDepth', fingerprint.screen.colorDepth);
            defineProperty(screen, 'pixelDepth', fingerprint.screen.pixelDepth);
            defineProperty(screen, 'orientation', {{
                angle: 0,
                type: 'landscape-primary'
            }});
            
            // === 4. 增强Canvas指纹伪装 ===
            if (fingerprint.canvas.enabled) {{
                const canvasProto = HTMLCanvasElement.prototype;
                const contextProto = CanvasRenderingContext2D.prototype;
                
                // 劫持toDataURL
                const originalToDataURL = canvasProto.toDataURL;
                canvasProto.toDataURL = function(type, encoderOptions) {{
                    const result = originalToDataURL.apply(this, arguments);
                    if (Math.random() < fingerprint.canvas.noise) {{
                        const bytes = new Uint8Array(result.length);
                        for (let i = 0; i < bytes.length; i++) {{
                            bytes[i] = result.charCodeAt(i);
                        }}
                        // 轻微修改最后几个字节
                        for (let i = 0; i < 3; i++) {{
                            const pos = bytes.length - 1 - i;
                            bytes[pos] = bytes[pos] ^ (Math.floor(Math.random() * 4) + 1);
                        }}
                        return String.fromCharCode.apply(null, bytes);
                    }}
                    return result;
                }};
                
                // 劫持getImageData
                const originalGetImageData = contextProto.getImageData;
                contextProto.getImageData = function() {{
                    const result = originalGetImageData.apply(this, arguments);
                    if (Math.random() < fingerprint.canvas.noise * 0.1) {{
                        const data = result.data;
                        for (let i = 0; i < data.length; i += 100) {{
                            if (Math.random() < 0.001) {{
                                data[i] = Math.min(255, Math.max(0, data[i] + Math.floor(Math.random() * 5) - 2));
                            }}
                        }}
                    }}
                    return result;
                }};
                
                // 劫持fillText和strokeText
                const originalFillText = contextProto.fillText;
                const originalStrokeText = contextProto.strokeText;
                
                contextProto.fillText = function(text, x, y, maxWidth) {{
                    const jitter = fingerprint.canvas.noise * 0.1;
                    const newX = x + (Math.random() - 0.5) * jitter;
                    const newY = y + (Math.random() - 0.5) * jitter;
                    return originalFillText.call(this, text, newX, newY, maxWidth);
                }};
                
                contextProto.strokeText = function(text, x, y, maxWidth) {{
                    const jitter = fingerprint.canvas.noise * 0.1;
                    const newX = x + (Math.random() - 0.5) * jitter;
                    const newY = y + (Math.random() - 0.5) * jitter;
                    return originalStrokeText.call(this, text, newX, newY, maxWidth);
                }};
            }}
            
            // === 5. 增强WebGL指纹伪装 ===
            const glContexts = ['webgl', 'webgl2', 'experimental-webgl', 'experimental-webgl2'];
            glContexts.forEach(contextName => {{
                const originalGetContext = HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext = function(type, attributes) {{
                    const context = originalGetContext.call(this, type, attributes);
                    if (type === contextName && context) {{
                        const originalGetParameter = context.getParameter;
                        context.getParameter = function(parameter) {{
                            switch(parameter) {{
                                case 37445: // UNMASKED_VENDOR_WEBGL
                                    return fingerprint.webgl.vendor;
                                case 37446: // UNMASKED_RENDERER_WEBGL
                                    return fingerprint.webgl.renderer;
                                case 7936: // VERSION
                                    return 'WebGL 1.0 (OpenGL ES 2.0 Chromium)';
                                case 7937: // SHADING_LANGUAGE_VERSION
                                    return 'WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)';
                                case 7938: // VENDOR
                                    return 'WebKit';
                                case 35724: // MAX_VERTEX_ATTRIBS
                                    return 16;
                                case 34921: // MAX_VERTEX_UNIFORM_VECTORS
                                    return 1024;
                                case 34930: // MAX_VARYING_VECTORS
                                    return 30;
                                case 35660: // MAX_VERTEX_TEXTURE_IMAGE_UNITS
                                    return 16;
                                case 34076: // MAX_TEXTURE_SIZE
                                    return 16384;
                                case 34024: // MAX_CUBE_MAP_TEXTURE_SIZE
                                    return 16384;
                                default:
                                    return originalGetParameter.call(this, parameter);
                            }}
                        }};
                        
                        // 伪装WebGL扩展
                        const originalGetExtension = context.getExtension;
                        context.getExtension = function(name) {{
                            const extension = originalGetExtension.call(this, name);
                            if (name === 'WEBGL_debug_renderer_info') {{
                                return {{
                                    UNMASKED_VENDOR_WEBGL: 37445,
                                    UNMASKED_RENDERER_WEBGL: 37446
                                }};
                            }}
                            return extension;
                        }};
                    }}
                    return context;
                }};
            }});
            
            // === 6. Audio指纹伪装 ===
            if (window.AudioContext || window.webkitAudioContext) {{
                const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
                const originalCreateOscillator = AudioContextConstructor.prototype.createOscillator;
                const originalCreateAnalyser = AudioContextConstructor.prototype.createAnalyser;
                
                AudioContextConstructor.prototype.createOscillator = function() {{
                    const oscillator = originalCreateOscillator.call(this);
                    const originalStart = oscillator.start;
                    oscillator.start = function(when) {{
                        const jitteredWhen = when + (Math.random() - 0.5) * 0.0001;
                        return originalStart.call(this, jitteredWhen);
                    }};
                    return oscillator;
                }};
                
                AudioContextConstructor.prototype.createAnalyser = function() {{
                    const analyser = originalCreateAnalyser.call(this);
                    const originalGetFloatFrequencyData = analyser.getFloatFrequencyData;
                    analyser.getFloatFrequencyData = function(array) {{
                        originalGetFloatFrequencyData.call(this, array);
                        // 添加轻微噪声
                        for (let i = 0; i < array.length; i++) {{
                            if (Math.random() < 0.001) {{
                                array[i] += (Math.random() - 0.5) * 0.01;
                            }}
                        }}
                    }};
                    return analyser;
                }};
            }}
            
            // === 7. 高精度时间伪装 ===
            if (window.performance) {{
                const originalNow = performance.now;
                performance.now = function() {{
                    return originalNow.call(this) + Math.random() * 0.1;
                }};
                
                // 伪装性能时间
                defineProperty(performance, 'timeOrigin', Date.now() - performance.now());
            }}
            
            // === 8. 地理位置伪装 ===
            if (navigator.geolocation) {{
                const originalGetCurrentPosition = navigator.geolocation.getCurrentPosition;
                navigator.geolocation.getCurrentPosition = function(success, error, options) {{
                    const fakePosition = {{
                        coords: {{
                            latitude: 39.9042 + (Math.random() - 0.5) * 0.01,
                            longitude: 116.4074 + (Math.random() - 0.5) * 0.01,
                            accuracy: Math.random() * 100 + 10,
                            altitude: null,
                            altitudeAccuracy: null,
                            heading: null,
                            speed: null
                        }},
                        timestamp: Date.now()
                    }};
                    
                    if (success) {{
                        setTimeout(() => success(fakePosition), Math.random() * 100);
                    }}
                }};
            }}
            
            // === 9. 时区和日期伪装 ===
            const originalDate = Date;
            const timezoneOffset = fingerprint.timezoneOffset || -480; // 默认UTC+8
            
            Date.prototype.getTimezoneOffset = function() {{
                return timezoneOffset;
            }};
            
            if (Intl.DateTimeFormat.prototype.resolvedOptions) {{
                const originalResolvedOptions = Intl.DateTimeFormat.prototype.resolvedOptions;
                Intl.DateTimeFormat.prototype.resolvedOptions = function() {{
                    const options = originalResolvedOptions.apply(this, arguments);
                    options.timeZone = fingerprint.timezone;
                    return options;
                }};
            }}
            
            // === 10. 字体检测伪装 ===
            const originalOffsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
            const originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
            
            Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {{
                get: function() {{
                    const width = originalOffsetWidth.get.call(this);
                    return width + (Math.random() - 0.5) * 0.1;
                }},
                configurable: true
            }});
            
            Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {{
                get: function() {{
                    const height = originalOffsetHeight.get.call(this);
                    return height + (Math.random() - 0.5) * 0.1;
                }},
                configurable: true
            }});
            
            // === 11. 隐藏所有自动化痕迹 ===
            // 移除webdriver属性
            delete navigator.__proto__.webdriver;
            delete navigator.webdriver;
            
            // 隐藏Selenium相关属性
            const seleniumProps = ['__selenium_unwrapped', '__webdriver_evaluate', '__webdriver_script_function', '__webdriver_script_func', '__webdriver_script_fn', '__fxdriver_evaluate', '__fxdriver_unwrapped', '__driver_evaluate', '__driver_unwrapped', '__selenium_evaluate', '__selenium_unwrapped'];
            seleniumProps.forEach(prop => {{
                delete window[prop];
                delete document[prop];
            }});
            
            // 隐藏phantom.js
            delete window._phantom;
            delete window.__phantom;
            delete window.callPhantom;
            
            // 隐藏nightmare.js
            delete window.__nightmare;
            delete window.nightmare;
            
            // === 12. 事件伪装 ===
            const originalAddEventListener = EventTarget.prototype.addEventListener;
            EventTarget.prototype.addEventListener = function(type, listener, options) {{
                if (typeof listener === 'function') {{
                    const originalListener = listener;
                    listener = function(event) {{
                        // 为鼠标事件添加轻微抖动
                        if (event.type.includes('mouse') && event.isTrusted !== false) {{
                            Object.defineProperty(event, 'isTrusted', {{ value: true, configurable: false }});
                        }}
                        return originalListener.apply(this, arguments);
                    }};
                }}
                return originalAddEventListener.call(this, type, listener, options);
            }};
            
            // === 13. 防止指纹脚本被检测 ===
            const script = document.currentScript;
            if (script && script.parentNode) {{
                script.parentNode.removeChild(script);
            }}
            
            // 清理痕迹
            setTimeout(() => {{
                const scripts = document.querySelectorAll('script[type="text/javascript"]');
                scripts.forEach(script => {{
                    if (script.textContent.includes('fingerprint') || script.textContent.includes('webdriver')) {{
                        script.remove();
                    }}
                }});
            }}, 100);
            
            console.log('🎭 增强浏览器指纹伪装已激活:', fingerprint.userAgent.substring(0, 50) + '...');
        }})();
        """
        
        return script

# 创建全局实例
fingerprint_manager = FingerprintManager() 