#!/bin/bash

# PostPilot Flask App - Quick Setup Script
# This script sets up and runs the Flask application locally

set -e  # Exit on error

echo "🚀 PostPilot Flask Setup"
echo "========================"
echo ""

# Check Python version
echo "✓ Checking Python version..."
python3 --version

# Install dependencies
echo "✓ Installing dependencies..."
pip install -r requirements.txt -q

# Create necessary directories
echo "✓ Setting up directories..."
mkdir -p posts images static templates

# Check if posts exist
if [ ! -f "posts/tour_posts.json" ]; then
    echo "⚠️  Warning: posts/tour_posts.json not found"
    echo "Creating template..."
    mkdir -p posts
    echo "[]" > posts/tour_posts.json
fi

if [ ! -f "posts/visa_posts.json" ]; then
    echo "⚠️  Warning: posts/visa_posts.json not found"
    echo "Creating template..."
    echo "[]" > posts/visa_posts.json
fi

if [ ! -f "posts/insta_posts.json" ]; then
    echo "⚠️  Warning: posts/insta_posts.json not found"
    echo "Creating template..."
    echo "[]" > posts/insta_posts.json
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 Before running the app:"
echo "  1. Update Facebook credentials in tour.py, visa.py, insta.py"
echo "  2. Add your images to the 'images/' folder"
echo "  3. Update post data in posts/ JSON files"
echo ""
echo "🚀 Starting Flask app..."
echo "   Access the app at: http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Run Flask
python app.py
