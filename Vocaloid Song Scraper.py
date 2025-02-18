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

from .env import secret_key
import db


app = Flask(__name__)

app.secret_key = "This is my super secret key that no one is supposed to see."

CLIENT_SECRETS_FILE = "client_secret.json"

SCOPES = ["https://www.googleapis.com/auth/youtube"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

DEBUG_MODE = False


def get_youtube_service():
    """Create and return a youtube API client for making API calls."""
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
        return response.get("id")

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
        json_error_message = json.dumps({"error": error_message}, ensure_ascii=False)

        # yield f"data: {json.dumps({'error': 'Invalid playlist key'})}\n\n"

        yield f"data: {json_error_message}\n\n"
        return None


def extract_video_id(url):
    """
    Extracts the YouTube video ID from a YouTube URL.

    Parameters:
    url (str): The YouTube URL.

    Returns:
    str: The extracted video ID.
    """
    if "youtu.be" in url:
        return url.split("/")[-1]
    elif "watch?v=" in url:
        return url.split("watch?v=")[-1].split("&")[0]


def get_video_with_highest_views(youtube, video_ids):
    """
    Given a list of YouTube video IDs, return the ID of the video with the most views.

    Parameters:
    youtube: The authenticated YouTube API client.
    video_ids: A list of Youtube video IDs.

    Returns:
    str: YouTube video ID of video with most views.
    """
    request = youtube.videos().list(part="statistics", id=",".join(video_ids))
    response = request.execute()

    max_views = -1
    best_video_id = None

    # print(response)

    for item in response.get("items", []):
        video_id = item["id"]
        view_count = int(item["statistics"]["viewCount"])

        if view_count > max_views:
            max_views = view_count
            best_video_id = video_id

    return best_video_id


def search_youtube(youtube, song_title, artist=None, max_results=10):
    """
    Search YouTube for a song title (optionally with an artist) and return the search results.

    Parameters:
    youtube: The authenticated YouTube API client.
    song_title (str): The name of the song.
    artist(str, optional): The name of the artist.
    max_results(int): Number of search items to return. Defaults to 10

    Returns:
    list: A list of search result items (JSON format).
    """
    query = f"{song_title} {artist}" if artist else song_title

    request = youtube.search().list(
        q=query,
        part="snippet",
        maxResults=max_results,
        type="video",
        order="viewCount",
    )

    response = request.execute()

    return response["items"]


def get_video_details(youtube, video_ids):
    """
    Given a list of YouTube video IDs, returns their data.

    Parameters:
    youtube: The authenticated YouTube API client.
    video_ids: A list of YouTube video IDs.

    returns:
    dict: A dictionary mapping video IDs to their duration and view count.
    """
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
    """
    Convert iso_duration to seconds.

    Parameters:
    iso_duration (str): ISO 8601 duration string (e.g., "PT3M45S").

    Returns:
    int: Duration in seconds.
    """
    duration = isodate.parse_duration(iso_duration)
    return int(duration.total_seconds())


def decide_on_best_video(vocadb_duration, video_data, tolerance=5):
    """
     Selects the best YouTube video based on duration similarity and view count.

    This function compares the given `vocadb_duration` with a dictionary of YouTube videos
    (`video_data`) and selects the most suitable video by considering both view count
    and duration closeness within a specified `tolerance`.

    Parameters:
    vocadb_duration (int): The expected song duration (in seconds) from VocaDB.
    video_data (dict): A dictionary where keys are YouTube video IDs and values contain:
                       - "duration" (str): ISO 8601 duration format.
                       - "view_count" (int): The number of views for the video.
    tolerance (int, optional): Acceptable difference (in seconds) between VocaDB
                               duration and video duration. Defaults to 5.

    Returns:
    str: The video ID of the best matching YouTube video, or None if no suitable match is found.
    """
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
    """
    Searches YouTube for the best matching video based on title, artist, and duration.

    This function performs a YouTube search using the song title (and optional artist),
    retrieves video details, and selects the best match using duration similarity and
    view count as ranking factors.

    Parameters:
    youtube: The authenticated YouTube API client.
    song_title (str): The title of the song to search for.
    vocadb_duration (int): The expected song duration (in seconds) from VocaDB.
    artist (str, optional): The artist name to refine the search. Defaults to None.

    Returns:
    str: The video ID of the best matching YouTube video, or None if no suitable match is found.
    """
    search_results = search_youtube(youtube, song_title, artist)

    video_ids = [video["id"]["videoId"] for video in search_results]

    video_data = get_video_details(youtube, video_ids)

    best_video_id = decide_on_best_video(vocadb_duration, video_data)

    return best_video_id


def add_video_to_playlist(youtube, playlist_id, video_id):
    """
    Add a YouTube video to a specified playlist with retry logic using exponential backoff.

    This function attempts to insert a video into the given YouTube playlist by calling the
    YouTube Data API's playlistItems.insert method. It uses exponential backoff with jitter
    to retry the request in case of temporary errors (HTTP status codes 500, 503, or 409).

    Parameters:
        youtube: An authenticated YouTube API client instance.
        playlist_id (str): The ID of the YouTube playlist where the video should be added.
        video_id (str): The YouTube video ID to insert into the playlist.

    Returns:
        dict: The API response if the insertion is successful.
        None: If the maximum number of retries is reached or a non-retriable error occurs.
    """
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
            return response

        except HttpError as e:
            error_details = e.content.decode() if hasattr(e, "content") else str(e)
            print(f"⚠️ Attempt {attempt+1} failed: {error_details}")

            if e.resp.status in [500, 503, 409]:
                wait_time = delay + random.uniform(0, 0.5)
                print(f"🔄 Retrying in {wait_time:.2f} seconds...")
                time.sleep(wait_time)
                delay *= 2
            else:
                print("❌ Fatal error. Not retrying.")
                break
    print("🚨 Max retries reached. Request failed.")
    return None


def add_to_playlist(
    youtube, list_id, playlist_id, start=0, MAX_RESULTS=50, total_count=None
):
    """
    Process a VocaDB song list and add corresponding YouTube videos to a specified playlist.

    This function retrieves songs from a VocaDB list (identified by `list_id`) in batches of
    `MAX_RESULTS` starting from the given `start` index. For each song in the list, it:

      1. Fetches song data from the VocaDB API, including the song's promotional videos (PVs).
      2. Filters the PVs to identify original YouTube PVs.
         - If more than one original YouTube PV is found, it selects the video with the highest view count.
         - If exactly one original YouTube PV is found, that video is used.
         - If no original YouTube PV is found, the function uses a YouTube search (based on the song name,
           its length, and artist) to find the best available video.
      3. Adds the selected YouTube video to the specified YouTube playlist using the YouTube Data API.
      4. Inserts a record into the local database to track the song, including its VocaDB ID, song name,
         artist name, selected YouTube video ID, review status (True if an original PV was found, False if a manual
         review is needed), and the song's original order in the VocaDB list.

    The function uses pagination to process the entire song list: after processing each batch of songs,
    it increments the `start` parameter and repeats until all songs have been processed.

    Parameters:
        youtube: The authenticated YouTube API client.
        list_id (int or str): The VocaDB list ID to retrieve songs from.
        playlist_id (str): The YouTube playlist ID where the videos will be added.
        MAX_RESULTS (int, optional): The maximum number of songs to retrieve per API call. Defaults to 50.
        start (int, optional): The starting index for fetching songs. Defaults to 0.
        total_count (int, optional): The total number of songs in the list (if known); if not provided,
                                     it will be determined from the first API response. Defaults to None.

    Returns:
        None
    """
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

            add_video_to_playlist(youtube, playlist_id, video_id_to_add)

            db.insert_song(
                song_id,
                playlist_id,
                data_songs_by_id["defaultName"],
                data_songs_by_id["artistString"],
                video_id_to_add,
                review_status,
                song_data["order"],
            )

            video_details = get_video_details(youtube, [video_id_to_add])
            video_name = video_details[video_id_to_add]["video_name"]
            current_song_number = song_data["order"]

            print(video_name)
            print(type(video_name))
            message = f"data: {json.dumps({'message': f'✅ Successfully added: {video_name} to playlist. ({current_song_number}/{total_count})'})}\n\n"
            print(message)
            yield message

        start += MAX_RESULTS

    db.update_current_song_number(total_count, playlist_id)

    return True


def replace_video_in_playlist(youtube, playlist_id, old_video_id, new_video_id):
    # """
    # Replace a video in a YouTube playlist by deleting the old video and inserting a new one
    # at the same position.

    # This function does the following:
    #   1. Retrieves the playlist items for the given playlist_id.
    #   2. Finds the playlist item that corresponds to old_video_id and obtains its unique
    #      playlistItem ID and current position.
    #   3. Deletes the found playlist item.
    #   4. Inserts the new video (new_video_id) into the playlist at the same position.

    # Parameters:
    #     youtube: An authenticated YouTube API client.
    #     playlist_id (str): The ID of the YouTube playlist.
    #     old_video_id (str): The YouTube video ID of the video to be replaced.
    #     new_video_id (str): The YouTube video ID of the new video to insert.

    # Returns:
    #     dict: The API response from the insertion of the new video, or None if the old video
    #           wasn't found.
    # """
    playlist_item_id = None
    position = None
    next_page_token = None

    # Step 1: Retrieve playlist items to find the target video.

    while True:
        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,  # Adjust if your playlist might have more than 50 items.
            pageToken=next_page_token,
        )
        response = request.execute()
        # print(response)

        # Loop through the items to locate the old video.
        for item in response.get("items", []):
            # Check if this playlist item corresponds to the old video.
            if item["snippet"]["resourceId"]["videoId"] == old_video_id:

                playlist_item_id = item["id"]
                position = item["snippet"]["position"]
                break

        next_page_token = response.get("nextPageToken")
        if not next_page_token or playlist_item_id:
            break

    if playlist_item_id is None:
        print("Old video not found in the playlist.")
        return None

    # Step 2: Delete the old playlist item.
    youtube.playlistItems().delete(id=playlist_item_id).execute()

    # Step 3: Insert the new video at the same position.
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

    # we have no playlist id if there's no tables

    # playlists_info = db.get_playlist_info()
    # print(playlists_info)
    # playlists_info_dict = {p["playlist_id"]: p for p in playlists_info}
    # print(playlists_info_dict)
    # for key, value in PLAYLISTS.items():
    #     playlist_id = value["list_id"]
    #     if playlist_id in playlists_info_dict:
    #         value["current_song_number"] = playlists_info_dict[playlist_id][
    #             "current_song_number"
    #         ]
    #         value["total_song_number"] = playlists_info_dict[playlist_id][
    #             "total_song_number"
    #         ]
    #     else:
    #         value["current_song_number"] = 0
    #         value["total_song_number"] = 0

    # print(playlists_info)
    # print(PLAYLISTS)
    return render_template(
        "index.html",
        playlists=PLAYLISTS,
    )


# @app.route("/create_playlist")
# def create_playlist():

#     youtube = get_youtube_service()
#     playlist_key = request.args.get("playlist_key")
#     if not playlist_key or playlist_key not in PLAYLISTS:
#         return "Invalid playlist selection", 400

#     playlist_data = PLAYLISTS[playlist_key]
#     playlist_id = make_playlist(
#         youtube, f"{playlist_data["display_name"]} - {playlist_data["description"]}"
#     )
#     print(playlist_id)
#     add_to_playlist(youtube, playlist_data["list_id"], playlist_id)

#     playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

#     db.insert_playlist(
#         playlist_id, playlist_data["display_name"], playlist_data["description"]
#     )

#     flash(
#         f"✅ Playlist '{playlist_data['display_name']}' created successfully! "
#         f"<a href='{playlist_url}' target='_blank' class='btn btn-success btn-sm'> View Playlist</a>",
#         "success",
#     )
#     return redirect(url_for("index"))


# @app.route("/continue_playlist")
# def continue_playlist():
#     youtube = get_youtube_service()
#     list_id = request.args.get("list_id")
#     playlist_id = request.args.get("playlist_id")
#     current_song_number = request.args.get("current_song_number")
#     success = add_to_playlist(youtube, list_id, playlist_id, current_song_number)
#     return jsonify(
#         {
#             "success": success,
#         }
#     )


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

                    yield f"data: {json.dumps({'error': 'Invalid playlist key'})}\n\n"
                    return
                playlist_data = PLAYLISTS[playlist_key]

                playlist_id = make_playlist(
                    youtube,
                    f"{playlist_data["display_name"]} - {playlist_data["description"]}",
                )
                if not isinstance(playlist_id, str):
                    yield from playlist_id
                    return

                db.insert_playlist(
                    playlist_id,
                    playlist_data["display_name"],
                    playlist_data["description"],
                )

                yield f"data: {json.dumps({'message': f'✅ Created playlist: {playlist_data["display_name"]}'})}\n\n"

            for video_info in add_to_playlist(
                youtube, list_id, playlist_id, current_song_number
            ):
                yield f"data: {json.dumps(video_info)}\n\n"
                time.sleep(1)

            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            yield f"data: {json.dumps({'message': f'🎵 Playlist complete! <a href=\"{playlist_url}\" target=\"_blank\" class=\"btn btn-success btn-sm\"> View Playlist</a>'})}\n\n"

        except googleapiclient.errors.HttpError as e:
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            yield f"data: {json.dumps({'error': f'⚠️ YouTube API quota reached. Try again later. Current playlist: <a href=\\"{playlist_url}\" target=\"_blank\" class=\"btn btn-success btn-sm\"> View Playlist</a>'})}\n\n"

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
    youtube_video_id_old = request.args.get("youtube_video_id_old")
    youtube_video_URL = request.args.get("youtube_video_url")
    youtube_video_id_new = extract_video_id(youtube_video_URL)

    video_details = get_video_details(youtube, [youtube_video_id_new])
    new_video_name = video_details[youtube_video_id_new]["video_name"]

    replace_video_in_playlist(
        youtube, playlist_id, youtube_video_id_old, youtube_video_id_new
    )
    success = db.update_song_video(youtube_video_id_old, youtube_video_id_new)

    return jsonify(
        {
            "success": success,
            "video_name": new_video_name,
            "youtube_video_id_new": youtube_video_id_new,
        }
    )


@app.route("/mark_reviewed")
def mark_reviewed():
    song_id = request.args.get("song_id")
    success = db.mark_song_reviewed(song_id)
    return jsonify({"success": success})


@app.route("/authorize")
def authorize():
    """
    Initiate the OAuth 2.0 authorization flow with Google.

    This route creates an OAuth 2.0 flow instance using the client secrets file and the
    specified scopes. It then sets the redirect URI to point to the 'oauth2callback' route,
    generates an authorization URL, saves the generated state in the session for security,
    and finally redirects the user to the Google OAuth consent screen.

    Returns:
        A Flask redirect response to the Google OAuth 2.0 authorization URL.
    """
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES
    )

    flow.redirect_uri = url_for("oauth2callback", _external=True)

    authorization_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true"
    )

    session["state"] = state
    return redirect(authorization_url)


@app.route("/oauth2callback")
def oauth2callback():
    """
    Handle the OAuth 2.0 callback from Google.

    This route is the redirect URI that Google calls after the user has authorized the app.
    It retrieves the saved state from the session, recreates the OAuth flow, and uses the full
    callback URL (which includes the authorization code) to fetch access and refresh tokens.
    The obtained credentials are stored in the session for future API calls, and the user is
    redirected to the index page.

    Returns:
        A Flask redirect response to the 'index' route.
    """
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


@app.route("/clear")
def clear_credentials():
    """
    Clear stored OAuth 2.0 credentials from the session.

    This route is used to log the user out by clearing the session of any stored credentials.
    After clearing the session, the user is redirected back to the index page.

    Returns:
        A Flask redirect response to the 'index' route.
    """
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    """
    Application entry point.

    This block ensures that when the script is run directly, the database tables are created,
    and the Flask application is started on 'localhost' at port 8080 with debug mode enabled.
    """
    db.create_tables()
    app.run("localhost", 8080, debug=True)
