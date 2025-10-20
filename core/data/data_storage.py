import pandas as pd
import os
from typing import Dict, Any, Optional, List
from pathlib import Path


class DataStorage:
    """数据存储类，用于保存和加载数据"""
    
    def __init__(self, storage_dir: str):
        """
        初始化数据存储器
        
        Args:
            storage_dir: 数据存储目录
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
    
    def save_data(self, data: pd.DataFrame, symbol: str, timeframe: str, format: str = 'csv') -> None:
        """
        保存数据到文件
        
        Args:
            data: 要保存的数据DataFrame
            symbol: 交易对符号
            timeframe: 时间周期
            format: 文件格式 ('csv', 'json', 'parquet')
        """
        # 清理符号中的特殊字符，避免文件路径问题
        # 将整个符号中的'/'替换为'_'，而不是只替换第一个
        safe_symbol = symbol.replace('/', '_')
        
        # 创建文件名
        filename = f"{safe_symbol}_{timeframe}.{format}"
        file_path = self.storage_dir / filename
        
        # 确保目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 根据格式保存数据
        if format.lower() == 'csv':
            data.to_csv(file_path, index=False)
        elif format.lower() == 'json':
            data.to_json(file_path, orient='records', date_format='iso')
        elif format.lower() == 'parquet':
            data.to_parquet(file_path, index=False)
        else:
            raise ValueError(f"不支持的文件格式: {format}")
    
    def load_data(self, symbol: str, timeframe: str, format: str = 'csv') -> pd.DataFrame:
        """
        从文件加载数据
        
        Args:
            symbol: 交易对符号
            timeframe: 时间周期
            format: 文件格式 ('csv', 'json', 'parquet')
            
        Returns:
            加载的数据DataFrame
        """
        # 清理符号中的特殊字符
        safe_symbol = symbol.replace('/', '_')
        
        # 创建文件名
        filename = f"{safe_symbol}_{timeframe}.{format}"
        file_path = self.storage_dir / filename
        
        # 检查文件是否存在
        if not file_path.exists():
            raise FileNotFoundError(f"数据文件不存在: {file_path}")
        
        # 根据格式加载数据
        if format.lower() == 'csv':
            data = pd.read_csv(file_path)
            # 确保时间戳列是datetime类型
            if 'timestamp' in data.columns:
                data['timestamp'] = pd.to_datetime(data['timestamp'])
        elif format.lower() == 'json':
            data = pd.read_json(file_path, orient='records')
            # 确保时间戳列是datetime类型
            if 'timestamp' in data.columns:
                data['timestamp'] = pd.to_datetime(data['timestamp'])
        elif format.lower() == 'parquet':
            data = pd.read_parquet(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {format}")
        
        return data
    
    def list_symbols(self, timeframe: Optional[str] = None) -> List[str]:
        """
        列出可用的交易对
        
        Args:
            timeframe: 可选的时间周期过滤
            
        Returns:
            交易对列表
        """
        symbols = set()
        
        # 遍历存储目录中的所有文件
        for file_path in self.storage_dir.glob("*"):
            if file_path.is_file():
                # 获取文件名（不包含扩展名）
                filename = file_path.stem
                
                # 从文件名中分离出时间周期部分
                # 文件名格式为: safe_symbol_timeframe，其中safe_symbol是符号的文件安全版本
                # 我们需要从右边开始分割，因为符号本身可能包含下划线
                parts = filename.rsplit('_', 1)
                
                if len(parts) == 2:
                    safe_symbol = parts[0]
                    file_timeframe = parts[1]
                    
                    # 将处理后的符号名恢复为原始符号名
                    symbol = safe_symbol.replace('_', '/')
                    
                    # 如果指定了时间周期，只返回匹配的
                    if timeframe is None or file_timeframe == timeframe:
                        symbols.add(symbol)
        
        return sorted(list(symbols))
    
    def list_timeframes(self, symbol: Optional[str] = None) -> List[str]:
        """
        列出可用的时间周期
        
        Args:
            symbol: 可选的交易对过滤
            
        Returns:
            时间周期列表
        """
        timeframes = set()
        
        # 遍历存储目录中的所有文件
        for file_path in self.storage_dir.glob("*"):
            if file_path.is_file():
                # 获取文件名（不包含扩展名）
                filename = file_path.stem
                
                # 从文件名中分离出时间周期部分
                # 文件名格式为: safe_symbol_timeframe，其中safe_symbol是符号的文件安全版本
                # 我们需要从右边开始分割，因为符号本身可能包含下划线
                parts = filename.rsplit('_', 1)
                
                if len(parts) == 2:
                    file_symbol = parts[0]
                    timeframe = parts[1]
                    
                    # 如果指定了交易对，只返回匹配的
                    if symbol is None:
                        # 如果没有指定符号，添加所有时间周期
                        timeframes.add(timeframe)
                    else:
                        # 比较时需要将原始符号转换为处理后的符号
                        safe_symbol = symbol.replace('/', '_')
                        if file_symbol == safe_symbol:
                            timeframes.add(timeframe)
        
        return sorted(list(timeframes))
    
    def delete_data(self, symbol: str, timeframe: str, format: str = 'csv') -> None:
        """
        删除数据文件
        
        Args:
            symbol: 交易对符号
            timeframe: 时间周期
            format: 文件格式 ('csv', 'json', 'parquet')
        """
        # 清理符号中的特殊字符
        safe_symbol = symbol.replace('/', '_')
        
        # 创建文件名
        filename = f"{safe_symbol}_{timeframe}.{format}"
        file_path = self.storage_dir / filename
        
        # 检查文件是否存在
        if file_path.exists():
            file_path.unlink()
        else:
            raise FileNotFoundError(f"数据文件不存在: {file_path}")
    
    def data_exists(self, symbol: str, timeframe: str, format: str = 'csv') -> bool:
        """
        检查数据文件是否存在
        
        Args:
            symbol: 交易对符号
            timeframe: 时间周期
            format: 文件格式 ('csv', 'json', 'parquet')
            
        Returns:
            文件是否存在
        """
        # 清理符号中的特殊字符
        safe_symbol = symbol.replace('/', '_')
        
        # 创建文件名
        filename = f"{safe_symbol}_{timeframe}.{format}"
        file_path = self.storage_dir / filename
        
        return file_path.exists()
    
    def get_data_info(self, symbol: str, timeframe: str, format: str = 'csv') -> Dict[str, Any]:
        """
        获取数据文件信息
        
        Args:
            symbol: 交易对符号
            timeframe: 时间周期
            format: 文件格式 ('csv', 'json', 'parquet')
            
        Returns:
            包含数据信息的字典
        """
        # 清理符号中的特殊字符
        safe_symbol = symbol.replace('/', '_')
        
        # 创建文件名
        filename = f"{safe_symbol}_{timeframe}.{format}"
        file_path = self.storage_dir / filename
        
        # 检查文件是否存在
        if not file_path.exists():
            raise FileNotFoundError(f"数据文件不存在: {file_path}")
        
        # 获取文件基本信息
        info = {
            'symbol': symbol,
            'timeframe': timeframe,
            'format': format,
            'file_path': str(file_path),
            'file_size': file_path.stat().st_size,
            'last_modified': pd.to_datetime(file_path.stat().st_mtime, unit='s')
        }
        
        # 尝试读取数据获取更多信息
        try:
            data = self.load_data(symbol, timeframe, format)
            info.update({
                'rows': len(data),
                'columns': list(data.columns),
                'start_date': data['timestamp'].min() if 'timestamp' in data.columns else None,
                'end_date': data['timestamp'].max() if 'timestamp' in data.columns else None
            })
        except Exception as e:
            info['load_error'] = str(e)
        
        return info