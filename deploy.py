import paramiko
from scp import SCPClient
import time

def deploy():
    host = '149.154.65.4'
    username = 'root'
    password = 'Zx984hg0000'
    bot_dir = '~/tiger_bot'

    files_to_copy = [
        'main.py',
        'config.json',
        'requirements.txt',
        'bot_monitor.py'
    ]

    setup_commands = [
        'apt-get update -y',
        'apt-get upgrade -y',
        'apt-get install -y python3 python3-venv python3-pip screen',
        f'mkdir -p {bot_dir}',
        f'cd {bot_dir} && python3 -m venv venv',
        f'cd {bot_dir} && . venv/bin/activate && pip install --upgrade pip',
        f'cd {bot_dir} && . venv/bin/activate && pip install -r requirements.txt scikit-learn',
        'pkill -f "python main.py" || true',
        f'cd {bot_dir} && screen -dmS tiger_bot bash -c "source venv/bin/activate && python main.py"',
        f'(crontab -l 2>/dev/null; echo '@reboot cd {bot_dir} && screen -dmS tiger_bot bash -c "source venv/bin/activate && python main.py"') | crontab -'
    ]

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"🔌 Подключаюсь к серверу {host}...")
        ssh.connect(host, username=username, password=password, timeout=30)
        print("✅ Подключение успешно!")

        print("📤 Копирую файлы на сервер...")
        with SCPClient(ssh.get_transport()) as scp:
            for file in files_to_copy:
                scp.put(file, f'{bot_dir}/{file}')
                print(f"   → {file} скопирован")

        print("⚙️ Настраиваю сервер...")
        for cmd in setup_commands:
            print(f"   Выполняю: {cmd[:60]}...")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                print(f"⚠️ Ошибка в команде: {cmd}")
                print(stderr.read().decode())
            else:
                print("   ✓ Успешно")

        print("
🎉 Бот успешно развёрнут и запущен!")
        print(f"Для проверки выполните: ssh root@{host}")
        print("Команды для управления:")
        print("  screen -r tiger_bot  # Просмотр работы бота")
        print("  tail -f ~/tiger_bot/bot.log  # Просмотр логов")

    except Exception as e:
        print(f"
❌ Ошибка развёртывания: {str(e)}")
    finally:
        ssh.close()

if __name__ == "__main__":
    print("🚀 Начинаю развёртывание торгового бота...")
    deploy()