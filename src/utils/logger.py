import datetime

class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'

def get_time():
    return f"{Colors.BLUE}[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]{Colors.RESET}"

def log_system(msg): 
    print(f"{get_time()} {Colors.CYAN}[SYSTEM]{Colors.RESET} ⚙️  {msg}", flush=True)

def log_info(msg):   
    print(f"{get_time()} {Colors.GREEN}[INFO  ]{Colors.RESET} ℹ️  {msg}", flush=True)

def log_ok(msg):     
    print(f"{get_time()} {Colors.GREEN}[OK    ]{Colors.RESET} ✅ {msg}", flush=True)

def log_warn(msg):   
    print(f"{get_time()} {Colors.YELLOW}[WARN  ]{Colors.RESET} ⚠️  {msg}", flush=True)

def log_alert(msg):  
    print(f"{get_time()} {Colors.MAGENTA}[ALERT ]{Colors.RESET} 🚨 {Colors.MAGENTA}{msg}{Colors.RESET}", flush=True)

def log_error(msg):  
    print(f"{get_time()} {Colors.RED}[ERROR ]{Colors.RESET} ❌ {Colors.RED}{msg}{Colors.RESET}", flush=True)
