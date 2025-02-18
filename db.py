from functools import wraps
import mysql.connector


def get_connection():
    connection = mysql.connector.connect(
        host="localhost", user="root", password="tri1999", database="vocaloid_db"
    )
    return connection


def with_db_connection(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        connection = get_connection()
        try:
            with connection:
                with connection.cursor() as cursor:
                    # Pass the cursor and connection to the function
                    return func(connection, cursor, *args, **kwargs)
        finally:
            connection.close()

    return wrapper


@with_db_connection
def create_tables(connection, cursor):
    create_table_query = """
    CREATE TABLE IF NOT EXISTS songs(
    id INT AUTO_INCREMENT PRIMARY KEY,
    vocadb_id INT NOT NULL,
    playlist_id VARCHAR(50) NOT NULL,
    song_name VARCHAR(255) NOT NULL,
    artist_name VARCHAR(255),
    youtube_video_id VARCHAR(20),
    review_status BOOLEAN DEFAULT FALSE,
    original_order INT,
    UNIQUE KEY unique_order (playlist_id, original_order)
    )
    """
    cursor.execute(create_table_query)
    create_table_query = """
    CREATE TABLE IF NOT EXISTS playlists(
    id INT AUTO_INCREMENT PRIMARY KEY,
    playlist_id VARCHAR(50) NOT NULL,
    playlist_name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    current_song_number INT,
    total_song_number INT,
    UNIQUE (playlist_id)
    )
    """
    cursor.execute(create_table_query)
    connection.commit()


@with_db_connection
def insert_song(
    connection,
    cursor,
    vocadb_id,
    playlist_id,
    song_name,
    artist_name,
    youtube_video_id,
    review_status,
    original_order,
):
    insert_query = """
    INSERT INTO songs (vocadb_id, playlist_id, song_name, artist_name, youtube_video_id, review_status, original_order)
    VALUES (%s,%s,%s,%s,%s,%s,%s)
    """
    values = (
        vocadb_id,
        playlist_id,
        song_name,
        artist_name,
        youtube_video_id,
        review_status,
        original_order,
    )
    cursor.execute(insert_query, values)
    connection.commit()


@with_db_connection
def insert_playlist(connection, cursor, playlist_id, playlist_name, description):
    insert_query = """
    INSERT INTO playlists (playlist_id,playlist_name,description) VALUES (%s,%s,%s)
    """
    values = (playlist_id, playlist_name, description)
    try:
        cursor.execute(insert_query, values)
        connection.commit()
    except mysql.connector.IntegrityError:
        pass


@with_db_connection
def get_songs_for_review(connection, cursor):
    query = """SELECT songs.*, playlists.playlist_name
        FROM songs
        JOIN playlists ON songs.playlist_id = playlists.playlist_id
        WHERE review_status = FALSE
        ORDER BY original_order ASC"""

    cursor.execute(query)

    # Get column names from cursor.description
    columns = [column[0] for column in cursor.description]

    rows = cursor.fetchall()

    songs = []
    for row in rows:
        # Create a dictionary for each row using column names
        song = {columns[i]: row[i] for i in range(len(columns))}

        songs.append(
            {
                "id": song["id"],
                "vocadb_id": song["vocadb_id"],
                "playlist_id": song["playlist_id"],
                "song_name": song["song_name"],
                "artist_name": song["artist_name"],
                "youtube_video_id": song["youtube_video_id"],
                "review_status": song["review_status"],
                "original_order": song["original_order"],
                "playlist_name": song["playlist_name"],
            }
        )

    return songs


@with_db_connection
def update_song_video(connection, cursor, youtube_video_id_old, youtube_video_id_new):
    update_query = "UPDATE songs SET youtube_video_id = %s WHERE youtube_video_id = %s"
    cursor.execute(update_query, (youtube_video_id_new, youtube_video_id_old))
    connection.commit()
    return True


@with_db_connection
def mark_song_reviewed(connection, cursor, song_id):
    update_query = "UPDATE songs SET review_status=TRUE WHERE id=%s"
    cursor.execute(update_query, (song_id,))
    connection.commit()
    return True


@with_db_connection
def get_playlist_info(connection, cursor):
    query = "SELECT id,playlist_id,playlist_name,description,current_song_number,total_song_number FROM playlists"

    cursor.execute(query)

    columns = [column[0] for column in cursor.description]

    playlists = [
        {columns[i]: row[i] for i in range(len(columns))} for row in cursor.fetchall()
    ]

    return playlists


@with_db_connection
def update_total_song_number(connection, cursor, total_song_number, playlist_id):
    update_query = "UPDATE playlists SET total_song_number=%s WHERE playlist_id=%s"
    values = (total_song_number, playlist_id)
    cursor.execute(update_query, values)
    connection.commit()

    return True


@with_db_connection
def update_current_song_number(connection, cursor, current_song_number, playlist_id):
    update_query = "UPDATE playlists SET current_song_number=%s WHERE playlist_id=%s"
    values = (current_song_number, playlist_id)
    cursor.execute(update_query, values)
    connection.commit()

    return True
