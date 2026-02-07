# PostPilot - Flask Version

A web-based Facebook Auto Poster and Instagram Sync application built with Flask.

## Features

- **Multi-Post Management**: Manage posts for Tour, NZ/Visa, and Instagram
- **Facebook Integration**: Automatically post to Facebook using Graph API
- **Instagram Sync**: Sync Facebook posts to Instagram
- **Web Interface**: Modern, responsive web UI for easy management
- **Real-time Control**: Start/Stop posting tasks on demand
- **Batch Operations**: Run all posting tasks simultaneously

## Prerequisites

- Python 3.7+
- pip

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Update Facebook credentials in `tour.py`, `visa.py`, and `insta.py`:
   - Replace `ACCESS_TOKEN` with your Facebook API access token
   - Replace `PAGE_ID` with your Facebook page ID
   - Replace `IG_USER_ID` with your Instagram User ID (for insta.py)

## Running the App

### Dev Mode
```bash
python app.py
```

The app will be available at: `http://localhost:5000`

### Production Mode
```bash
gunicorn app:app
```

## Usage

1. **Add Posts**: Click "➕ Add Post" to create a new post with message and image
2. **Edit Posts**: Click "✏️ Edit" to modify existing posts
3. **Delete Posts**: Click "❌ Delete" to remove posts
4. **Start Posting**: Use individual or "Run All" buttons to start automatic posting
5. **Stop Posting**: Use individual or "Stop All" buttons to halt posting

## Project Structure

```
postpilot/
├── app.py                  # Main Flask application
├── tour.py                 # Tour posting module
├── visa.py                 # NZ/Visa posting module
├── insta.py                # Instagram sync module
├── requirements.txt        # Python dependencies
├── templates/
│   └── index.html         # Main HTML template
├── static/
│   ├── style.css          # Styling
│   ├── script.js          # Frontend logic
│   └── logo.png           # Application logo
├── posts/
│   ├── tour_posts.json    # Tour posts data
│   ├── visa_posts.json    # Visa posts data
│   └── insta_posts.json   # Instagram posts data
└── images/                # Post images
```

## API Endpoints

### Posts Management
- `GET /api/posts/<type>` - Get all posts of a type
- `POST /api/posts/<type>` - Create new post
- `PUT /api/posts/<type>/<index>` - Update post
- `DELETE /api/posts/<type>/<index>` - Delete post

### Control
- `POST /api/control/<type>/start` - Start posting
- `POST /api/control/<type>/stop` - Stop posting
- `POST /api/control/all/start` - Start all tasks
- `POST /api/control/all/stop` - Stop all tasks

### Status
- `GET /api/status` - Get current status of all tasks

### File Upload
- `POST /api/upload` - Upload image file

## Configuration

### Environment Variables
- `FLASK_ENV` - Set to 'development' or 'production'
- `FLASK_DEBUG` - Enable debug mode (development only)

### Settings in Code
- `POST_INTERVAL` - Delay between posts (in tour.py and visa.py)
- `CHECK_INTERVAL` - Interval for Instagram sync check (in insta.py)

## Security Notes

⚠️ **Important**: 
- Never commit actual Facebook API tokens to version control
- Use environment variables for sensitive credentials
- Consider using a `.env` file locally (don't commit it)

## Troubleshooting

### Posts not showing
- Ensure JSON files exist in `posts/` directory
- Check file permissions

### Images not loading
- Verify images exist in `images/` directory
- Check file names match exactly (case-sensitive)

### Facebook posting fails
- Verify access token is valid and not expired
- Check that page ID is correct
- Ensure page has proper permissions

## License

Private Project

## Support

For issues or questions, please contact the project owner.
