import argparse
from contextlib import closing
from pathlib import Path
from pprint import pprint

from radarrapi import (
    find_data_from_smb_nfo,
    get_custom_formats,
    get_movies_for_downloaded_quality,
    get_qualities,
    get_moviefile,
    set_quality,
    set_custom_formats,
)
from utils import humanbytes_storage, get_by_path

UNKNOWN_QUALITY = "Unknown"


def get_unknown_quality_movies():
    return get_movies_for_downloaded_quality(UNKNOWN_QUALITY)


def get_movie_data(
    smb_user: str, smb_password: str, smb_server_name: str, smb_server_ip: str,
):
    path_share_map = {
        "/tank1/Media": "Media",
        "/tank2/Media": "Media2",
        "/tank3/Media": "Media3",
        "/tank4/Media": "Media4",
    }

    for movie in get_unknown_quality_movies():
        nfo_lines = find_data_from_smb_nfo(
            movie,
            smb_user,
            smb_password,
            smb_server_name,
            smb_server_ip,
            path_share_map,
        )

        yield movie, nfo_lines


def update_key(window, key, value):
    key = f"__{key}__"
    window[key].update(value)


def update_window(
    window, movie, nfo_lines, index, movie_count, quality_names, custom_format_names
):
    def get_mediainfo(key, default=""):
        return get_by_path(movie, ["movieFile", "mediaInfo", key], default)

    update_key(window, "AUDIO_FMT", get_mediainfo("audioFormat"))
    update_key(window, "AUDIO_CHANNELS", get_mediainfo("audioChannels"))
    width = get_mediainfo("width", 0)
    height = get_mediainfo("height", 0)
    update_key(window, "VIDEO_DIMENSIONS", f"{width}x{height}")
    update_key(
        window, "VIDEO_BITRATE", f"{int(get_mediainfo('videoBitrate')/1024)} KB/s"
    )
    update_key(window, "VIDEO_CODEC_ID", get_mediainfo("videoCodecID"))
    update_key(window, "VIDEO_CODEC_LIBRARY", get_mediainfo("videoCodecLibrary"))
    update_key(window, "VIDEO_FMT", get_mediainfo("videoFormat"))
    update_key(window, "VIDEO_FPS", get_mediainfo("videoFps"))
    update_key(window, "VIDEO_PROFILE", get_mediainfo("videoProfile"))

    update_key(
        window, "FILE_CONTAINER", get_mediainfo("containerFormat"),
    )
    size = (
        humanbytes_storage(movie.get("sizeOnDisk"))
        if movie.get("sizeOnDisk")
        else "N/A"
    )
    update_key(window, "FILE_SIZE", size)

    movie_path = ""
    if movie.get("path") and get_by_path(movie, ["movieFile", "relativePath"]):
        movie_path = Path(movie["path"]) / get_by_path(
            movie, ["movieFile", "relativePath"]
        )

    update_key(window, "FILE_PATH", movie_path)
    update_key(window, "MOVIE_TITLE", movie["title"])
    update_key(window, "PROGRESS", f"{index+1}/{movie_count}")
    # Reset selection to movie's quality
    movie_quality = (
        get_by_path(movie, ["movieFile", "quality", "quality", "name"])
        or UNKNOWN_QUALITY
    )

    quality_select_index = quality_names.index("Bluray-1080p")
    format_select_index = custom_format_names.index("Complex Surround")

    window["__QUAL__"].update(set_to_index=quality_select_index)
    # Clear selection
    window["__FMT__"].update(set_to_index=format_select_index)

    window["__NFO_LINES__"].update(
        "\n".join(nfo_lines) if nfo_lines else "No .nfo to show."
    )


if __name__ == "__main__":
    import PySimpleGUI as sg

    parser = argparse.ArgumentParser(
        description="Update radarr file qualties for " "unknown quality files."
    )

    parser.add_argument("--smb-user", "-su", required=True, help="Username for SMB")
    parser.add_argument("--smb-pass", "-sp", required=True, help="Password for SMB")
    parser.add_argument(
        "--smb-server-name", "-sn", required=True, help="SMB server name."
    )
    parser.add_argument("--smb-server-ip", "-si", required=True, help="SMB server IP.")
    args = parser.parse_args()

    qualities = get_qualities()
    qualities_by_name = {q["quality"]["name"]: q["quality"] for q in qualities}
    custom_formats = get_custom_formats()
    # custom_formats_by_name = {cf["name"]: cf for cf in custom_formats}

    movies = list(
        get_movie_data(
            args.smb_user, args.smb_pass, args.smb_server_name, args.smb_server_ip
        )
    )

    idx = 0
    movie, nfo_lines = movies[idx]

    sg.theme("Default 1")

    def kv(label, key, size=(20, 1)):
        return sg.Text(f"{label}: "), sg.Text("", key=f"__{key}__", size=size)

    audio_frame = sg.Frame(
        "Audio", [[*kv("format", "AUDIO_FMT"), *kv("channels", "AUDIO_CHANNELS")]],
    )

    video_frame = sg.Frame(
        "Video",
        layout=[
            [
                *kv("dimensions", "VIDEO_DIMENSIONS"),
                *kv("bitrate", "VIDEO_BITRATE"),
                *kv("codec id", "VIDEO_CODEC_ID"),
            ],
            [
                *kv("codec library", "VIDEO_CODEC_LIBRARY", size=(20, 2)),
                *kv("format", "VIDEO_FMT"),
                *kv("fps", "VIDEO_FPS"),
            ],
            [*kv("profile", "VIDEO_PROFILE")],
        ],
    )

    file_frame = sg.Frame(
        "File",
        layout=[
            [*kv("container", "FILE_CONTAINER"), *kv("filesize", "FILE_SIZE"),],
            [*kv("path", "FILE_PATH", size=(125, 1))],
        ],
    )

    NO_CHANGE = "-No change-"
    quality_names = [NO_CHANGE] + [quality["title"] for quality in qualities]
    custom_format_names = [NO_CHANGE] + sorted(custom_formats.keys())
    layout = [
        [
            sg.Text("", text_color="Blue", key="__MOVIE_TITLE__", size=(60, 1)),
            sg.Text("", key="__PROGRESS__", size=(13, 1)),
        ],
        [sg.Text("Relevant lines from .nfo")],
        [
            sg.Multiline(
                default_text="No .nfo loaded.", key="__NFO_LINES__", size=(80, 3)
            )
        ],
        [audio_frame],
        [video_frame],
        [file_frame],
        [sg.Text("Quality")],
        [
            sg.Listbox(
                quality_names,
                size=(25, len(qualities) + 1),
                select_mode=sg.LISTBOX_SELECT_MODE_SINGLE,
                # default_values=[UNKNOWN_QUALITY],
                default_values=["Bluray-1080p"],
                key="__QUAL__",
            ),
            sg.Column(
                [
                    [sg.Text("Custom format")],
                    [sg.Text("(Multiple-select enabled)")],
                    [
                        sg.Listbox(
                            custom_format_names,
                            size=(25, len(custom_formats) + 1),
                            select_mode=sg.LISTBOX_SELECT_MODE_MULTIPLE,
                            enable_events=True,
                            key="__FMT__",
                            default_values=["Complex Surround"],
                        ),
                    ],
                ]
            ),
        ],
        [sg.Ok("Next")],
    ]
    print(custom_format_names)
    print(quality_names)
    with closing(sg.Window("Unknowns updater", layout)) as window:
        window.finalize()

        # populate window with initial values
        update_window(
            window,
            movie,
            nfo_lines,
            idx,
            len(movies),
            quality_names,
            custom_format_names,
        )

        while True:
            # get the quality data for currently-displayed movie
            current_quality_name = get_by_path(
                movie, ["movieFile", "quality", "quality", "name"]
            )
            current_formats_names = sorted(
                [
                    cf["name"]
                    for cf in get_by_path(
                        movie, ["movieFile", "quality", "customFormats"], default=[]
                    )
                ]
            )
            event, values = window.read()

            if event in (None, "Exit"):
                break

            if event == "Next":
                idx += 1

                # get the quality data selected in the GUI
                selected_quality_name = values.get("__QUAL__", [None])[0]
                selected_formats_names = sorted(values.get("__FMT__", []))

                # check if the quality of the movie doesn't equal the quality
                # selected in the GUI
                if (
                    selected_quality_name != current_quality_name
                    or selected_formats_names != current_formats_names
                ) and (
                    selected_quality_name != NO_CHANGE
                    and current_formats_names != [NO_CHANGE]
                ):
                    print("Getting moviefile")
                    # refresh the moviefile data from Radarr because I'm not sure if
                    # the  moviefile data we got from the "/movie" endpoint is the
                    # same format as the data we have to post to the "/moviefile"
                    # endpoint.
                    movie_file = get_moviefile(movie["movieFile"]["id"])

                    # ...and pull out the name of the quality.  We'll use the name to
                    # look up the actual quality data later.
                    refreshed_quality_name = get_by_path(
                        movie_file, ["quality", "quality", "name"]
                    )

                    # ...and pull out the list of custom format dicts.  Remember
                    # that there are multiple selectable custom formats per moviefile.
                    refreshed_custom_formats_names = sorted(
                        [
                            cf["name"]
                            for cf in get_by_path(
                                movie_file, ["quality", "customFormats"], default=[]
                            )
                        ]
                    )

                    # and again check if the selected quality matches the moviefile
                    # quality
                    updated_quality_data = None
                    updated_format_data = None
                    if (
                        selected_quality_name != refreshed_quality_name
                        and selected_quality_name != NO_CHANGE
                    ):
                        # GUI-selected quality does not match moviefile quality
                        updated_quality_data = qualities_by_name[selected_quality_name]
                    if (
                        selected_formats_names != refreshed_custom_formats_names
                        and selected_formats_names != [NO_CHANGE]
                    ):
                        # GUI-selected custom formats names does not match moviefile
                        # qualities
                        updated_format_data = [
                            custom_formats[name] for name in selected_formats_names
                        ]

                    if updated_quality_data:
                        print(
                            f"Updating quality on  {movie['title']} from"
                            f" {refreshed_quality_name} "
                            f"to {selected_quality_name}"
                        )
                        set_quality(updated_quality_data, movie_file)
                    if updated_format_data:
                        print(
                            f"Updating custom formats on {movie['title']} from "
                            f"{refreshed_custom_formats_names} to "
                            f"{selected_formats_names}"
                        )
                        set_custom_formats(updated_format_data, movie_file)

                movie, nfo_lines = movies[idx]
                update_window(
                    window,
                    movie,
                    nfo_lines,
                    idx,
                    len(movies),
                    quality_names,
                    custom_format_names,
                )
