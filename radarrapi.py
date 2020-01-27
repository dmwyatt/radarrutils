import io
import os
import platform
import re
import socket
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pprint import pprint
from time import sleep
from typing import (
    Any,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Pattern,
    Sequence,
    TypedDict,
    Union,
)

import requests
from dateutil import parser

from utils import get_by_path

API_KEY = "API KEY HERE"
BASE_QUERY = {"apikey": API_KEY}

BASE_URL = f"https://raneus.thewyattshouse.com:32913/api"
PROFILE_PATH = "/profile"
MOVIE_PATH = "/movie"
COMMAND_PATH = "/command"
QUALITY_PATH = "/qualitydefinition"
CUSTOM_FORMAT_PATH = "/customformat"
MOVIEFILE_PATH = "/moviefile"

client_machine_name = None


class QualityType(TypedDict):
    id: int
    modifier: str
    name: str
    resolution: str
    source: str


class CustomFormatTagValue(TypedDict):
    pattern: str
    options: str


class CustomFormatTag(TypedDict):
    raw: str
    tagType: str
    tagModifier: str
    value: CustomFormatTagValue


class CustomFormat(TypedDict):
    name: str
    formatTags: List[CustomFormatTag]
    id: int


def set_quality(quality_data: QualityType, movie_file: Mapping[str, Any]):
    if sorted(quality_data.keys()) == [
        "id",
        "maxSize",
        "minSize",
        "quality",
        "title",
        "weight",
    ]:
        quality_data = quality_data["quality"]
    assert sorted(quality_data.keys()) == [
        "id",
        "modifier",
        "name",
        "resolution",
        "source",
    ]
    movie_file["quality"]["quality"] = quality_data

    return update_moviefile(movie_file)


def add_custom_format(cf_id: CustomFormat, movie_file: Mapping[str, Any]):
    """Add a custom format to moviefile's existing custom formats"""
    movie_file["quality"]["customFormats"].append(cf_id)

    return update_moviefile(movie_file)


def set_custom_formats(
    custom_formats: Sequence[CustomFormat], movie_file: Mapping[str, Any]
):
    """Replace moviefile's custom formats with the provided custom formats"""
    movie_file["quality"]["customFormats"] = list(custom_formats)

    return update_moviefile(movie_file)


def _get(path: str):
    return requests.get(BASE_URL + path, params=BASE_QUERY)


def _put(path: str, data: Any):
    return requests.put(BASE_URL + path, params=BASE_QUERY, json=data)


def get_moviefile(id_: int):
    return _get(f"{MOVIEFILE_PATH}/{id_}").json()


def get_moviefiles():
    return _get(MOVIEFILE_PATH).json()


def set_profile(movie: MutableMapping[str, Any], profile_id: int):
    movie["profileId"] = profile_id
    movie["qualityProfileId"] = profile_id
    return update_movie(movie)


def update_moviefile(data: Mapping[str, Any]):
    return _put(MOVIEFILE_PATH, data).json()


def update_movie(data: Mapping[str, Any]):
    return _put(MOVIE_PATH, data).json()


def get_qualities():
    return _get(QUALITY_PATH).json()


def get_quality_by_name(name: str):
    for qual in get_qualities():
        if qual["title"] == name:
            return qual


def get_custom_formats():
    api_fmts = _get(CUSTOM_FORMAT_PATH).json()
    # Radarr is messed up.  See https://github.com/Radarr/Radarr/issues/4049
    custom_fmt_names = sorted([f["name"] for f in api_fmts])

    found_api_fmts = {}

    found_all_fmts = False
    for movie in get_movies():
        for cf in get_by_path(
            movie, ["movieFile", "quality", "customFormats"], default=[]
        ):
            if cf["name"] not in found_api_fmts:
                found_api_fmts[cf["name"]] = cf

        #     if sorted(found_api_fmts.keys()) == custom_fmt_names:
        #         found_all_fmts = True
        #         break
        #
        # if found_all_fmts:
        #     break

    if sorted(found_api_fmts.keys()) != custom_fmt_names:
        print("Couldn't find all custom formats from movie files.")

    return found_api_fmts


def get_profiles():
    return _get(PROFILE_PATH).json()


def get_movies():
    return _get(MOVIE_PATH).json()


def get_movie_by_title(title: str, exact=False, case_sensitive=False):
    def does_match(movie):
        if exact and case_sensitive:
            return movie["title"] == title
        elif exact and not case_sensitive:
            return movie["title"].casefold() == title.casefold()
        elif not exact and case_sensitive:
            return title in movie["title"]
        elif not exact and not case_sensitive:
            return title.casefold() in movie["title"].casefold()

    matches = []
    for movie in get_movies():
        if does_match(movie):
            matches.append(movie)

    if len(matches) > 1:
        raise ValueError(f'Too many movies match "{title}"')
    if len(matches) == 0:
        return
    return matches[0]


def get_profile_by_name(name: str, profiles: Optional[Sequence[Any]] = None):
    profiles = get_profiles() if not profiles else profiles
    for profile in profiles:
        if profile["name"] == name:
            return profile


def get_movies_for_profile(profile_id: int):
    movies = get_movies()
    for movie in movies:
        if movie.get("qualityProfileId") == profile_id:
            yield movie


def get_movies_for_downloaded_quality(quality_name: str):
    for movie in get_movies():
        name = (
            movie.get("movieFile", {})
            .get("quality", {})
            .get("quality", {})
            .get("name", None)
        )
        if name and name.casefold() == quality_name.casefold():
            yield movie


def force_search_for_existing_movies(movie_ids: Sequence[int]):
    response = requests.post(
        BASE_URL + COMMAND_PATH,
        json={"name": "moviesSearch", "movieIds": list(movie_ids)},
        params=BASE_QUERY,
    )

    return response.json()


def get_commands_status():
    return _get(COMMAND_PATH).json()


def get_command_status(command_id: int):
    statuses = get_commands_status()
    for status in statuses:
        if status["id"] == command_id:
            return status


def find_data_from_smb_nfo(
    movie: Mapping[str, Any],
    smb_user: str,
    smb_password: str,
    smb_server_name: str,
    smb_server_ip: str,
    path_share_map: Mapping[str, str],
    workgroup: str = "",
    matchers: Sequence[Union[str, Pattern]] = None,
) -> List[str]:
    from smb.SMBConnection import SMBConnection

    if matchers is None:
        matchers = ["bluray"]

    global client_machine_name
    if client_machine_name is None:
        client_machine_name = (
            os.environ.get("COMPUTERNAME") or platform.node() or socket.gethostname()
        )
        assert client_machine_name, "Cannot determine host name."

    def _connect():
        conn = SMBConnection(
            smb_user,
            smb_password,
            client_machine_name,
            smb_server_name,
            domain=workgroup,
            use_ntlm_v2=True,
            is_direct_tcp=True,
        )
        conn.connect(smb_server_ip, 445)
        return conn

    with closing(_connect()) as conn:
        # verify movie path is something we know how to handle
        found = False
        movie_path_prefix = None
        for path_prefix in path_share_map:
            if movie["folderName"].startswith(path_prefix):
                movie_path_prefix = path_prefix
                found = True
                break

        assert found, f'Unknown path: {movie["folderName"]}'

        movie_share = path_share_map[movie_path_prefix]
        movie_path = movie["folderName"].replace(movie_path_prefix, "")

        files = conn.listPath(movie_share, movie_path, pattern="*.nfo")

        matching_lines = []

        if files:
            assert len(files) == 1

            # get contents of nfo
            f = io.BytesIO()
            conn.retrieveFile(movie_share, movie_path + "/" + files[0].filename, f)
            f.seek(0)
            nfo_contents = f.read().decode("latin1")

            found = False
            for line in nfo_contents.splitlines():
                for matcher in matchers:
                    if isinstance(matcher, str):
                        matcher = re.compile(matcher, flags=re.IGNORECASE)

                if matcher.match(line):
                    matching_lines.append(line)

        return matching_lines


def update_audio():
    count = 0
    custom_formats = get_custom_formats()
    needs_updating = []
    for movie in get_movies():
        if not movie.get("movieFile"):
            continue
        count += 1
        audio_format = get_by_path(movie, ["movieFile", "mediaInfo", "audioFormat"])
        audio_channels = get_by_path(movie, ["movieFile", "mediaInfo", "audioChannels"])
        cf = None
        if audio_channels >= 6:
            cf_names = [
                cf["name"]
                for cf in get_by_path(movie, ["movieFile", "quality", "customFormats"])
            ]
            if "Complex Surround" not in cf_names:
                needs_updating.append(movie)
    count = 0
    for movie in needs_updating:
        count += 1
        audio_format = get_by_path(movie, ["movieFile", "mediaInfo", "audioFormat"])
        audio_channels = get_by_path(movie, ["movieFile", "mediaInfo", "audioChannels"])
        print(f"Adding Complex Surround to {count}/{len(needs_updating)}: ")
        print(movie["title"], audio_format, audio_channels)
        moviefile = get_moviefile(get_by_path(movie, ["movieFile", "id"]))
        assert moviefile
        add_custom_format(custom_formats["Complex Surround"], moviefile)


def fixit():
    recent = []
    today = datetime.now(timezone.utc) - timedelta(hours=3)
    more_audio_profile = get_profile_by_name("most (audio)")
    assert more_audio_profile
    import_more_audio_profile = get_profile_by_name("import-most-audio")
    assert import_more_audio_profile
    for movie in get_movies():
        added = parser.parse(movie["added"])
        if added > today and movie["profileId"] == more_audio_profile["id"]:
            set_profile(movie, import_more_audio_profile["id"])
            recent.append(movie)

    pprint([m["title"] for m in recent])


def update_unk_blu_complex():
    updates = []
    for movie in get_movies_for_downloaded_quality("Unknown"):
        width = get_by_path(movie, ["movieFile", "mediaInfo", "width"], 0)
        channels = get_by_path(movie, ["movieFile", "mediaInfo", "audioChannels"], 0)
        if 1900 <= width <= 1920 and channels > 3:
            updates.append(movie)

    if updates:
        blu_qual = get_quality_by_name("Bluray-1080p")
        custom_formats = [get_custom_formats()["Complex Surround"]]
        assert blu_qual
        for movie in updates:
            print(movie["title"])
            moviefile = movie.get("movieFile")
            assert moviefile
            moviefile = get_moviefile(moviefile["id"])
            assert moviefile

            set_quality(blu_qual, moviefile)
            set_custom_formats(custom_formats, moviefile)
    print(len(updates))


if __name__ == "__main__":
    # update_unk_blu_complex()
    # pprint(get_custom_formats())
    # exit()
    profile_map = {
        "import-most-audio": "most (audio)",
        "import-most-space": "most (space)",
        "import-1080-ok": "1080p's ok",
        "import-highest": "highest",
    }

    profiles_by_id = {p["id"]: p for p in get_profiles()}
    profile_names = [p["name"] for p in profiles_by_id.values()]
    assert all([n in profile_names for n in profile_map.keys()])
    assert all([n in profile_names for n in profile_map.values()])

    profile_id_map = {}

    for source_name, dest_name in profile_map.items():
        source_id = None
        dest_id = None
        for profile in profiles_by_id.values():
            if profile["name"] == source_name:
                source_id = profile["id"]
                continue
            if profile["name"] == dest_name:
                dest_id = profile["id"]
        assert source_id and dest_id
        profile_id_map[source_id] = dest_id

    start_at_index = 0
    movies = list(get_movies())
    end_at_index = len(movies)
    movies_to_search = []
    for idx, movie in enumerate(movies):
        if idx == end_at_index:
            break
        if idx < start_at_index:
            continue
        print(
            f"Checking movie {movie['title']} ({idx-start_at_index}"
            f"/{end_at_index - start_at_index})"
        )

        profile_name = profiles_by_id[movie["profileId"]]["name"]

        if profile_name.startswith("import-"):
            # if profile_name.startswith(""):
            movies_to_search.append(movie)

    for idx, movie in enumerate(movies_to_search):
        print(f"Movie {idx+1} of {len(movies_to_search)}")
        print("Searching for ", movie["title"], "...", end="")
        data = force_search_for_existing_movies([movie["id"]])

        # status checking
        while get_command_status(data["id"]) or "complete" != "complete":
            sleep(1)
            print(".", end="")

        print("\n")

        new_profile_id = profile_id_map[movie["profileId"]]
        print(
            f'Updating profile from {profiles_by_id[movie["profileId"]]["name"]} to '
            f"{profiles_by_id[new_profile_id]['name']}"
        )
        set_profile(movie, new_profile_id)

    print("\ndone")
