import discord
from discord.ext import commands
import asyncio
import os  # <- Make sure this is imported
import json
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('DiscordBot')

# Bot Token from environment variable
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    raise ValueError("❌ No DISCORD_TOKEN found! Set it in Railway environment variables.")

# Rest of your bot.py code stays the same...
```

### **requirements.txt**
```
discord.py>=2.3.0
yt-dlp>=2023.3.4
PyNaCl>=1.5.0
aiohttp>=3.9.0
```

### **Procfile** (no file extension!)
```
worker: python bot.py
```

### **runtime.txt**
```
python-3.11.0
```

### **.gitignore**
```
.env
__pycache__/
*.pyc
*.log
prefixes.json
*.pem
.DS_Store