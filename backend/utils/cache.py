"""
缓存工具模块
"""
import time
from functools import wraps

# 数据缓存
data_cache = {}

def cache_with_timeout(timeout=60):
    """带超时的缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}_{str(args)}_{str(kwargs)}"
            current_time = time.time()
            
            # 检查缓存
            if cache_key in data_cache:
                cached_time, cached_data = data_cache[cache_key]
                if current_time - cached_time < timeout:
                    return cached_data
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            data_cache[cache_key] = (current_time, result)
            return result
        return wrapper
    return decorator

def clear_cache():
    """清理缓存"""
    global data_cache
    data_cache = {}
    return True 