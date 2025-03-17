from dotenv import load_dotenv
from flask import (
    flash,
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    Response,
    session,
    stream_with_context,
    url_for,
)
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.errors import HttpError
import html
import isodate
import json
import math
import os
import requests
import random
import re
import time

import db

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("API_KEY")

CLIENT_SECRETS_FILE = "client_secret.json"

SCOPES = ["https://www.googleapis.com/auth/youtube"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

DEBUG_MODE = False


def get_youtube_service():
    if "credentials" not in session:
        return redirect(url_for("authorize"))
    credentials = google.oauth2.credentials.Credentials(**session["credentials"])
    return googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials
    )


PLAYLISTS = {
    "hall_of_myths": {
        "display_name": "Hall of Myths",
        "description": "Vocaloid Songs That Have Reached 10,000,000+ Views On NicoNicoDouga",
        "list_id": 6477,
        "current_song_number": 0,
        "total_song_number": 0,
        "playlist_id": 0,
    },
    "hall_of_legends": {
        "display_name": "Hall of Legends",
        "description": "Vocaloid Songs That Have Reached 1,000,000+ Views On NicoNicoDouga",
        "list_id": 30,
        "current_song_number": 0,
        "total_song_number": 0,
        "playlist_id": 0,
    },
    "hall_of_fame": {
        "display_name": "Hall of Fame",
        "description": "Vocaloid Songs That Have Reached 100,000+ Views On NicoNicoDouga",
        "list_id": 186,
        "current_song_number": 0,
        "total_song_number": 0,
        "playlist_id": 0,
    },
}


def make_playlist(youtube, title):
    request = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": "A playlist generated by Vocaloid Playlist Creator",
            },
            "status": {"privacyStatus": "public"},
        },
    )

    try:
        response = request.execute()
        return (True, response.get("id"))  # Always return a string on success

    except googleapiclient.errors.HttpError as e:
        print(e)
        error_content = json.loads(
            e.content.decode("utf-8")
        )  # Convert from bytes to dict
        reason = (
            error_content.get("error", {})
            .get("errors", [{}])[0]
            .get("reason", "Unknown error")
        )

        error_message = f"Error creating playlist: {reason}"
        if reason == "RATE_LIMIT_EXCEEDED":
            error_message = (
                "Youtube Data API Quota Limit Exceeded - Please Try Again Later"
            )

        json_error_message = json.dumps(
            {"error": error_message}, ensure_ascii=False
        )  # Return JSON string instead of yielding
        return (False, json_error_message)


def extract_video_id(url):
    pattern = (
        r"(?:https?://)?"  # Optional scheme.
        r"(?:www\.)?"  # Optional www.
        r"(?:m\.)?"  # Optional mobile subdomain.
        r"(?:youtube\.com|youtu\.be)"  # Domain.
        r"(?:/watch\?v=|/embed/|/v/|/)"  # Different path formats.
        r"([0-9A-Za-z_-]{11})"  # Video ID: 11 allowed characters.
    )

    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None


def get_video_with_highest_views(youtube, video_ids):
    request = youtube.videos().list(part="statistics", id=",".join(video_ids))
    response = request.execute()

    max_views = -1
    best_video_id = None

    for item in response.get("items", []):
        video_id = item["id"]
        view_count = int(item["statistics"]["viewCount"])

        if view_count > max_views:
            max_views = view_count
            best_video_id = video_id

    return best_video_id


def search_youtube(youtube, song_title, artist=None, max_results=10):
    query = f"{song_title} {artist}" if artist else song_title
    request = youtube.search().list(
        q=query,
        part="snippet",
        maxResults=max_results,
        type="video",
        order="viewCount",
        regionCode="JP",
        relevanceLanguage="ja",
    )
    response = request.execute()

    return response["items"]


def get_video_details(youtube, video_ids):
    request = youtube.videos().list(
        part="contentDetails,statistics,snippet", id=",".join(video_ids)
    )
    response = request.execute()

    video_data = {}
    for item in response["items"]:
        video_id = item["id"]
        duration = item["contentDetails"]["duration"]
        view_count = int(item["statistics"]["viewCount"])
        video_name = item["snippet"]["title"]
        video_data[video_id] = {
            "duration": duration,
            "view_count": view_count,
            "video_name": video_name,
        }
    return video_data


def convert_duration_to_seconds(iso_duration):
    duration = isodate.parse_duration(iso_duration)
    return int(duration.total_seconds())


def decide_on_best_video(vocadb_duration, video_data, tolerance=5):
    best_match = None
    best_score = -float("inf")

    for video_id, details in video_data.items():
        video_duration = convert_duration_to_seconds(details["duration"])
        view_count = int(details["view_count"])
        duration_diff = abs(video_duration - vocadb_duration)

        if duration_diff <= tolerance:
            penalty_factor = 1.0
        else:
            penalty_factor = 0.5 ** ((duration_diff - tolerance) / 10.0)

        score = (view_count / 1000.0) * penalty_factor

        if score > best_score:
            best_score = score
            best_match = video_id

    return best_match


def find_best_youtube_video(youtube, song_title, vocadb_duration, artist=None):

    search_results = search_youtube(youtube, song_title, artist)
    video_ids = [video["id"]["videoId"] for video in search_results]
    video_data = get_video_details(youtube, video_ids)
    best_video_id = decide_on_best_video(vocadb_duration, video_data)

    return best_video_id


def add_video_to_playlist(youtube, playlist_id, video_id):
    max_retries = 5
    delay = 1
    for attempt in range(max_retries):
        try:
            response = (
                youtube.playlistItems()
                .insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id,
                            },
                        }
                    },
                )
                .execute()
            )
            return (True, response)

        except HttpError as e:
            error_details = e.content.decode() if hasattr(e, "content") else str(e)
            print(f"⚠️ Attempt {attempt+1} failed: {error_details}")

            try:
                error_content = json.loads(e.content.decode("utf-8"))
                errors_list = error_content.get("error", {}).get("errors", [])
                if errors_list:
                    reason = errors_list[0].get("reason", "")
                    if reason == "quotaExceeded":
                        error_message = "YouTube Data API Quota Limit Exceeded - Please Try Again Later"
                        return (False, {"error": "🚨 " + error_message})

            except Exception as ex:
                return (
                    False,
                    {"error": "🚨 Error parsing error content: " + ex},
                )

            if e.resp.status in [500, 503, 409]:
                wait_time = delay + random.uniform(0, 0.5)
                print(f"🔄 Retrying in {wait_time:.2f} seconds...")
                time.sleep(wait_time)
                delay *= 2
            else:
                print("❌ Fatal error. Not retrying.")
                break

    print("🚨 Request failed.")
    error_message = (
        "Failed to add video to playlist due to unknown error or max retries reached."
    )
    return (False, error_message)


def add_to_playlist(
    youtube, list_id, playlist_id, start=0, MAX_RESULTS=50, total_count=None
):
    while total_count is None or start < total_count:
        response = requests.get(
            "https://vocadb.net/api/songLists/{list_id}/songs".format(list_id=list_id),
            params={
                "maxResults": MAX_RESULTS,
                "getTotalCount": True,
                "start": start,
            },
            timeout=10,
        )
        data_songs_from_list = response.json()

        if total_count is None:
            total_count = data_songs_from_list["totalCount"]
            db.update_total_song_number(total_count, playlist_id)

        for song_data in data_songs_from_list["items"]:
            song_id = song_data["song"]["id"]
            url_get_song_by_id = f"https://vocadb.net/api/songs/{song_id}"
            response = requests.get(
                url_get_song_by_id, params={"fields": "PVs"}, timeout=10
            )
            data_songs_by_id = response.json()

            youtube_video_ids_to_check, video_id_to_add = [], None
            for item in data_songs_by_id["pvs"]:
                if item["service"] != "Youtube" or item["pvType"] != "Original":
                    continue
                else:
                    youtube_video_ids_to_check.append(extract_video_id(item["url"]))

            if len(youtube_video_ids_to_check) > 1:
                video_id_to_add = get_video_with_highest_views(
                    youtube, youtube_video_ids_to_check
                )
                review_status = True
            elif len(youtube_video_ids_to_check) == 1:
                video_id_to_add = youtube_video_ids_to_check[0]
                review_status = True
            else:
                print(
                    f"No Original PVs Found for: {data_songs_by_id["defaultName"]} - {data_songs_by_id["artistString"]}"
                )
                video_id_to_add = find_best_youtube_video(
                    youtube,
                    data_songs_by_id["defaultName"],
                    data_songs_by_id["lengthSeconds"],
                    data_songs_by_id["artistString"],
                )
                review_status = False

            if video_id_to_add:
                success, result = add_video_to_playlist(
                    youtube, playlist_id, video_id_to_add
                )
                if not success:
                    yield (False, result)
                    return

            current_song_number = song_data["order"]
            db.update_current_song_number(current_song_number, playlist_id)

            db.insert_song(
                song_id,
                playlist_id,
                data_songs_by_id["defaultName"],
                data_songs_by_id["artistString"],
                video_id_to_add,
                review_status,
                song_data["order"],
            )

            if video_id_to_add:
                video_details = get_video_details(youtube, [video_id_to_add])
                video_name = video_details[video_id_to_add]["video_name"]

            message = (
                {
                    "message": f"✅ Successfully added: {video_name} to playlist. ({current_song_number}/{total_count})"
                }
                if video_id_to_add
                else {
                    "message": f"✅ No search results found for {data_songs_by_id["defaultName"]} - marked for review. ({current_song_number}/{total_count})"
                }
            )
            yield (True, message)

        start += MAX_RESULTS

    return True


def replace_video_in_playlist(youtube, playlist_id, old_video_id, new_video_id):
    playlist_item_id = None
    position = None
    next_page_token = None

    while True:
        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=next_page_token,
        )
        response = request.execute()

        for item in response.get("items", []):
            if item["snippet"]["resourceId"]["videoId"] == old_video_id:

                playlist_item_id = item["id"]
                position = item["snippet"]["position"]
                break

        next_page_token = response.get("nextPageToken")
        if not next_page_token or playlist_item_id:
            break

    if playlist_item_id is None:
        return None

    youtube.playlistItems().delete(id=playlist_item_id).execute()

    insert_request = youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": new_video_id},
                "position": position,
            }
        },
    )
    insert_response = insert_request.execute()

    return insert_response


@app.route("/")
def index():
    youtube = get_youtube_service()
    if isinstance(youtube, Response):
        return youtube

    playlists_info = db.get_playlist_info()

    for playlist_in_db in playlists_info:
        for key, playlist in PLAYLISTS.items():
            if playlist["display_name"] == playlist_in_db["playlist_name"]:
                playlist["current_song_number"] = playlist_in_db["current_song_number"]
                playlist["total_song_number"] = playlist_in_db["total_song_number"]
                playlist["playlist_id"] = playlist_in_db["playlist_id"]

    return render_template("index.html", playlists=PLAYLISTS)


@app.route("/stream_playlist")
def stream_playlist():
    def event_stream():
        youtube = get_youtube_service()
        list_id = request.args.get("list_id")
        playlist_id = request.args.get("playlist_id")
        current_song_number = int(request.args.get("current_song_number", 0))

        try:
            if current_song_number == 0:
                playlist_key = request.args.get("key")
                if not playlist_key or playlist_key not in PLAYLISTS:
                    yield "data: " + json.dumps(
                        {"error": "Invalid playlist key"}
                    ) + "\n\n"
                    return
                playlist_data = PLAYLISTS[playlist_key]

                success, playlist_id_or_error = make_playlist(
                    youtube,
                    f"{playlist_data['display_name']} - {playlist_data['description']}",
                )

                if not success:
                    yield f"data: {playlist_id_or_error}\n\n"
                    return
                else:
                    playlist_id = playlist_id_or_error

                db.insert_playlist(
                    playlist_id,
                    playlist_data["display_name"],
                    playlist_data["description"],
                )

                yield "data: " + json.dumps(
                    {"success": f"✅ Created playlist: {playlist_data['display_name']}"}
                ) + "\n\n"

            for success, video_info in add_to_playlist(
                youtube, list_id, playlist_id, current_song_number
            ):
                yield "data: " + json.dumps(video_info) + "\n\n"
                if not success:
                    return

            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            yield "data: " + json.dumps(
                {
                    "success": f'🎵 Playlist complete! <a href="{playlist_url}" target="_blank" class="btn btn-success btn-sm"> View Playlist</a>'
                }
            ) + "\n\n"

        except googleapiclient.errors.HttpError as e:
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            yield "data: " + json.dumps(
                {
                    "error": f'⚠️ YouTube API quota reached. Try again later. Current playlist: <a href="{playlist_url}" target="_blank" class="btn btn-success btn-sm"> View Playlist</a>'
                }
            ) + "\n\n"

    return Response(
        stream_with_context(event_stream()), content_type="text/event-stream"
    )


@app.route("/review")
def review():
    songs = db.get_songs_for_review()
    return render_template("review.html", songs=songs)


@app.route("/update_video")
def update_video():
    youtube = get_youtube_service()
    playlist_id = request.args.get("playlist_id")
    song_id = request.args.get("song_id")
    youtube_video_id_old = request.args.get("youtube_video_id_old")
    youtube_video_URL = request.args.get("youtube_video_url")
    youtube_video_id_new = extract_video_id(youtube_video_URL)

    video_details = get_video_details(youtube, [youtube_video_id_new])
    new_video_name = video_details[youtube_video_id_new]["video_name"]

    if youtube_video_id_old == "None":
        add_video_to_playlist(youtube, playlist_id, youtube_video_id_new)
    else:
        replace_video_in_playlist(
            youtube, playlist_id, youtube_video_id_old, youtube_video_id_new
        )
    db.update_song_video(song_id, youtube_video_id_new)

    return jsonify(
        {
            "success": f"Successfully updated video to: {new_video_name}",
            "youtube_video_id_new": youtube_video_id_new,
        }
    )


@app.route("/mark_reviewed")
def mark_reviewed():
    song_id = request.args.get("song_id")
    song_name = request.args.get("song_name")
    db.mark_song_reviewed(song_id)
    return jsonify({"success": f"Successfully marked song {song_name} as reviewed."})


@app.route("/authorize")
def authorize():
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES
    )

    flow.redirect_uri = url_for("oauth2callback", _external=True)

    authorization_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )

    session["state"] = state
    return redirect(authorization_url)


@app.route("/oauth2callback")
def oauth2callback():
    state = session.get("state")

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state
    )
    flow.redirect_uri = url_for("oauth2callback", _external=True)

    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    session["credentials"] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    db.create_tables()
    app.run("localhost", 8080, debug=True)
