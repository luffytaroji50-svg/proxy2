# Combined Proxy Checker Bot - Render Webhook Deployment (Fixed)
import aiohttp
import asyncio
import time
import json
import random
import threading
from urllib.parse import urlparse
import io
import os
from datetime import datetime
import logging
import traceback
import requests
from flask import Flask, request, jsonify

# Telegram imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Bot configuration - Use environment variables for security
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 10000))

# Validate required environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL environment variable is required")
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS environment variable is required")

# Configure logging for Render
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Flask app for health checks and webhooks
app = Flask(__name__)

# Global variables
bot_application = None
proxy_bot = None

@app.route("/")
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "proxy-checker-bot",
        "bot_ready": bot_application is not None
    })

@app.route("/webhook", methods=["POST"])
def webhook():
    """Webhook endpoint for Telegram - Fixed for synchronous handling"""
    try:
        if not bot_application:
            logger.error("Bot application not ready")
            return "Bot not ready", 503
            
        json_data = request.get_json(force=True)
        if not json_data:
            return "No data", 400
            
        update = Update.de_json(json_data, bot_application.bot)
        if not update:
            return "Invalid update", 400
            
        # Process update in background thread to avoid blocking
        def process_update():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(bot_application.process_update(update))
            except Exception as e:
                logger.error(f"Update processing error: {e}")
            finally:
                try:
                    loop.close()
                except:
                    pass
        
        thread = threading.Thread(target=process_update)
        thread.daemon = True
        thread.start()
        
        return "OK"
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 400

# Test bot connection first
def test_bot_connection():
    """Test if bot token works"""
    try:
        print("Testing bot connection...")
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                bot_info = data.get('result', {})
                print(f"Bot connection successful!")
                print(f"Bot name: {bot_info.get('first_name', 'Unknown')}")
                print(f"Bot username: @{bot_info.get('username', 'Unknown')}")
                return True
            else:
                print(f"Bot API error: {data}")
                return False
        else:
            print(f"HTTP error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Connection test failed: {e}")
        return False


class EnhancedResidentialChecker:
    def __init__(self, bot, session):
        self.bot = bot
        self.session = session
        self.premium_proxies = []
        self.checked_count = 0
        self.total_proxies = 0
        self.lock = threading.Lock()
        self.start_time = time.time()
        
        # Settings optimized for Render stability
        self.timeout = 6
        self.max_concurrent = 12
        self.test_url = "http://httpbin.org/ip"
        self.chunk_size = 20
        
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        ]

    def parse_proxy(self, proxy_line):
        """Parse all different proxy formats"""
        proxy_line = proxy_line.strip()
        if not proxy_line or proxy_line.startswith('#'):
            return None
        
        if proxy_line.startswith('(Http)'):
            proxy_line = proxy_line[6:].strip()
        
        try:
            if proxy_line.startswith(('http://', 'https://')):
                return proxy_line
            
            if proxy_line.startswith('socks5://'):
                socks_part = proxy_line[9:]
                return f"http://{socks_part}"
            
            if '@' in proxy_line and proxy_line.count(':') >= 3:
                auth_part, host_port = proxy_line.split('@', 1)
                username, password = auth_part.split(':', 1)
                return f"http://{username}:{password}@{host_port}"
            
            parts = proxy_line.split(':')
            if len(parts) >= 4:
                host, port, username = parts[0], parts[1], parts[2]
                password = ':'.join(parts[3:])
                return f"http://{username}:{password}@{host}:{port}"
            
            elif len(parts) == 2:
                host, port = parts[0], parts[1]
                return f"http://{host}:{port}"
        
        except Exception:
            pass
        
        return None

    def clean_proxy_output(self, proxy):
        """Clean proxy for output"""
        if proxy.startswith('http://'):
            return proxy[7:]
        elif proxy.startswith('https://'):
            return proxy[8:]
        return proxy

    def get_random_headers(self):
        """Generate realistic browser headers"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'DNT': '1',
            'Connection': 'keep-alive',
        }

    async def analyze_proxy_quality(self, session, proxy, ip_address):
        """Analyze proxy quality with reliable scoring"""
        quality_score = 0
        analysis_data = {}
        
        ip_parts = ip_address.split('.')
        if len(ip_parts) != 4:
            return 0, {}
        
        try:
            url = f'http://ip-api.com/json/{ip_address}?fields=status,country,regionName,city,isp,org,as,proxy,hosting,mobile'
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('status') == 'success':
                        analysis_data = data
                        
                        if not data.get('hosting', True):
                            quality_score += 30
                        
                        if not data.get('proxy', True):
                            quality_score += 30
                        
                        if data.get('mobile', False):
                            quality_score += 25
                        
                        isp = data.get('isp', '').lower()
                        residential_keywords = [
                            'comcast', 'verizon', 'att', 'charter', 'cox', 'spectrum', 'xfinity',
                            'telecom', 'broadband', 'cable', 'fiber', 'dsl', 'residential'
                        ]
                        
                        datacenter_keywords = [
                            'amazon', 'google', 'microsoft', 'digitalocean', 'vultr', 'linode',
                            'ovh', 'hetzner', 'cloudflare', 'hosting', 'server', 'datacenter',
                            'cloud', 'vps', 'dedicated'
                        ]
                        
                        if any(keyword in isp for keyword in residential_keywords):
                            quality_score += 20
                        elif any(keyword in isp for keyword in datacenter_keywords):
                            quality_score -= 25
            
            await asyncio.sleep(2.5)  # Rate limiting
            
        except Exception as e:
            logger.debug(f"IP analysis failed for {ip_address}: {e}")
        
        return quality_score, analysis_data

    async def test_proxy_comprehensive(self, session, proxy, semaphore):
        """Test proxy with quality analysis"""
        async with semaphore:
            try:
                start_time = time.time()
                headers = self.get_random_headers()
                
                timeout_config = aiohttp.ClientTimeout(total=self.timeout, connect=3)
                
                async with session.get(
                    self.test_url,
                    proxy=proxy,
                    timeout=timeout_config,
                    headers=headers,
                    ssl=False
                ) as response:
                    
                    if response.status != 200:
                        return proxy, False, 0, None, "Failed connectivity"
                    
                    response_time = round((time.time() - start_time) * 1000, 2)
                    
                    try:
                        data = await response.json()
                        ip_address = data.get('origin', '').split(',')[0].strip()
                    except:
                        try:
                            ip_address = (await response.text()).strip()
                        except:
                            ip_address = ""
                    
                    if not ip_address:
                        return proxy, False, 0, None, "No IP extracted"
                    
                    quality_score, analysis_data = await self.analyze_proxy_quality(session, proxy, ip_address)
                    
                    if response_time < 1000:
                        quality_score += 10
                    elif response_time < 2000:
                        quality_score += 5
                    
                    is_premium = quality_score >= 35
                    
                    result_data = {
                        'ip': ip_address,
                        'response_time': response_time,
                        'quality_score': quality_score,
                        'country': analysis_data.get('country', 'Unknown'),
                        'isp': analysis_data.get('isp', 'Unknown'),
                        'is_hosting': analysis_data.get('hosting', True),
                        'is_proxy': analysis_data.get('proxy', True),
                        'is_mobile': analysis_data.get('mobile', False),
                        'is_premium': is_premium
                    }
                    
                    status = "PREMIUM RESIDENTIAL" if is_premium else f"NOT PREMIUM (Score: {quality_score})"
                    
                    return proxy, is_premium, response_time, result_data, status
                    
            except asyncio.TimeoutError:
                return proxy, False, 0, None, "Timeout"
            except Exception as e:
                return proxy, False, 0, None, f"Error: {str(e)[:30]}"

    async def test_proxies_chunk(self, proxies_chunk):
        """Test chunk of proxies"""
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent * 2,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        timeout_config = aiohttp.ClientTimeout(total=self.timeout * 2)
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout_config,
            skip_auto_headers=['User-Agent']
        ) as session:
            
            tasks = [self.test_proxy_comprehensive(session, proxy, semaphore) for proxy in proxies_chunk]
            
            for coro in asyncio.as_completed(tasks):
                if self.session.get('is_cancelled'):
                    break
                    
                try:
                    result = await coro
                    
                    with self.lock:
                        self.checked_count += 1
                        proxy, is_premium, response_time, details, status = result
                        
                        if is_premium and details:
                            clean_proxy = self.clean_proxy_output(proxy)
                            proxy_data = {
                                'proxy': clean_proxy,
                                'response_time': response_time,
                                'details': details
                            }
                            self.premium_proxies.append(proxy_data)
                            self.session['premium_proxies'].append(proxy_data)
                            
                            print(f"Premium: {clean_proxy} | {response_time}ms | Score: {details['quality_score']}")
                        
                        self.session['checked_count'] = self.checked_count
                        
                        if self.checked_count % 5 == 0:
                            try:
                                await self.send_progress_update()
                            except Exception as e:
                                logger.error(f"Progress update error: {e}")
                                
                except Exception as task_error:
                    logger.error(f"Task error: {task_error}")
                    with self.lock:
                        self.checked_count += 1
                    continue

    async def send_progress_update(self):
        """Send progress update"""
        if self.session.get('is_cancelled'):
            return
        
        try:
            user_id = self.session['user_id']
            message_id = self.session.get('status_message_id')
            
            if not message_id:
                return
            
            elapsed = time.time() - self.start_time
            progress = (self.checked_count / self.total_proxies) * 100 if self.total_proxies > 0 else 0
            rate = self.checked_count / elapsed if elapsed > 0 else 0
            eta = (self.total_proxies - self.checked_count) / rate if rate > 0 else 0
            
            status_text = f"""Checking Residential Proxies...

Progress: {self.checked_count:,}/{self.total_proxies:,} ({progress:.1f}%)
Elapsed: {elapsed:.0f}s | Rate: {rate:.1f}/s
ETA: {eta:.0f}s remaining
Premium Found: {len(self.premium_proxies)}

Status: Analyzing proxy quality..."""
            
            keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_session")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=status_text,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Progress update error: {e}")

    async def run_tests(self, proxies):
        """Run all proxy tests"""
        self.total_proxies = len(proxies)
        self.session['total_proxies'] = self.total_proxies
        
        print(f"Testing {len(proxies)} proxies for premium residential...")
        
        chunks = [proxies[i:i + self.chunk_size] for i in range(0, len(proxies), self.chunk_size)]
        
        for i, chunk in enumerate(chunks):
            if self.session.get('is_cancelled'):
                break
            
            print(f"Chunk {i+1}/{len(chunks)} ({len(chunk)} proxies)...")
            
            try:
                await self.test_proxies_chunk(chunk)
            except Exception as chunk_error:
                logger.error(f"Chunk error: {chunk_error}")
                continue
            
            if i < len(chunks) - 1:
                await asyncio.sleep(5)


class FastProxyChecker:
    def __init__(self, bot, session):
        self.bot = bot
        self.session = session
        self.working_proxies = []
        self.checked_count = 0
        self.total_proxies = 0
        self.lock = threading.Lock()
        self.start_time = time.time()
        
        self.timeout = 4
        self.max_concurrent = 15
        self.test_url = "http://httpbin.org/ip"
        self.chunk_size = 30
        
    def parse_proxy(self, proxy_line):
        """Parse all different proxy formats"""
        proxy_line = proxy_line.strip()
        if not proxy_line or proxy_line.startswith('#'):
            return None
        
        if proxy_line.startswith('(Http)'):
            proxy_line = proxy_line[6:].strip()
        
        try:
            if proxy_line.startswith(('http://', 'https://')):
                return proxy_line
            
            if proxy_line.startswith('socks5://'):
                socks_part = proxy_line[9:]
                return f"http://{socks_part}"
            
            if '@' in proxy_line and proxy_line.count(':') >= 3:
                auth_part, host_port = proxy_line.split('@', 1)
                username, password = auth_part.split(':', 1)
                return f"http://{username}:{password}@{host_port}"
            
            parts = proxy_line.split(':')
            if len(parts) >= 4:
                host, port, username = parts[0], parts[1], parts[2]
                password = ':'.join(parts[3:])
                return f"http://{username}:{password}@{host}:{port}"
            
            elif len(parts) == 2:
                host, port = parts[0], parts[1]
                return f"http://{host}:{port}"
        
        except Exception:
            pass
        
        return None

    def clean_proxy_output(self, proxy):
        """Clean proxy for output"""
        if proxy.startswith('http://'):
            return proxy[7:]
        elif proxy.startswith('https://'):
            return proxy[8:]
        return proxy

    async def test_proxy_async(self, session, proxy, semaphore):
        """Test a single proxy"""
        async with semaphore:
            try:
                start_time = time.time()
                
                timeout_config = aiohttp.ClientTimeout(total=self.timeout, connect=2)
                
                async with session.get(
                    self.test_url,
                    proxy=proxy,
                    timeout=timeout_config,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    ssl=False
                ) as response:
                    
                    if response.status == 200:
                        end_time = time.time()
                        response_time = round((end_time - start_time) * 1000, 2)
                        
                        try:
                            data = await response.json()
                            ip_info = data.get('origin', 'Working')
                        except:
                            try:
                                ip_info = (await response.text()).strip() or 'Working'
                            except:
                                ip_info = 'Working'
                        
                        return proxy, True, response_time, ip_info
                        
            except Exception:
                pass
            
            return proxy, False, 0, None

    async def test_proxies_chunk(self, proxies_chunk):
        """Test a chunk of proxies"""
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent * 2,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        timeout_config = aiohttp.ClientTimeout(total=self.timeout * 2)
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout_config,
            skip_auto_headers=['User-Agent']
        ) as session:
            
            tasks = [self.test_proxy_async(session, proxy, semaphore) for proxy in proxies_chunk]
            
            for coro in asyncio.as_completed(tasks):
                if self.session.get('is_cancelled'):
                    break
                    
                try:
                    result = await coro
                    
                    with self.lock:
                        self.checked_count += 1
                        proxy, is_working, response_time, ip_info = result
                        
                        if is_working:
                            clean_proxy = self.clean_proxy_output(proxy)
                            proxy_data = {
                                'proxy': clean_proxy,
                                'response_time': response_time,
                                'ip': ip_info
                            }
                            self.working_proxies.append(proxy_data)
                            self.session['working_proxies'].append(proxy_data)
                            
                            print(f"Working: {clean_proxy} | {response_time}ms")
                        
                        self.session['checked_count'] = self.checked_count
                        
                        if self.checked_count % 10 == 0:
                            try:
                                await self.send_progress_update()
                            except Exception as e:
                                logger.error(f"Progress update error: {e}")
                                
                except Exception as task_error:
                    logger.error(f"Task error: {task_error}")
                    with self.lock:
                        self.checked_count += 1
                    continue

    async def send_progress_update(self):
        """Send progress update"""
        if self.session.get('is_cancelled'):
            return
        
        try:
            user_id = self.session['user_id']
            message_id = self.session.get('status_message_id')
            
            if not message_id:
                return
            
            elapsed = time.time() - self.start_time
            progress = (self.checked_count / self.total_proxies) * 100 if self.total_proxies > 0 else 0
            rate = self.checked_count / elapsed if elapsed > 0 else 0
            eta = (self.total_proxies - self.checked_count) / rate if rate > 0 else 0
            
            status_text = f"""Checking Proxies... (Fast Mode)

Progress: {self.checked_count:,}/{self.total_proxies:,} ({progress:.1f}%)
Elapsed: {elapsed:.0f}s | Rate: {rate:.1f}/s
ETA: {eta:.0f}s remaining
Working Found: {len(self.working_proxies)}

Status: Fast checking in progress..."""
            
            keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_session")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=status_text,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Progress update error: {e}")

    async def run_tests(self, proxies):
        """Run all proxy tests"""
        self.total_proxies = len(proxies)
        self.session['total_proxies'] = self.total_proxies
        
        print(f"Testing {len(proxies)} proxies for fast checking...")
        
        chunks = [proxies[i:i + self.chunk_size] for i in range(0, len(proxies), self.chunk_size)]
        
        for i, chunk in enumerate(chunks):
            if self.session.get('is_cancelled'):
                break
            
            print(f"Chunk {i+1}/{len(chunks)} ({len(chunk)} proxies)...")
            
            try:
                await self.test_proxies_chunk(chunk)
            except Exception as chunk_error:
                logger.error(f"Chunk error: {chunk_error}")
                continue
            
            if i < len(chunks) - 1:
                await asyncio.sleep(3)


class CombinedProxyBot:
    def __init__(self):
        self.active_sessions = {}
        self.session_lock = threading.Lock()
        self.user_stats = {}
        
    def is_admin(self, user_id):
        """Check if user is admin"""
        return user_id in ADMIN_IDS
        
    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin command to view bot statistics"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("Access denied. Admin only command.")
            return
            
        try:
            total_users = len(self.user_stats)
            active_sessions = len(self.active_sessions)
            
            sorted_users = sorted(self.user_stats.items(), key=lambda x: x[1].get('total_checks', 0), reverse=True)
            
            stats_text = f"""Bot Statistics

Total Users: {total_users}
Active Sessions: {active_sessions}
Memory Usage: {len(self.active_sessions)} sessions stored

Top Users:"""
            
            for i, (uid, data) in enumerate(sorted_users[:5], 1):
                username = data.get('username', 'Unknown')
                total_checks = data.get('total_checks', 0)
                stats_text += f"\n{i}. @{username} - {total_checks} checks"
            
            if active_sessions > 0:
                stats_text += f"\n\nActive Sessions:"
                for session_user_id, session in self.active_sessions.items():
                    mode = session.get('mode', 'unknown')
                    progress = session.get('checked_count', 0)
                    total = session.get('total_proxies', 0)
                    stats_text += f"\nUser {session_user_id}: {mode} mode ({progress}/{total})"
            
            await update.message.reply_text(stats_text)
            
        except Exception as e:
            await update.message.reply_text(f"Error generating stats: {str(e)}")
    
    def update_user_stats(self, user_id, username, first_name, mode=None):
        """Update user statistics"""
        if user_id not in self.user_stats:
            self.user_stats[user_id] = {
                'username': username,
                'first_name': first_name,
                'total_checks': 0,
                'last_seen': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'preferred_mode': None
            }
        
        self.user_stats[user_id]['last_seen'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if mode:
            self.user_stats[user_id]['preferred_mode'] = mode
            self.user_stats[user_id]['total_checks'] += 1
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        try:
            user = update.effective_user
            user_id = user.id
            
            self.update_user_stats(user_id, user.username or 'None', user.first_name or 'Unknown')
            
            print(f"User {user_id} ({user.first_name}) started the bot")
            
            welcome_text = f"""Combined Proxy Checker Bot

Hello {user.first_name}!

Choose your checking mode:

RESIDENTIAL CHECKER:
• Premium residential proxy detection
• Advanced IP analysis and scoring  
• Quality score: 35+ points
• Settings: 6s timeout, 12 concurrent
• Best for: Finding high-quality residential proxies

FAST CHECKER:
• Ultra-fast HTTP connectivity testing
• Basic working proxy detection
• Settings: 4s timeout, 15 concurrent
• Best for: Quick proxy validation

Max limit: 15,000 proxies for both modes
Select your preferred mode below:"""
            
            keyboard = [
                [InlineKeyboardButton("Residential Checker", callback_data="mode_residential")],
                [InlineKeyboardButton("Fast Checker", callback_data="mode_fast")],
                [InlineKeyboardButton("Help", callback_data="show_help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                welcome_text, 
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Start command error: {e}")
            await update.message.reply_text("Error occurred. Please try again.")

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle uploaded proxy file"""
        try:
            user_id = update.effective_user.id
            
            if not context.user_data.get('waiting_for_file'):
                await update.message.reply_text("Use /start command first and select a mode!")
                return
            
            document = update.message.document
            
            if not document.file_name.endswith('.txt'):
                await update.message.reply_text("Send a .txt file only!")
                return
            
            if document.file_size > 2 * 1024 * 1024:  # 2MB limit for stability
                await update.message.reply_text("File too large! Max: 2MB")
                return
            
            processing_msg = await update.message.reply_text("Processing file...")
            
            try:
                file = await context.bot.get_file(document.file_id)
                file_content = await file.download_as_bytearray()
                
                try:
                    content = file_content.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        content = file_content.decode('latin-1')
                    except UnicodeDecodeError:
                        content = file_content.decode('utf-8', errors='ignore')
                
                lines = content.splitlines()
                
                raw_proxies = []
                for line in lines:
                    clean_line = line.strip()
                    if clean_line and not clean_line.startswith('#'):
                        raw_proxies.append(clean_line)
                
                if not raw_proxies:
                    await processing_msg.edit_text("No valid proxies found!")
                    return
                
                max_proxies = 15000  # Reduced for Render stability
                if len(raw_proxies) > max_proxies:
                    await processing_msg.edit_text(
                        f"Too many proxies! Found: {len(raw_proxies):,}, Max: {max_proxies:,}"
                    )
                    return
                
                await processing_msg.delete()
                context.user_data['waiting_for_file'] = False
                await self.start_checking(update, context, raw_proxies, document.file_name)
                
            except Exception as file_error:
                logger.error(f"File error: {file_error}")
                await processing_msg.edit_text(f"File processing error: {str(file_error)[:50]}")
                
        except Exception as e:
            logger.error(f"Document handler error: {e}")
            await update.message.reply_text("File processing failed. Try again.")

    async def start_checking(self, update: Update, context: ContextTypes.DEFAULT_TYPE, proxies, filename):
        """Start the checking process"""
        try:
            user_id = update.effective_user.id
            mode = context.user_data.get('mode')
            
            self.update_user_stats(user_id, update.effective_user.username or 'None', 
                                 update.effective_user.first_name or 'Unknown', mode)
            
            if user_id in self.active_sessions:
                await update.message.reply_text("Session already exists!")
                return
            
            print(f"Starting {mode} check for user {user_id}: {len(proxies)} proxies")
            
            if mode == 'residential':
                session = {
                    'user_id': user_id,
                    'proxies': proxies,
                    'filename': filename,
                    'mode': mode,
                    'start_time': time.time(),
                    'checked_count': 0,
                    'premium_proxies': [],
                    'total_proxies': len(proxies),
                    'is_cancelled': False,
                    'status_message_id': None
                }
                mode_text = "Premium Residential Detection"
                settings_text = "6s timeout, 12 concurrent"
            else:
                session = {
                    'user_id': user_id,
                    'proxies': proxies,
                    'filename': filename,
                    'mode': mode,
                    'start_time': time.time(),
                    'checked_count': 0,
                    'working_proxies': [],
                    'total_proxies': len(proxies),
                    'is_cancelled': False,
                    'status_message_id': None
                }
                mode_text = "Fast HTTP Checking"
                settings_text = "4s timeout, 15 concurrent"
            
            self.active_sessions[user_id] = session
            
            keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_session")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            status_text = f"""Proxy Checking Started

File: {filename}
Proxies: {len(proxies):,}
Mode: {mode_text}
Settings: {settings_text}
Status: Starting...

This will analyze each proxy for quality!"""
            
            message = await update.message.reply_text(status_text, reply_markup=reply_markup)
            session['status_message_id'] = message.message_id
            
            asyncio.create_task(self.run_checking_process(context.bot, session))
            
        except Exception as e:
            logger.error(f"Start checking error: {e}")
            await update.message.reply_text("Error starting. Try again.")

    async def run_checking_process(self, bot, session):
        """Main checking process"""
        try:
            print(f"Starting {session['mode']} process for user {session['user_id']}")
            
            if session['mode'] == 'residential':
                checker = EnhancedResidentialChecker(bot, session)
            else:
                checker = FastProxyChecker(bot, session)
            
            parsed_proxies = []
            for line in session['proxies']:
                try:
                    parsed = checker.parse_proxy(line)
                    if parsed:
                        parsed_proxies.append(parsed)
                except Exception:
                    continue
            
            if not parsed_proxies:
                await self.send_error_message(bot, session, "No valid proxies found")
                return
            
            unique_proxies = list(dict.fromkeys(parsed_proxies))
            removed = len(parsed_proxies) - len(unique_proxies)
            if removed > 0:
                print(f"Removed {removed} duplicates")
            
            session['total_proxies'] = len(unique_proxies)
            
            await checker.run_tests(unique_proxies)
            
            if not session.get('is_cancelled'):
                await self.send_final_results(bot, session)
            
        except Exception as e:
            logger.error(f"Process error: {e}")
            traceback.print_exc()
            await self.send_error_message(bot, session, str(e))
        
        finally:
            try:
                user_id = session['user_id']
                if user_id in self.active_sessions:
                    del self.active_sessions[user_id]
                print(f"Finished for user {user_id}")
            except Exception:
                pass

    async def send_final_results(self, bot, session):
        """Send final results based on mode"""
        try:
            user_id = session['user_id']
            mode = session['mode']
            total_time = time.time() - session['start_time']
            
            if mode == 'residential':
                results = session.get('premium_proxies', [])
                result_type = "premium residential"
            else:
                results = session.get('working_proxies', [])
                result_type = "working"
            
            success_rate = (len(results) / session['total_proxies']) * 100 if session['total_proxies'] > 0 else 0
            avg_rate = session['total_proxies'] / total_time if total_time > 0 else 0
            
            summary = f"""Proxy Checking Complete!

Mode: {mode.title()} Checker
Results:
• Checked: {session['total_proxies']:,}
• {result_type.title()} found: {len(results)}
• Success: {success_rate:.1f}%
• Time: {total_time:.1f}s
• Rate: {avg_rate:.1f}/s

{f"Top {result_type} proxies:" if results else f"No {result_type} proxies found"}"""
            
            if results:
                if mode == 'residential':
                    sorted_results = sorted(results, key=lambda x: x['details']['quality_score'], reverse=True)
                    for i, proxy_data in enumerate(sorted_results[:5], 1):
                        details = proxy_data['details']
                        summary += f"\n{i}. {proxy_data['proxy']}"
                        summary += f"\n   {proxy_data['response_time']}ms | Score: {details['quality_score']} | {details['country']}"
                else:
                    sorted_results = sorted(results, key=lambda x: x.get('response_time', 9999))
                    for i, proxy_data in enumerate(sorted_results[:5], 1):
                        summary += f"\n{i}. {proxy_data['proxy']}"
                        summary += f"\n   {proxy_data['response_time']}ms"
            
            await bot.send_message(user_id, summary)
            
            if results:
                await self.send_result_files(bot, user_id, session)
                
        except Exception as e:
            logger.error(f"Results error: {e}")

    async def send_result_files(self, bot, user_id, session):
        """Send result files based on mode"""
        try:
            mode = session['mode']
            
            if mode == 'residential':
                results = session.get('premium_proxies', [])
                file_prefix = "premium_residential"
                file_description = "Premium Residential Proxies"
            else:
                results = session.get('working_proxies', [])
                file_prefix = "working_proxies"
                file_description = "Working Proxies"
            
            if not results:
                return
                
            timestamp = int(time.time())
            
            clean_content = ""
            for proxy_data in results:
                clean_content += f"{proxy_data['proxy']}\n"
            
            clean_file = io.BytesIO(clean_content.encode('utf-8'))
            clean_file.name = f"{file_prefix}_{timestamp}.txt"
            
            await bot.send_document(
                user_id,
                clean_file,
                caption=f"{file_description} ({len(results)} found)"
            )
            
            detailed_content = f"# {file_description} Results\n"
            detailed_content += f"# Checked: {session['total_proxies']}\n"
            detailed_content += f"# Found: {len(results)}\n"
            detailed_content += f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            if mode == 'residential':
                sorted_results = sorted(results, key=lambda x: x['details']['quality_score'], reverse=True)
                for proxy_data in sorted_results:
                    details = proxy_data['details']
                    detailed_content += f"{proxy_data['proxy']} # {proxy_data['response_time']}ms | Score: {details['quality_score']} | {details['country']} | {details['isp']} | IP: {details['ip']}\n"
            else:
                sorted_results = sorted(results, key=lambda x: x.get('response_time', 9999))
                for proxy_data in sorted_results:
                    detailed_content += f"{proxy_data['proxy']} # {proxy_data['response_time']}ms | {proxy_data['ip']}\n"
            
            detailed_file = io.BytesIO(detailed_content.encode('utf-8'))
            detailed_file.name = f"detailed_{file_prefix}_{timestamp}.txt"
            
            await bot.send_document(
                user_id,
                detailed_file,
                caption="Detailed Results with analysis"
            )
            
            print(f"Files sent to user {user_id}")
            
        except Exception as e:
            logger.error(f"File sending error: {e}")

    async def send_error_message(self, bot, session, error):
        """Send error message"""
        try:
            user_id = session.get('user_id')
            if user_id:
                await bot.send_message(
                    user_id,
                    f"Error: {str(error)[:150]}\n\nTry again with /start"
                )
        except Exception as e:
            logger.error(f"Error message failed: {e}")

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel session"""
        try:
            user_id = update.effective_user.id
            
            if user_id not in self.active_sessions:
                await update.message.reply_text("No active session.")
                return
            
            self.active_sessions[user_id]['is_cancelled'] = True
            await update.message.reply_text("Session cancelled.\n\nUse /start to begin again.")
            
            await asyncio.sleep(2)
            if user_id in self.active_sessions:
                del self.active_sessions[user_id]
                
        except Exception as e:
            logger.error(f"Cancel error: {e}")
            await update.message.reply_text("Cancel failed.")

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button clicks"""
        try:
            query = update.callback_query
            await query.answer()
            
            data = query.data
            user_id = update.effective_user.id
            
            if data == "mode_residential":
                context.user_data['mode'] = 'residential'
                context.user_data['waiting_for_file'] = True
                
                instructions = """Send your proxy list file

RESIDENTIAL CHECKER MODE SELECTED

Supported formats:
• ip:port
• ip:port:username:password  
• username:password@ip:port
• http://ip:port
• socks5://ip:port

Requirements:
• .txt file format only
• One proxy per line
• Max 15,000 proxies
• Max file size: 2MB

This mode will analyze each proxy for:
- ISP type and residential indicators
- Hosting/datacenter detection
- Mobile connection detection
- Quality scoring (35+ = premium)

Upload your file now..."""
                
                await query.edit_message_text(instructions)
                
            elif data == "mode_fast":
                context.user_data['mode'] = 'fast'
                context.user_data['waiting_for_file'] = True
                
                instructions = """Send your proxy list file

FAST CHECKER MODE SELECTED

Supported formats:
• ip:port
• ip:port:username:password  
• username:password@ip:port
• http://ip:port
• socks5://ip:port

Requirements:
• .txt file format only
• One proxy per line
• Max 15,000 proxies
• Max file size: 2MB

This mode will test for:
- Basic HTTP connectivity
- Response time measurement
- IP extraction
- Quick validation only

Upload your file now..."""
                
                await query.edit_message_text(instructions)
                
            elif data == "show_help":
                help_text = """HELP - Combined Proxy Checker Bot

RESIDENTIAL CHECKER:
• Deep analysis of proxy quality
• ISP detection and scoring
• Mobile/hosting identification
• Premium threshold: 35+ points
• Slower but more detailed
• Best for: Quality over quantity

FAST CHECKER:
• Quick HTTP connectivity test
• Basic working validation
• Response time measurement
• No quality analysis
• Faster processing
• Best for: Quantity over quality

SUPPORTED FORMATS:
• ip:port
• ip:port:user:pass
• user:pass@ip:port
• http://ip:port
• socks5://ip:port

LIMITS & SPECS:
• Max proxies: 15,000
• Max file size: 2MB
• File format: .txt only

COMMANDS:
/start - Main menu
/cancel - Stop active session

Choose mode based on your needs!"""
                
                keyboard = [
                    [InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(help_text, reply_markup=reply_markup)
                
            elif data == "back_to_menu":
                welcome_text = """Combined Proxy Checker Bot

Choose your checking mode:

RESIDENTIAL CHECKER:
• Premium residential proxy detection
• Advanced IP analysis and scoring
• Quality score: 35+ points
• Settings: 6s timeout, 12 concurrent
• Best for: Finding high-quality residential proxies

FAST CHECKER:
• Ultra-fast HTTP connectivity testing
• Basic working proxy detection
• Settings: 4s timeout, 15 concurrent
• Best for: Quick proxy validation

Max limit: 15,000 proxies for both modes
Select your preferred mode below:"""
                
                keyboard = [
                    [InlineKeyboardButton("Residential Checker", callback_data="mode_residential")],
                    [InlineKeyboardButton("Fast Checker", callback_data="mode_fast")],
                    [InlineKeyboardButton("Help", callback_data="show_help")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(welcome_text, reply_markup=reply_markup)
                
            elif data == "cancel_session":
                if user_id not in self.active_sessions:
                    await query.edit_message_text("No session found.")
                    return
                
                self.active_sessions[user_id]['is_cancelled'] = True
                await query.edit_message_text("Session cancelled.\n\nUse /start to restart.")
                
                await asyncio.sleep(2)
                if user_id in self.active_sessions:
                    del self.active_sessions[user_id]
                    
        except Exception as e:
            logger.error(f"Button error: {e}")
            try:
                await query.edit_message_text("Error occurred.")
            except:
                pass


async def setup_bot():
    """Setup the bot application"""
    global bot_application, proxy_bot
    
    try:
        print("Creating bot application...")
        
        bot_application = (
            Application.builder()
            .token(BOT_TOKEN)
            .read_timeout(30)
            .write_timeout(30)
            .connect_timeout(30)
            .pool_timeout(30)
            .build()
        )
        
        proxy_bot = CombinedProxyBot()
        print("Bot instance created")
        
        bot_application.add_handler(CommandHandler("start", proxy_bot.start))
        bot_application.add_handler(CommandHandler("cancel", proxy_bot.cancel_command))
        bot_application.add_handler(CommandHandler("stats", proxy_bot.admin_stats))
        bot_application.add_handler(MessageHandler(filters.Document.ALL, proxy_bot.handle_document))
        bot_application.add_handler(CallbackQueryHandler(proxy_bot.button_handler))
        
        async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            logger.error(f"Error: {context.error}")
            if update and update.effective_user:
                try:
                    await context.bot.send_message(
                        update.effective_user.id,
                        "An error occurred. Please try /start"
                    )
                except:
                    pass
        
        bot_application.add_error_handler(error_handler)
        print("Handlers registered")
        
        await bot_application.initialize()
        await bot_application.start()
        
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await bot_application.bot.set_webhook(webhook_url)
        print(f"Webhook set: {webhook_url}")
        
        print("Bot setup complete!")
        return True
        
    except Exception as e:
        print(f"Bot setup failed: {e}")
        traceback.print_exc()
        return False


def run_webhook_server():
    """Run the webhook server"""
    try:
        print(f"Starting webhook server on port {PORT}")
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        print(f"Flask server error: {e}")


async def main():
    """Main function - Webhook mode only"""
    print("=" * 60)
    print("COMBINED PROXY CHECKER BOT - RENDER WEBHOOK DEPLOYMENT")
    print("=" * 60)
    print(f"Token: {BOT_TOKEN[:10]}...{BOT_TOKEN[-10:]}")
    print(f"Admin IDs: {ADMIN_IDS}")
    print(f"Port: {PORT}")
    print(f"Webhook URL: {WEBHOOK_URL}")
    print("=" * 60)
    
    if not WEBHOOK_URL.startswith(('http://', 'https://')):
        print(f"ERROR: WEBHOOK_URL must start with http:// or https://")
        return
    
    if not test_bot_connection():
        print("Bot connection failed!")
        return
    
    if not await setup_bot():
        print("Bot setup failed!")
        return
    
    print("Bot is running in webhook mode!")
    print(f"Health check: {WEBHOOK_URL}/")
    print(f"Webhook endpoint: {WEBHOOK_URL}/webhook")
    print("Go to Telegram and send /start to your bot!")
    
    run_webhook_server()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()