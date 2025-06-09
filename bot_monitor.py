import psutil
import platform
from datetime import datetime

class TigerBotMonitor:
    def get_server_stats(self) -> str:
        """Получение статистики сервера"""
        stats = [
            f"🐯 Tiger Bot Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"CPU: {psutil.cpu_percent()}% | RAM: {psutil.virtual_memory().percent}%",
            f"Disk: {psutil.disk_usage('/').percent}% | Uptime: {datetime.now() - datetime.fromtimestamp(psutil.boot_time())}",
            f"OS: {platform.system()} {platform.release()}",
            f"Python: {platform.python_version()}"
        ]
        return "\n".join(stats)

if __name__ == "__main__":
    monitor = TigerBotMonitor()
    print(monitor.get_server_stats())