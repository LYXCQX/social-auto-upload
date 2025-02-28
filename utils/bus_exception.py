# 添加自定义异常类
class UpdateError(Exception):
    """任务未找到异常"""

    def __init__(self, message=None):
        self.message = message or "没有找到任务标签，可能还没接取该任务，请先接取任务"
        super().__init__(self.message)

class BusError(Exception):
    """任务未找到异常"""

    def __init__(self, message=None):
        self.message = message or "业务异常，"
        super().__init__(self.message)