import json
import re
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import requests
from colorama import Fore
from tqdm import tqdm

from . import config
from .constants import LogLevel
from .logger import log

VT_URL = "https://vanillatweaks.net/"
DP_URL = f"{VT_URL}assets/resources/json/{config.MC_BASE_VERSION}/dpcategories.json"
CT_URL = f"{VT_URL}assets/resources/json/{config.MC_BASE_VERSION}/ctcategories.json"
PACK_DB = config.CONFIG_DIR / "packdb.json"

pack_data = {}


def formalise_name(name: str):
    """
    Removes spaces from a name. Also adds a source identifier i.e. 'back to blocks' becomes 'vanillatweaks.backtoblocks'
    """
    return f"VanillaTweaks.{name.title().replace(' ', '')}"


def dl_with_progress(url: str, display: str) -> BytesIO:
    # Streaming, so we can iterate over the response.
    response = requests.get(url, stream=True)
    total_size_in_bytes = int(response.headers.get('content-length', 0))
    block_size = 1024  # 1 Kibibyte
    progress_bar = tqdm(total=total_size_in_bytes, unit="iB",
                        unit_scale=True, desc=display,
                        bar_format="{l_bar}%s{bar}%s{r_bar}" %
                        (Fore.BLUE, Fore.RESET),
                        ascii=True)
    buffer = BytesIO()
    for data in response.iter_content(block_size):
        progress_bar.update(len(data))
        buffer.write(data)
    buffer.seek(0)
    progress_bar.close()
    log(f"'{url}' saved to memory, status code {response.status_code}", LogLevel.DEBUG)
    if total_size_in_bytes != 0 and progress_bar.n != total_size_in_bytes:
        log("Printing the fancy progress bar caused an issue, it's probably okay to ignore this", LogLevel.WARN)
    return buffer


def vt_to_packdb(src: BytesIO, dst: Path) -> None:
    """
    Converts a vanilla tweaks JSON metadata file into a compatible list of packs.
    - src: The path to the vanilla tweaks metadata
    - dst: The path to the new pack list (usually ~/.config/mcpkg/packs.json)
    """
    global pack_data
    src_dict = json.load(src)
    new_dict = {}
    for src_category in src_dict["categories"]:
        for src_pack in src_category["packs"]:
            tags = [src_category["category"]]
            new_dict[formalise_name(src_pack["name"])] = {
                "remoteName": src_pack["name"],
                "display": src_pack["display"],
                "version": src_pack["version"],
                "description": src_pack["description"],
                "tags": tags
            }

    # Load any already stored values and union them
    if (dst.exists()):
        dst_dict = json.load(dst.open())
        new_dict = dst_dict | new_dict

    pack_data = new_dict
    json.dump(new_dict, dst.open("w"), indent=2, sort_keys=True)


def fetch_pack_list() -> None:
    """
    Fetches the pack list from Vanilla Tweaks servers and stores it in a compatible pack list
    """
    datapack_metadata = dl_with_progress(DP_URL,
                                         f"[{Fore.GREEN}INFO{Fore.RESET}] Downloading datapack metadata")
    vt_to_packdb(datapack_metadata, PACK_DB)
    tweak_metadata = dl_with_progress(CT_URL,
                                      f"[{Fore.GREEN}INFO{Fore.RESET}] Downloading crafting tweak metadata")
    vt_to_packdb(tweak_metadata, PACK_DB)
    log("Fetch complete", LogLevel.INFO)


def get_pack_metadata(pack_id: str) -> dict[str, Any]:
    """
    Gets the metadata of a given pack
    """
    packs = get_local_pack_list()
    if pack_id not in packs:
        log(f"The pack ID '{pack_id}' was not found in the sync database", LogLevel.ERROR)
        raise SystemExit(-1)
    return packs[pack_id]


def get_local_pack_list(pack_filter: list[dict[str, str]] = None) -> dict[str, dict[str, Any]]:
    """
    Gets the local pack list, filtered by the objects in `pack_filter`
    """
    global pack_data
    if not PACK_DB.exists():
        log("Can't find a locally stored packdb.json. Attempting to fetch now...", LogLevel.WARN)
        fetch_pack_list()

    if pack_data is not None:
        with PACK_DB.open() as file:
            packs = json.load(file)
        pack_data = packs
    else:
        packs = pack_data

    if pack_filter is not None:
        results = {}
        for search_term in pack_filter:
            expression = search_term["id"]
            for key in packs.keys():
                if re.search(expression, key, re.IGNORECASE):
                    results[key] = packs[key]
                    if "version" in search_term:
                        results[key]["version"] = search_term["version"]
    else:
        results = packs

    return results
