"""
日志配置模块
提供统一的日志配置和全局异常处理
"""
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import sys
import traceback
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


class LoggerConfig:
    """日志配置管理类"""
    
    def __init__(
        self,
        logs_dir: Optional[Path] = None,
        log_level: int = logging.INFO,
        keep_days: int = 7,
        enable_debug: bool = False,
        console_level: Optional[int] = None
    ):
        """
        初始化日志配置
        
        Args:
            logs_dir: 日志目录路径，默认为项目根目录下的 logs 文件夹
            log_level: 日志级别，默认为 INFO
            keep_days: 日志保留天数，默认为 7 天
            enable_debug: 是否启用 DEBUG 日志文件，默认为 False
            console_level: 控制台日志级别，默认与 log_level 相同
        """
        if logs_dir is None:
            project_root = Path(__file__).resolve().parent.parent
            logs_dir = project_root / "logs"
        
        self.logs_dir = Path(logs_dir)
        self.log_level = log_level
        self.keep_days = keep_days
        self.enable_debug = enable_debug
        self.console_level = console_level if console_level is not None else log_level
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def _load_config() -> Dict[str, Any]:
        """从 config.json 加载配置"""
        try:
            project_root = Path(__file__).resolve().parent.parent
            config_file = project_root / "config.json"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    @staticmethod
    def _parse_log_level(level_str: str) -> int:
        """解析日志级别字符串"""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        return level_map.get(str(level_str).upper(), logging.INFO)
    
    @classmethod
    def from_config(cls, config_path: Optional[Path] = None) -> "LoggerConfig":
        """从配置文件创建 LoggerConfig 实例"""
        config = cls._load_config()
        logging_config = config.get("logging", {})
        
        log_level_str = logging_config.get("level", "INFO")
        console_level_str = logging_config.get("console_level", log_level_str)
        
        return cls(
            logs_dir=config_path,
            log_level=cls._parse_log_level(log_level_str),
            keep_days=logging_config.get("keep_days", 7),
            enable_debug=logging_config.get("enable_debug", False),
            console_level=cls._parse_log_level(console_level_str)
        )
        
    def setup(self) -> Path:
        """
        设置日志配置
        
        Returns:
            日志目录路径
        """
        # 创建日志目录
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # 获取根日志记录器
        root = logging.getLogger()
        root.setLevel(self.log_level)
        
        # 清除现有的处理器
        for handler in list(root.handlers):
            root.removeHandler(handler)
        
        # 创建格式化器
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        
        # 1. 控制台处理器 - 输出指定级别的日志
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(self.console_level)
        root.addHandler(stream_handler)
        
        # 2. DEBUG 级别日志文件处理器（可选）
        if self.enable_debug:
            debug_handler = TimedRotatingFileHandler(
                filename=self.logs_dir / "debug.log",
                when="midnight",
                interval=1,
                backupCount=self.keep_days,
                encoding="utf-8",
                utc=False
            )
            debug_handler.suffix = "%Y%m%d"
            debug_handler.setFormatter(formatter)
            debug_handler.setLevel(logging.DEBUG)
            root.addHandler(debug_handler)
        
        # 3. INFO 级别日志文件处理器
        info_handler = TimedRotatingFileHandler(
            filename=self.logs_dir / "info.log",
            when="midnight",
            interval=1,
            backupCount=self.keep_days,
            encoding="utf-8",
            utc=False
        )
        info_handler.suffix = "%Y%m%d"
        info_handler.setFormatter(formatter)
        info_handler.setLevel(logging.INFO)
        # 只记录 INFO 和 WARNING 级别的日志
        info_handler.addFilter(lambda record: record.levelno < logging.ERROR)
        root.addHandler(info_handler)
        
        # 4. ERROR 级别日志文件处理器
        error_handler = TimedRotatingFileHandler(
            filename=self.logs_dir / "error.log",
            when="midnight",
            interval=1,
            backupCount=self.keep_days,
            encoding="utf-8",
            utc=False
        )
        error_handler.suffix = "%Y%m%d"
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        root.addHandler(error_handler)
        
        # 清理旧日志文件
        self._cleanup_old_logs()
        
        # 注册全局异常处理器
        sys.excepthook = self._global_exception_handler
        
        self.logger.info("日志系统初始化完成")
        self.logger.info("日志目录: %s", self.logs_dir)
        self.logger.info("日志级别: %s", logging.getLevelName(self.log_level))
        self.logger.info("控制台级别: %s", logging.getLevelName(self.console_level))
        if self.enable_debug:
            self.logger.info("DEBUG 日志: debug.log (保留 %d 天)", self.keep_days)
        self.logger.info("INFO 日志: info.log (保留 %d 天)", self.keep_days)
        self.logger.info("ERROR 日志: error.log (保留 %d 天)", self.keep_days)
        
        return self.logs_dir
    
    def _cleanup_old_logs(self) -> None:
        """清理超过指定天数的日志文件"""
        try:
            now = datetime.now()
            cutoff_time = now - timedelta(days=self.keep_days)
            
            deleted_count = 0
            # 匹配各种日志文件模式
            patterns = ["debug.log.*", "info.log.*", "error.log.*", "knowledge-base-*.log*"]
            
            for pattern in patterns:
                for log_file in self.logs_dir.glob(pattern):
                    try:
                        # 获取文件修改时间
                        file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                        if file_mtime < cutoff_time:
                            log_file.unlink()
                            deleted_count += 1
                            self.logger.info(f"已删除过期日志文件: {log_file.name}")
                    except Exception as e:
                        self.logger.warning(f"删除日志文件 {log_file.name} 失败: {e}")
            
            if deleted_count > 0:
                self.logger.info(f"共清理 {deleted_count} 个过期日志文件")
        except Exception as e:
            self.logger.error(f"清理旧日志文件时出错: {e}")
    
    def _global_exception_handler(self, exc_type, exc_value, exc_traceback):
        """全局异常处理器，记录所有未捕获的异常"""
        if issubclass(exc_type, KeyboardInterrupt):
            # 不记录 KeyboardInterrupt
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        logger = logging.getLogger(__name__)
        
        # 记录异常的基本信息
        logger.error("=" * 80)
        logger.error("🔥 捕获到未处理的全局异常 🔥")
        logger.error("=" * 80)
        
        # 异常类型和消息
        logger.error("异常类型: %s", exc_type.__name__)
        logger.error("异常消息: %s", str(exc_value))
        
        # 异常发生的位置
        if exc_traceback:
            tb_frame = exc_traceback.tb_frame
            tb_lineno = exc_traceback.tb_lineno
            logger.error("异常发生位置:")
            logger.error("  文件: %s", tb_frame.f_code.co_filename)
            logger.error("  函数: %s", tb_frame.f_code.co_name)
            logger.error("  行号: %d", tb_lineno)
        
        # 完整的堆栈跟踪
        logger.error("-" * 80)
        logger.error("完整堆栈跟踪:")
        logger.error("-" * 80)
        stack_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        for line in stack_lines:
            for sub_line in line.rstrip().split('\n'):
                logger.error(sub_line)
        
        # 详细的帧信息和局部变量
        logger.error("-" * 80)
        logger.error("调用链详细信息:")
        logger.error("-" * 80)
        tb = exc_traceback
        frame_index = 0
        while tb is not None:
            frame = tb.tb_frame
            lineno = tb.tb_lineno
            code = frame.f_code
            filename = code.co_filename
            func_name = code.co_name
            
            logger.error("")
            logger.error("帧 #%d:", frame_index)
            logger.error("  位置: %s:%d", filename, lineno)
            logger.error("  函数: %s", func_name)
            
            # 记录局部变量（限制输出长度避免日志过大）
            local_vars = frame.f_locals
            if local_vars:
                logger.error("  局部变量:")
                for var_name, var_value in list(local_vars.items())[:10]:  # 只显示前10个变量
                    try:
                        var_str = repr(var_value)
                        if len(var_str) > 200:
                            var_str = var_str[:200] + "... (截断)"
                        logger.error("    %s = %s", var_name, var_str)
                    except Exception:
                        logger.error("    %s = <无法表示>", var_name)
                
                if len(local_vars) > 10:
                    logger.error("    ... (还有 %d 个变量未显示)", len(local_vars) - 10)
            
            tb = tb.tb_next
            frame_index += 1
        
        logger.error("=" * 80)
        logger.error("异常信息记录完毕")
        logger.error("=" * 80)
        
        # 使用 exc_info 参数再次记录，这样可以被其他日志处理器捕获
        logger.error(
            "未捕获的异常",
            exc_info=(exc_type, exc_value, exc_traceback)
        )


def setup_logging(
    logs_dir: Optional[Path] = None,
    log_level: Optional[int] = None,
    keep_days: Optional[int] = None,
    enable_debug: Optional[bool] = None,
    from_config: bool = True
) -> Path:
    """
    设置日志配置的便捷函数
    
    Args:
        logs_dir: 日志目录路径
        log_level: 日志级别
        keep_days: 日志保留天数
        enable_debug: 是否启用 DEBUG 日志
        from_config: 是否从 config.json 读取配置（默认为 True）
        
    Returns:
        日志目录路径
    """
    if from_config:
        # 从配置文件读取
        config = LoggerConfig.from_config(config_path=logs_dir)
        # 允许参数覆盖配置文件
        if log_level is not None:
            config.log_level = log_level
        if keep_days is not None:
            config.keep_days = keep_days
        if enable_debug is not None:
            config.enable_debug = enable_debug
    else:
        # 使用传入参数
        config = LoggerConfig(
            logs_dir=logs_dir,
            log_level=log_level or logging.INFO,
            keep_days=keep_days or 7,
            enable_debug=enable_debug or False
        )
    return config.setup()
