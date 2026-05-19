# Routes package initialization
from .stock_basic import stock_basic_bp
from .stock_timeshare import stock_timeshare_bp
from .stock_tick import stock_tick_bp
from .stock_other import stock_other_bp
from .l2_dashboard import l2_dashboard_bp
from .emotion_cycle import emotion_cycle_bp
from .limit_up_echelon import limit_up_echelon_bp
from .theme_manage import theme_manage_bp
from .auction_grab import auction_grab_bp
from .dragon_tiger import dragon_tiger_bp
from .auth import auth_bp
from .user import user_bp
from .orders import orders_bp
from .ai_diagnosis import ai_diagnosis_bp
from .ai_account import ai_account_bp

__all__ = [
    'stock_basic_bp',
    'stock_timeshare_bp',
    'stock_tick_bp',
    'stock_other_bp',
    'l2_dashboard_bp',
    'emotion_cycle_bp',
    'limit_up_echelon_bp',
    'theme_manage_bp',
    'auction_grab_bp',
    'dragon_tiger_bp',
    'auth_bp',
    'user_bp',
    'orders_bp',
    'ai_diagnosis_bp',
    'ai_account_bp',
]
