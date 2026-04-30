#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dapaodan.com 单次测试注册脚本
用于学习研究自动化注册流程
"""

import re
import sys
import time
import random
import string
import requests
from loguru import logger

# 添加项目路径
sys.path.insert(0, '.')

from utils.config import Config
from core.ema_service import EmaService


# ============================================================
# 用户信息生成 - 生成自然、不易被识别的用户名/邮箱/密码
# ============================================================

# 常见中文名拼音 + 常见后缀
FIRST_NAMES = [
    'wang', 'li', 'zhang', 'liu', 'chen', 'yang', 'zhao', 'huang',
    'zhou', 'wu', 'xu', 'sun', 'hu', 'zhu', 'gao', 'lin',
    'he', 'guo', 'ma', 'luo', 'liang', 'song', 'zheng', 'xie',
    'han', 'tang', 'feng', 'yu', 'dong', 'xiao', 'cheng', 'cao',
]
SECOND_NAMES = [
    'wei', 'fang', 'lei', 'ming', 'jie', 'hua', 'qiang', 'jun',
    'yong', 'jian', 'ping', 'xin', 'chao', 'hao', 'bo', 'tao',
    'gang', 'bin', 'nan', 'peng', 'fei', 'long', 'kai', 'rui',
    'yan', 'lin', 'xue', 'yi', 'hang', 'zhi', 'chen', 'yu',
]
EMAIL_DOMAINS = ['qq.com', '163.com', '126.com', 'sina.com', 'foxmail.com', 'gmail.com']


def generate_username():
    """生成自然的用户名，如 zhangwei88, liminghao"""
    first = random.choice(FIRST_NAMES)
    second = random.choice(SECOND_NAMES)
    suffix = random.choice([
        str(random.randint(1, 99)),
        str(random.randint(88, 99)),
        str(random.randint(2000, 2006)),
        '',
    ])
    return f"{first}{second}{suffix}"


def generate_email(username):
    """基于用户名生成邮箱"""
    domain = random.choice(EMAIL_DOMAINS)
    # 有时候邮箱前缀和用户名略有不同
    prefix = random.choice([
        username,
        username + str(random.randint(1, 9)),
        username.replace(username[:2], username[:2].upper(), 1) if len(username) > 2 else username,
    ])
    return f"{prefix}@{domain}"


def generate_password():
    """生成看起来自然的密码"""
    patterns = [
        # 拼音+数字+符号
        lambda: random.choice(FIRST_NAMES).capitalize() + str(random.randint(100, 999)) + random.choice(['!', '@', '#', '$']),
        # 常见密码模式
        lambda: random.choice(['Abc', 'Pwd', 'Pass', 'My']) + str(random.randint(1000, 9999)) + random.choice(['!', '@', '#']),
        # 名字+生日风格
        lambda: random.choice(SECOND_NAMES).capitalize() + str(random.randint(1990, 2005)) + random.choice(['a', 'b', 'c']),
    ]
    return random.choice(patterns)()


# ============================================================
# 页面令牌提取
# ============================================================

def extract_tokens(html):
    """从注册页面HTML中提取动态令牌"""
    tokens = {}

    # 提取发送验证码的 nonce
    m = re.search(
        r'"xh_social_wechat_social_add_ons_social_mobile"\s*:\s*"([a-f0-9]+)"',
        html
    )
    if m:
        tokens['sms_nonce'] = m.group(1)

    # 提取发送验证码的 hash
    sms_hash = re.search(
        r'xh_social_wechat_social_add_ons_social_mobile.*?"hash"\s*:\s*"([a-f0-9]+)"',
        html, re.DOTALL
    )
    if sms_hash:
        tokens['sms_hash'] = sms_hash.group(1)

    # 提取发送验证码的 notice_str
    sms_notice = re.search(
        r'xh_social_wechat_social_add_ons_social_mobile.*?"notice_str"\s*:\s*"(\d+)"',
        html, re.DOTALL
    )
    if sms_notice:
        tokens['sms_notice_str'] = sms_notice.group(1)

    # 提取注册提交URL中的参数（在URL查询字符串中）
    # 格式：action=xh_social_add_ons_login&tab=register&xh_social_add_ons_login=XXX&notice_str=XXX&hash=XXX
    reg_url = re.search(
        r'action=xh_social_add_ons_login&tab=register&xh_social_add_ons_login=([a-f0-9]+)&notice_str=(\d+)&hash=([a-f0-9]+)',
        html
    )
    if reg_url:
        tokens['register_nonce'] = reg_url.group(1)
        tokens['register_notice_str'] = reg_url.group(2)
        tokens['register_hash'] = reg_url.group(3)

    return tokens


# ============================================================
# 注册主流程
# ============================================================

class DapaodanRegister:
    """dapaodan.com 注册器"""

    BASE_URL = "https://dapaodan.com"
    REGISTER_URL = f"{BASE_URL}/register/"
    AJAX_URL = f"{BASE_URL}/wp-admin/admin-ajax.php"

    def __init__(self):
        self.config = Config()
        self.ema = EmaService(self.config)
        self.session = requests.Session()
        self.tokens = {}
        self.phone = None

        # 设置自然的浏览器 headers
        ua = random.choice(self.config.USER_AGENTS)
        self.session.headers.update({
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Sec-Ch-Ua': '"Chromium";v="138", "Google Chrome";v="138", "Not=A?Brand";v="99"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Upgrade-Insecure-Requests': '1',
        })

        # 设置代理
        if self.config.USE_PROXY and self.config.PROXY_LIST:
            proxy = random.choice(self.config.PROXY_LIST)
            self.session.proxies = {'http': proxy, 'https': proxy}
            logger.info(f"使用代理: {proxy}")

    def step1_visit_page(self):
        """第1步：访问注册页面，获取 cookies 和动态令牌"""
        logger.info("=== 第1步：访问注册页面 ===")

        resp = self.session.get(self.REGISTER_URL, timeout=30)
        resp.raise_for_status()
        logger.info(f"页面状态码: {resp.status_code}, cookies: {len(self.session.cookies)}")

        self.tokens = extract_tokens(resp.text)
        logger.info(f"提取到的令牌: {list(self.tokens.keys())}")

        required = ['sms_nonce', 'sms_hash', 'register_nonce', 'register_hash']
        missing = [k for k in required if k not in self.tokens]
        if missing:
            logger.error(f"缺少关键令牌: {missing}")
            logger.debug(f"已获取令牌: {self.tokens}")
            return False

        return True

    def step2_get_phone(self):
        """第2步：从e码获取手机号"""
        logger.info("=== 第2步：获取手机号 ===")

        if not self.ema.login():
            logger.error("e码登录失败")
            return False

        # 不做可用性检测，加快速度；使用实卡以提高短信接收率
        self.phone = self.ema.get_phone(card_type='实卡', check_availability=False)
        if not self.phone:
            logger.error("获取手机号失败")
            return False

        logger.info(f"获取到手机号: {self.phone}")
        return True

    def step3_send_sms(self, username, email, password):
        """第3步：发送短信验证码"""
        logger.info("=== 第3步：发送短信验证码 ===")

        # 切换 headers 为 AJAX 模式
        self.session.headers.update({
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': self.REGISTER_URL,
            'Origin': self.BASE_URL,
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        })

        data = {
            'action': 'xh_social_wechat_social_add_ons_social_mobile',
            'tab': 'mobile_login_vcode',
            'xh_social_wechat_social_add_ons_social_mobile': self.tokens['sms_nonce'],
            'notice_str': self.tokens.get('sms_notice_str', ''),
            'hash': self.tokens['sms_hash'],
            'unique': '1',
            'mobile': self.phone,
            'register_user_login': username,
            'register_user_email': email,
            'register_password': password,
        }

        resp = self.session.post(self.AJAX_URL, data=data, timeout=30)
        logger.info(f"发送验证码状态码: {resp.status_code}")
        logger.debug(f"响应内容: {resp.text[:500]}")

        try:
            result = resp.json()
        except Exception:
            logger.error(f"响应非JSON: {resp.text[:500]}")
            return False

        logger.info(f"发送验证码响应: {result}")

        if result.get('errcode') == 0:
            logger.info("短信验证码发送成功")
            return True

        logger.error(f"发送验证码失败: {result.get('errmsg', '未知错误')}")
        return False

    def step4_wait_sms(self):
        """第4步：等待接收短信验证码"""
        logger.info("=== 第4步：等待短信验证码 ===")

        # 轮询e码API获取短信，关键词为短信【】中的签名
        sms_keyword = '大炮弹'
        start_time = time.time()
        timeout = 90
        interval = 3

        while time.time() - start_time < timeout:
            try:
                params = {
                    'code': 'getMsg',
                    'token': self.ema.token,
                    'phone': self.phone,
                    'keyWord': sms_keyword,
                }
                resp = self.ema.session.get(self.ema.api_url, params=params, timeout=15)
                result = resp.text.strip()

                if '[尚未收到]' in result or result.startswith('ERROR:'):
                    elapsed = int(time.time() - start_time)
                    logger.info(f"短信尚未收到，继续等待... ({elapsed}s)")
                    time.sleep(interval)
                    continue

                # 收到短信，e码返回格式: 手机号/费用/短信内容
                logger.info(f"收到短信原始内容: {result}")
                # 提取实际短信内容（取最后一个/之后的部分）
                parts = result.split('/', 2)
                sms_body = parts[2] if len(parts) >= 3 else result
                logger.info(f"短信正文: {sms_body}")
                code = self.ema.extract_sms_code(sms_body)
                if code:
                    logger.info(f"提取到验证码: {code}")
                    return code

                # 没提取到，继续等
                time.sleep(interval)

            except Exception as e:
                logger.warning(f"轮询异常: {e}")
                time.sleep(interval)

        logger.error("短信验证码接收超时")
        return None

    def step5_submit_register(self, username, email, password, sms_code):
        """第5步：提交注册"""
        logger.info("=== 第5步：提交注册 ===")

        params = {
            'action': 'xh_social_add_ons_login',
            'tab': 'register',
            'xh_social_add_ons_login': self.tokens['register_nonce'],
            'notice_str': self.tokens.get('register_notice_str', ''),
            'hash': self.tokens['register_hash'],
        }

        data = {
            'register_user_login': username,
            'register_user_email': email,
            'register_password': password,
            'mobile': self.phone,
            'mobile_vcode': sms_code,
        }

        resp = self.session.post(self.AJAX_URL, params=params, data=data, timeout=30)
        result = resp.json()
        logger.info(f"注册响应: {result}")

        if result.get('errcode') == 0:
            logger.info("注册成功!")
            return True

        logger.error(f"注册失败: {result.get('errmsg', '未知错误')}")
        return False

    def cleanup(self):
        """释放手机号"""
        if self.phone:
            self.ema.release_phone(self.phone)
            logger.info(f"已释放手机号: {self.phone}")

    def run(self):
        """执行完整注册流程"""
        username = generate_username()
        email = generate_email(username)
        password = generate_password()

        logger.info("=" * 60)
        logger.info("dapaodan.com 测试注册")
        logger.info("=" * 60)
        logger.info(f"用户名: {username}")
        logger.info(f"邮箱:   {email}")
        logger.info(f"密码:   {password}")
        logger.info("=" * 60)

        try:
            # 第1步：访问注册页面
            if not self.step1_visit_page():
                return None

            # 随机延迟，模拟人类行为
            time.sleep(random.uniform(1, 3))

            # 第2步：获取手机号
            if not self.step2_get_phone():
                return None

            time.sleep(random.uniform(1, 2))

            # 第3步：发送短信
            if not self.step3_send_sms(username, email, password):
                self.cleanup()
                return None

            # 第4步：等待短信验证码
            sms_code = self.step4_wait_sms()
            if not sms_code:
                self.cleanup()
                return None

            time.sleep(random.uniform(0.5, 1.5))

            # 第5步：提交注册
            if not self.step5_submit_register(username, email, password, sms_code):
                self.cleanup()
                return None

            # 释放手机号
            self.cleanup()

            # 输出结果
            result = {
                'username': username,
                'email': email,
                'password': password,
                'phone': self.phone,
            }

            logger.info("=" * 60)
            logger.info("注册成功! 账号信息：")
            logger.info(f"  用户名: {username}")
            logger.info(f"  邮箱:   {email}")
            logger.info(f"  密码:   {password}")
            logger.info(f"  手机号: {self.phone}")
            logger.info("=" * 60)

            return result

        except Exception as e:
            logger.error(f"注册流程异常: {e}")
            self.cleanup()
            return None


if __name__ == '__main__':
    result = DapaodanRegister().run()
    if not result:
        logger.error("注册失败")
        sys.exit(1)
