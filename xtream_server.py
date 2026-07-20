import os
import re
from flask import Flask, jsonify, redirect, request

app = Flask(__name__)

# File paths for the three M3U files
M3U_FILES = {
    "live": "xtream_live.m3u",
    "vod": "xtream_vod.m3u",
    "series": "xtream_series.m3u",
}

STREAMS = {"live": {}, "vod": {}}
CATEGORIES = {"live": {}, "vod": {}, "series": {}}

# Special structures for TV Series (grouped hierarchy)
SERIES_LIST = {}  # { series_id: { "name": ..., "cover": ..., "category_id": ..., "seasons": {...} } }
EPISODE_MAP = {}  # { episode_id: target_url }


def parse_series_title(name):
    """
    Parses titles like 'Blindspot S05 Blindspot - S05E03 - الحلقة 3'
    Returns: (series_title, season_num, episode_num)
    """
    # 1. Search for S01E01 pattern
    se_match = re.search(r'S(\d+)\s*E(\d+)', name, re.IGNORECASE)
    if se_match:
        season_num = int(se_match.group(1))
        episode_num = int(se_match.group(2))
        
        # Series name is everything before the first 'S05' or 'S05E03'
        raw_title = re.split(r'\bS\d+', name, flags=re.IGNORECASE)[0].strip(" -_")
        series_title = raw_title if raw_title else name
        return series_title, season_num, episode_num

    # 2. Fallback: Search for Season only or default to S1E1
    s_match = re.search(r'\bS(\d+)\b', name, re.IGNORECASE)
    if s_match:
        season_num = int(s_match.group(1))
        raw_title = re.split(r'\bS\d+', name, flags=re.IGNORECASE)[0].strip(" -_")
        return (raw_title if raw_title else name), season_num, 1

    return name, 1, 1


def load_m3u_file(file_path, stype):
    """Parses live, vod, or series M3U files."""
    if not os.path.exists(file_path):
        print(f"[!] File not found: {file_path} (Skipping...)")
        return

    cat_counter = len(CATEGORIES[stype]) + 1
    stream_counter = len(STREAMS.get(stype, {})) + 1

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    current_metadata = {}

    for line in lines:
        line = line.strip()

        if line.startswith("#EXTINF"):
            logo_match = re.search(r'tvg-logo="(.*?)"', line)
            logo = logo_match.group(1) if logo_match else ""

            group_match = re.search(r'group-title="(.*?)"', line)
            cat_name = group_match.group(1) if group_match else "Uncategorized"

            name = line.split(",")[-1].strip()

            current_metadata = {
                "name": name,
                "stream_icon": logo,
                "cat_name": cat_name,
            }

        elif line and not line.startswith("#"):
            if current_metadata:
                target_url = line
                cat_name = current_metadata["cat_name"]

                # Category Management
                cat_dict = CATEGORIES[stype]
                if cat_name not in cat_dict.values():
                    cat_id = str(cat_counter)
                    cat_dict[cat_id] = cat_name
                    cat_counter += 1
                else:
                    cat_id = [k for k, v in cat_dict.items() if v == cat_name][0]

                # If processing TV Series
                if stype == "series":
                    series_title, season_num, episode_num = parse_series_title(current_metadata["name"])

                    # Group by Series Title
                    series_id = None
                    for sid, sdata in SERIES_LIST.items():
                        if sdata["name"].lower() == series_title.lower():
                            series_id = sid
                            break

                    if not series_id:
                        series_id = str(len(SERIES_LIST) + 1)
                        SERIES_LIST[series_id] = {
                            "series_id": series_id,
                            "name": series_title,
                            "cover": current_metadata["stream_icon"],
                            "category_id": cat_id,
                            "seasons": {}  # { season_num: [episodes] }
                        }

                    # Add episode to season
                    ep_id = str(len(EPISODE_MAP) + 1000)
                    EPISODE_MAP[ep_id] = target_url

                    season_key = str(season_num)
                    if season_key not in SERIES_LIST[series_id]["seasons"]:
                        SERIES_LIST[series_id]["seasons"][season_key] = []

                    SERIES_LIST[series_id]["seasons"][season_key].append({
                        "id": ep_id,
                        "episode_num": episode_num,
                        "title": current_metadata["name"],
                        "container_extension": "m3u8",
                        "info": {"duration": "", "rating": 0},
                        "custom_sid": "",
                        "added": "1600000000"
                    })

                # If processing Live or VOD
                else:
                    stream_id = str(stream_counter)
                    stream_counter += 1

                    STREAMS[stype][stream_id] = {
                        "name": current_metadata["name"],
                        "stream_icon": current_metadata["stream_icon"],
                        "category_id": cat_id,
                        "stream_id": stream_id,
                        "target_url": target_url,
                    }

                current_metadata = {}

    if stype == "series":
        print(f"[+] Loaded {file_path}: {len(SERIES_LIST)} unique series, {len(EPISODE_MAP)} total episodes")
    else:
        print(f"[+] Loaded {file_path}: {len(STREAMS[stype])} streams")


def load_all_m3u_files():
    """Clears memory and reloads all playlists."""
    global STREAMS, CATEGORIES, SERIES_LIST, EPISODE_MAP
    STREAMS = {"live": {}, "vod": {}}
    CATEGORIES = {"live": {}, "vod": {}, "series": {}}
    SERIES_LIST.clear()
    EPISODE_MAP.clear()

    print("\n==========================================")
    print("Loading Media Playlists...")
    print("==========================================")
    for stype, file_path in M3U_FILES.items():
        load_m3u_file(file_path, stype)
    print("==========================================\n")


@app.route("/player_api.php", methods=["GET", "POST"])
def xtream_api():
    action = request.args.get("action")
    username = request.args.get("username", "admin")
    password = request.args.get("password", "admin")

    # 1. Login Authentication
    if not action:
        host = request.host.split(":")[0]
        return jsonify({
            "user_info": {
                "auth": 1,
                "status": "Active",
                "username": username,
                "password": password,
                "message": "Welcome",
                "auth_date": 1600000000,
                "exp_date": "1988121600",
                "is_trial": "0",
                "active_cons": "0",
                "created_at": "1600000000",
                "max_connections": "100",
                "allowed_output_formats": ["m3u8", "ts", "mp4", "mkv"],
            },
            "server_info": {
                "url": host,
                "port": "80",
                "https_port": "443",
                "server_protocol": "http",
                "rtmp_port": "8880",
                "timezone": "UTC",
                "timestamp_now": 1600000000,
                "time_now": "2026-07-20 05:00:00",
            },
        })

    # 2. Category Endpoints
    if action == "get_live_categories":
        return jsonify([
            {"category_id": cid, "category_name": cname, "parent_id": 0}
            for cid, cname in CATEGORIES["live"].items()
        ])

    if action == "get_vod_categories":
        return jsonify([
            {"category_id": cid, "category_name": cname, "parent_id": 0}
            for cid, cname in CATEGORIES["vod"].items()
        ])

    if action == "get_series_categories":
        return jsonify([
            {"category_id": cid, "category_name": cname, "parent_id": 0}
            for cid, cname in CATEGORIES["series"].items()
        ])

    # 3. Stream & Series List Endpoints
    if action == "get_live_streams":
        return jsonify([
            {
                "num": idx + 1,
                "name": data["name"],
                "stream_type": "live",
                "stream_id": sid,
                "stream_icon": data["stream_icon"],
                "category_id": data["category_id"],
            }
            for idx, (sid, data) in enumerate(STREAMS["live"].items())
        ])

    if action == "get_vod_streams":
        return jsonify([
            {
                "num": idx + 1,
                "name": data["name"],
                "stream_type": "movie",
                "stream_id": sid,
                "stream_icon": data["stream_icon"],
                "category_id": data["category_id"],
                "container_extension": "m3u8",
            }
            for idx, (sid, data) in enumerate(STREAMS["vod"].items())
        ])

    if action == "get_series":
        return jsonify([
            {
                "num": idx + 1,
                "name": sdata["name"],
                "series_id": sid,
                "cover": sdata["cover"],
                "plot": "",
                "cast": "",
                "director": "",
                "genre": "",
                "releaseDate": "",
                "last_modified": "1600000000",
                "rating": "0",
                "rating_5based": 0,
                "category_id": sdata["category_id"],
            }
            for idx, (sid, sdata) in enumerate(SERIES_LIST.items())
        ])

    # 4. Detailed Series Info Endpoint (Seasons & Episodes Breakdown)
    if action == "get_series_info":
        series_id = request.args.get("series_id")
        if series_id in SERIES_LIST:
            sdata = SERIES_LIST[series_id]
            seasons_info = []

            for s_num, ep_list in sdata["seasons"].items():
                seasons_info.append({
                    "air_date": "",
                    "episode_count": len(ep_list),
                    "id": int(s_num),
                    "name": f"Season {s_num}",
                    "overview": "",
                    "poster_path": sdata["cover"],
                    "season_number": int(s_num)
                })

            return jsonify({
                "seasons": seasons_info,
                "episodes": sdata["seasons"],
                "info": {
                    "name": sdata["name"],
                    "cover": sdata["cover"],
                    "plot": "",
                    "genre": "",
                    "releaseDate": ""
                }
            })

    return jsonify([])


@app.route("/<stream_type>/<username>/<password>/<stream_id>")
def play_media(stream_type, username, password, stream_id):
    clean_id = re.sub(r"\D", "", stream_id.split(".")[0])

    # Direct Episode Redirect for Series
    if clean_id in EPISODE_MAP:
        target_url = EPISODE_MAP[clean_id]
        print(f"[*] Playing Episode ID {clean_id} -> {target_url}")
        return redirect(target_url, code=302)

    # Live or VOD Redirect
    type_map = {"live": "live", "movie": "vod"}
    stype = type_map.get(stream_type, "live")

    if stype in STREAMS and clean_id in STREAMS[stype]:
        target_url = STREAMS[stype][clean_id]["target_url"]
        print(f"[*] Playing [{stype}] Stream ID {clean_id} -> {target_url}")
        return redirect(target_url, code=302)

    return "Stream not found", 404


load_all_m3u_files()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
