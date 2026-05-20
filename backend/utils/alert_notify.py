"""股票条件预警邮件通知，复用 job_notify 的 SMTP 配置"""
import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from utils.job_notify import _smtp_config

logger = logging.getLogger(__name__)

_ALERT_TYPE_LABELS = {
    'change_pct': '涨跌幅',
    'limit_up': '涨停',
    'limit_down': '跌停',
    'seal_order': '涨停封单',
}


def build_alert_email(rule: dict, quote: dict, limit_up_data: dict) -> tuple:
    """构建预警邮件主题和正文，返回 (subject, body)"""
    code = rule['code']
    name = rule.get('stock_name') or code
    alert_type = rule['alert_type']
    threshold = rule.get('threshold')
    direction = rule.get('direction')
    pct = quote.get('change_percent', 0) or 0
    price = quote.get('price', 0) or 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    label = _ALERT_TYPE_LABELS.get(alert_type, alert_type)

    if alert_type == 'change_pct':
        direction_label = f"涨超{threshold}%" if direction == 'above' else f"跌超{threshold}%"
        subject = f"[预警] {name}({code}) {label}触发 · {direction_label}"
        body = (f"【NiuNIuNiu 预警】\n"
                f"{name}({code}) 当前涨跌幅 {pct:+.2f}%，已触发{direction_label}预警\n"
                f"当前价：{price}  触发时间：{now}")
    elif alert_type == 'limit_up':
        subject = f"[预警] {name}({code}) 已涨停"
        body = (f"【NiuNIuNiu 预警】\n"
                f"{name}({code}) 已涨停\n"
                f"当前价：{price}  涨幅：{pct:+.2f}%  触发时间：{now}")
    elif alert_type == 'limit_down':
        subject = f"[预警] {name}({code}) 已跌停"
        body = (f"【NiuNIuNiu 预警】\n"
                f"{name}({code}) 已跌停\n"
                f"当前价：{price}  涨幅：{pct:+.2f}%  触发时间：{now}")
    elif alert_type == 'seal_order':
        seal_lots = int(limit_up_data.get('seal_volume_lots', 0) or 0)
        direction_label = '超过' if direction == 'above' else '低于'
        subject = f"[预警] {name}({code}) 涨停封单{direction_label}阈值"
        body = (f"【NiuNIuNiu 预警】\n"
                f"{name}({code}) 涨停封单 {seal_lots} 手，{direction_label}设定阈值 {threshold} 手\n"
                f"当前价：{price}  触发时间：{now}")
    else:
        subject = f"[预警] {name}({code}) {label}触发"
        body = f"【NiuNIuNiu 预警】\n{name}({code}) 预警条件已触发  触发时间：{now}"

    return subject, body


def send_stock_alert(rule: dict, quote: dict, limit_up_data: dict, to_email: str) -> bool:
    """发送股票预警邮件，返回是否成功"""
    cfg = _smtp_config()
    if not cfg:
        logger.warning("未配置 SMTP，跳过预警邮件: %s %s", rule.get('code'), rule.get('alert_type'))
        return False

    subject, body = build_alert_email(rule, quote, limit_up_data)
    msg = MIMEMultipart()
    msg['From'] = cfg['sender']
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        if cfg['use_ssl']:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg['host'], cfg['port'], context=context) as smtp:
                smtp.login(cfg['user'], cfg['password'])
                smtp.sendmail(cfg['sender'], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg['host'], cfg['port']) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(cfg['user'], cfg['password'])
                smtp.sendmail(cfg['sender'], [to_email], msg.as_string())
        logger.info("预警邮件已发送 -> %s [%s %s]", to_email, rule.get('code'), rule.get('alert_type'))
        return True
    except Exception as e:
        logger.error("预警邮件发送失败: %s", e)
        return False
