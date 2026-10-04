# PostPilot - Flask Platform

PostPilot is a web-based Facebook Auto Poster and Instagram Sync application built with Flask.

## Features

- **Multi-Post Management**: Manage posts for Tour (Nexora Suite), NZ/Visa (Phoenix Intl), Gaatha AI, and Instagram
- **Facebook Integration**: Automatically post to Facebook using Graph API v19.0
- **Instagram Sync**: Sync Facebook posts to Instagram Business profiles
- **Web Interface**: Modern, responsive web UI for desktop, tablet, and mobile browsers
- **Real-time Control**: Start/Stop posting tasks on demand
- **Batch Operations**: Run all posting tasks simultaneously
- **Session Authentication & CSRF**: Secure role-based session login with CSRF protection

## Prerequisites

- Python 3.10+
- pip

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy configuration template and configure credentials:
```bash
cp .env.example .env
```
Update your Meta credentials in `.env`:
- `FB_ACCESS_TOKEN`
- `FB_PAGE_ID_SUITE`
- `FB_PAGE_ID_PHOENIX`
- `FB_PAGE_ID_GAATHA_AI`

## Running the App

### Dev Mode / Termux
```bash
python app.py
```
The app will be available at: `http://localhost:5000`

### Production Mode
```bash
./run-production.sh 4 5000
```
In a separate terminal or service, run the background worker:
```bash
python worker.py
```

## API Endpoints

### Authentication
- `POST /api/auth/login` - Sign in
- `POST /api/auth/logout` - Sign out
- `GET /api/auth/me` - Current session and CSRF token

### Posts Management
- `GET /api/posts/<type>` - Get all posts of a type
- `POST /api/posts/<type>` - Create new post
- `PUT /api/posts/<type>/<id>` - Update post by ID
- `DELETE /api/posts/<type>/<id>` - Delete post by ID
- `DELETE /api/posts/<type>/all` - Delete all posts of a type
- `GET /api/search?q=<query>` - Search posts

### Control & Status
- `POST /api/control/<type>/start` - Start posting loop
- `POST /api/control/<type>/stop` - Stop posting loop
- `POST /api/control/all/start` - Start all tasks
- `POST /api/control/all/stop` - Stop all tasks
- `GET /api/status` - Get current status of all tasks
- `GET /api/interval/<type>` - Get posting interval
- `PUT /api/interval/<type>` - Update posting interval
