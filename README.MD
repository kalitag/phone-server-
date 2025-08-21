# ReviewCheckk Telegram Bot

A production-ready Telegram bot that automates clean, uniform deal posts in "ReviewCheckk" style. The bot detects product links, extracts information, and formats them into standardized posts.

## Features

- 🔗 **Multi-platform Support**: Amazon, Flipkart, Meesho, Myntra, Ajio, and 20+ e-commerce sites
- 🔄 **URL Unshortening**: Automatically resolves shortened links (amzn.to, fkrt.cc, etc.)
- 🧹 **Clean URLs**: Removes affiliate and tracking parameters
- 📝 **Smart Title Extraction**: Brand-first, concise titles with quantity detection
- 💰 **Price Detection**: From messages and product pages
- 📍 **Meesho Special Handling**: Size and PIN code support
- 📸 **Media Support**: Processes photos with captions
- ⚡ **Fast Response**: Target <3 seconds processing time
- 🛡️ **Robust Error Handling**: Never crashes, graceful fallbacks

## Installation

### Prerequisites

- Python 3.10 or higher
- pip package manager
- Telegram Bot Token (get from @BotFather)

### Setup Steps

1. **Clone the repository**
```bash
git clone <repository-url>
cd reviewcheckk-bot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set environment variables**
```bash
# Linux/Mac
export BOT_TOKEN="8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s"

# Windows
set BOT_TOKEN=8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s

# Or create a .env file (recommended)
echo "BOT_TOKEN=8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s" > .env
```

4. **Run the bot**
```bash
python bot.py
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `BOT_TOKEN` | Telegram Bot API token | Yes |
| `LOG_LEVEL` | Logging level (INFO, DEBUG, ERROR) | No (default: INFO) |

### Using .env file (Recommended)

Create a `.env` file in the project root:
```env
BOT_TOKEN=8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s
LOG_LEVEL=INFO
```

Then modify bot.py to use python-dotenv:
```python
from dotenv import load_dotenv
load_dotenv()
```

## Usage

### Basic Commands

- `/start` - Welcome message and introduction
- `/help` - Usage instructions

### Sending Product Links

1. **Text message with link**:
   - Send: `Check this out: https://amzn.to/xyz @299`
   - Bot formats and replies with clean post

2. **Photo with caption**:
   - Send photo with caption containing link
   - Bot processes the caption link

3. **Forwarded messages**:
   - Forward messages containing product links
   - Bot extracts and processes links

4. **Multiple links**:
   - Send multiple links in one message
   - Bot processes each link separately

### Output Format

**Non-Meesho Products**:
```
Nike Sports Shoes 1kg @2999 rs
https://www.amazon.in/dp/example

@reviewcheckk
```

**Meesho Products**:
```
Women's Kurti Set @499 rs
https://www.meesho.com/product/example
Size - S, M, L, XL
Pin - 110001

@reviewcheckk
```

## Deployment

### Local Development

```bash
python bot.py
```

### Production Deployment

#### Using systemd (Linux)

1. Create service file `/etc/systemd/system/reviewcheckk-bot.service`:
```ini
[Unit]
Description=ReviewCheckk Telegram Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/path/to/bot
Environment="BOT_TOKEN=your-token-here"
ExecStart=/usr/bin/python3 /path/to/bot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

2. Enable and start:
```bash
sudo systemctl enable reviewcheckk-bot
sudo systemctl start reviewcheckk-bot
```

#### Using Docker

1. Create Dockerfile:
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
CMD ["python", "bot.py"]
```

2. Build and run:
```bash
docker build -t reviewcheckk-bot .
docker run -d --name reviewcheckk-bot -e BOT_TOKEN=your-token-here reviewcheckk-bot
```

#### Cloud Platforms

- **Heroku**: Add Procfile with `worker: python bot.py`
- **Railway**: Direct deployment from GitHub
- **Render**: Use background worker service
- **AWS EC2/Lambda**: Deploy as containerized service
- **Google Cloud Run**: Deploy as container

## Architecture

### Core Components

1. **URLResolver**: URL detection, unshortening, and sanitization
2. **TitleCleaner**: Title extraction and formatting
3. **PriceExtractor**: Price detection from text and pages
4. **PinDetector**: PIN code extraction for Meesho
5. **ResponseBuilder**: Message formatting

### Data Flow

```
User Message → Extract URLs → Unshorten → Clean URL → 
Extract Title/Price → Format Response → Send Reply
```

## Performance Optimization

- Async/await for non-blocking operations
- Connection pooling for HTTP requests
- Caching for repeated URL requests (optional)
- Timeout limits to prevent hanging
- Concurrent processing for multiple links

## Security Considerations

1. **Token Security**: Never commit BOT_TOKEN to version control
2. **Input Validation**: All user inputs are sanitized
3. **Rate Limiting**: Respect Telegram's rate limits
4. **Error Handling**: No sensitive data in error messages
5. **Web Scraping**: Respects robots.txt and uses appropriate delays

## Troubleshooting

### Common Issues

1. **Bot not responding**:
   - Check BOT_TOKEN is set correctly
   - Verify internet connection
   - Check bot permissions in group chats

2. **"Unable to extract product info"**:
   - Site might be blocking requests
   - Product page structure changed
   - Network timeout

3. **Incorrect price/title**:
   - Site-specific parsing may need adjustment
   - Check for page structure changes

### Logging

Enable debug logging for troubleshooting:
```python
logging.basicConfig(level=logging.DEBUG)
```

Check logs for:
- URL processing steps
- HTTP request/response status
- Parsing decisions
- Error traces

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new features
4. Submit pull request

## Testing

Run tests (if implemented):
```bash
python -m pytest tests/
```

Manual testing checklist:
- [ ] Single link processing
- [ ] Multiple links in one message
- [ ] Photo with caption
- [ ] Forwarded messages
- [ ] Meesho size/PIN handling
- [ ] Invalid/unsupported links
- [ ] Network timeout handling

## License

MIT License - See LICENSE file for details

## Support

For issues and questions:
- Create an issue on GitHub
- Contact @reviewcheckk on Telegram

## Changelog

### v1.0.0 (Current)
- Initial release
- Support for major e-commerce platforms
- URL unshortening and cleaning
- Smart title and price extraction
- Meesho special handling
- Robust error handling

## Future Enhancements

- [ ] Redis caching for repeated URLs
- [ ] Admin commands for configuration
- [ ] Analytics and reporting
- [ ] Webhook support for better scaling
- [ ] Custom output format templates
- [ ] Multi-language support
- [ ] Price tracking and alerts
- [ ] Bulk link processing
- [ ] Image text extraction (OCR)

## Credits

Built with:
- python-telegram-bot
- BeautifulSoup4
- Requests

---

**Note**: This bot is for educational and automation purposes. Ensure compliance with e-commerce sites' terms of service and robots.txt files.
