# Vocaloid Playlist Creator

**Vocaloid Playlist Creator** is a web application that gets Vocaloid song data from [VocaDB](https://vocadb.net/) and creates YouTube playlists. The application uses Flask for the backend, integrates with the YouTube Data API for playlist management, and uses MySQL to persist data. Real-time updates are provided via Server-Sent Events (SSE), and Bootstrap toasts are used to notify the user of progress and errors. Data is stored in a MySQL database.

---

Table of Contents

1. Overview
2. Features
3. Prerequisites
4. Installation
5. Configuration
6. Usage
7. Authentication Process
8. Code Structure
9. Troubleshooting
10. Contributing
11. License
12. Acknowledgments

---

## Overview

**Vocaloid Playlist Creator** automates the process of collecting Vocaloid song data from VocaDB's API and curates YouTube playlists based on various criteria such as view counts and duration. The application uses OAuth 2.0 for YouTube authentication, allowing users to create, update, and manage their playlists seamlessly. Real-time progress updates are streamed to the browser via Server-Sent Events (SSE), and Bootstrap toasts notify users of successes, errors, and other important events.

---

## Features

- **Data Fetching from VocaDB:**
  Retrieve song data from VocaDB based on various criteria.
- **YouTube Playlist Management:**
  Create and update YouTube playlists using the YouTube Data API.
- **Real-Time Updates:**
  Use Server-Sent Events (SSE) to stream progress updates to the browser.
- **User Notifications:**
  Display real-time notifications using Bootstrap toasts for success messages and errors.
- **Manual Video Updates:**
  Handle missing or invalid YouTube video IDs and allow manual updates via a web interface.

---

## Prerequisites

- Python 3.7 or higher
- MySQL database server
- A Google Cloud project with the YouTube Data API v3 enabled
- A client_secrets.json file from Google Cloud Console for OAuth credentials

---

## Installation

1. **Clone the Repository:**

```
git clone https://github.com/yourusername/vocaloid-song-scraper.git
cd vocaloid-song-scraper
```

2. **Create a Virtual Environment and Install Dependencies:**

```
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Set Up Environment Variables:**
   Create a .env file (or set environment variables through your hosting service) with values such as:

```
CLIENT_SECRETS_FILE=client_secrets.json
SECRET_KEY=your_secret_key
DATABASE_URL=your_database_connection_string
```

4. **Initialize the Database:**
   Run the provided migrations or SQL scripts to create the necessary tables in your MySQL database.

---

## Configuration

- **Google OAuth:**
  Ensure your CLIENT_SECRETS_FILE is properly configured with your Google client ID, client secret, and redirect URIs.
- **Database:**
  Update your database connection settings to match your MySQL server.

---

## Usage

1. **Run the Application:**
   Start the Flask development server:

```
flask run --port=8080
```

2. **Access the Application:**
   Visit http://localhost:8080 in your web browser.

3. **Create/Update Playlists:**
   - Click "Create Playlist" or "Continue Creating Playlist" to start the scraping and playlist creation process.
   - Watch real-time progress updates and notifications via SSE and Bootstrap toasts.
   - Manually update songs with missing video IDs if necessary.

---

## Authentication Process

The application uses OAuth 2.0 to authenticate with the YouTube Data API. Here's a brief walkthrough:

1. **Authorization Endpoint (/authorize):**

- The app generates an authorization URL using your client secrets and requested scopes.
- It includes parameters like access_type="offline" and prompt="consent" to request a refresh token.
- The user is redirected to Google's consent screen.

2. **OAuth Callback (/oauth2callback):**

- After the user grants access, Google redirects them back to your callback endpoint with an authorization code.
- The app calls flow.fetch_token(authorization_response=request.url) to exchange the code for tokens.
- The credentials (access token, refresh token, etc.) are stored in the session under session["credentials"].

3. **Using Credentials:**

- The get_youtube_service() function checks for stored credentials and builds an authenticated YouTube API client.

---

## Code Structure

- **vocaloid_playlist_creator.py:**
  Main Flask application and route definitions.
- **db.py:**
  Database helper functions for interacting with MySQL (e.g., updating playlist info, inserting songs).
- **templates/:**
- HTML templates rendered by Flask.
- **static/:**
  CSS and JavaScript files, including client-side code for SSE and toast notifications.
- .env:
  Environment variable definitions (not checked into version control).

---

## Troubleshooting

- **OAuth Errors:**
  Check that your client secrets and redirect URIs are correct in the Google Cloud Console.
- **Database Issues:**
  Verify your MySQL connection and ensure that migration scripts have been run successfully.
- **API Quota Problems:**
  Monitor your API usage in the Google Cloud Console. The app handles quota exceeded errors, but you may need to upgrade your quota for high-traffic use.
- **SSE and Toasts:**
  If real-time updates or toasts do not display as expected, check your browser console for JavaScript errors and ensure your SSE endpoint (/stream_playlist) is returning data in the proper format.

---

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests for enhancements and bug fixes.

---

License
This project is licensed under the MIT License. See the LICENSE file for details.

---

## Acknowledgments

- YouTube Data API v3
- VocaDB
- Flask
- Bootstrap
- Other open source projects and resources used in this project.
- ChatGPT

```

```
