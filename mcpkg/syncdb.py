import json
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import requests
from colorama import Fore

from . import config, fileio
from .pack import Pack, PackSet, encode_packset, decode_packset
from .constants import LogLevel, PackType
from .logger import log

VT_URL = "https://vanillatweaks.net"
DP_URL = f"{VT_URL}/assets/resources/json/{config.MC_BASE_VERSION}/dpcategories.json"
CT_URL = f"{VT_URL}/assets/resources/json/{config.MC_BASE_VERSION}/ctcategories.json"
RP_URL = f"{VT_URL}/assets/resources/json/{config.MC_BASE_VERSION}/rpcategories.json"
PACK_DB = config.CONFIG_DIR / "packdb.json"

pack_data: Optional[PackSet] = None


def make_post(url: str, request: "dict[str, str]") -> str:
    # Prep the request (allows for more verbose debug output)
    prep_request = requests.Request('POST',
                                    url,
                                    data=request).prepare()
    log(f"Sending request: '{prep_request.body}'' to '{url}'", LogLevel.DEBUG)
    log(f"Request payload: {request}", LogLevel.DEBUG)

    s = requests.Session()
    res = s.send(prep_request)

    response_message = json.loads(res.text)
    if response_message["status"] == "error":
        log(f"""Couldn't get packs!
\tResponse from {url}: {response_message['message']}
\tFor more details, it's recommended to turn on verbose mode with either the --verbose flag or setting mcpkg.config.verbose = True""",
            LogLevel.ERROR)
        raise SystemExit(-1)

    return f"{VT_URL}{response_message['link']}"


def post_pack_dl_request(packs: PackSet, pack_type: PackType) -> str:
    """
    Makes a POST request to the Vanilla Tweaks server.
    Returns a URL that should be used to download the packs
    Request structure:
    ```
      packs: {
          "category_name": [
              "remote_name_a",
              "remote_name_b"
          ]
      },
      version: 1.16
    ```
    """
    pack_request = {}

    for pack in packs:
        assert pack.pack_type == pack_type
        if pack.category not in pack_request:
            pack_request[pack.category] = []
        pack_request[pack.category].append(pack.remote_name)

    # Make the POST request to get the packs download link
    url = f"{VT_URL}/assets/server/zip{pack_type}s.php"
    request_data = {
        "packs": json.dumps(pack_request),
        "version": "1.16"
    }
    return make_post(url, request_data)


def vt_to_packdb(src: BytesIO, dst: Path, pack_type: PackType) -> None:
    """
    Converts a vanilla tweaks JSON metadata file into a compatible list of packs.
    - src: The path to the vanilla tweaks metadata
    - dst: The path to the new pack list (usually ~/.config/mcpkg/packs.json)
    """
    global pack_data
    src_dict: "dict[str, Any]" = json.load(src)
    pack_set = PackSet()
    for src_category in src_dict["categories"]:
        category_name = src_category["category"]
        for src_pack in src_category["packs"]:
            tags = [src_category["category"]]
            version = src_pack.get("version")
            if not version:
                version = "0.0.0"
            pack_to_add = Pack(
                src_pack["name"],
                src_pack["display"],
                pack_type,
                category_name,
                version,
                src_pack["description"],
                tags
            )
            pack_set[pack_to_add.id] = pack_to_add

    # Load any already stored values and union them
    if (dst.exists()):
        with open(dst) as fp:
            existing_packset = decode_packset(fp)
        pack_set.union(existing_packset)

    pack_data = pack_set
    with dst.open("w") as fp:
        encode_packset(pack_set, fp)


def fetch_pack_list() -> None:
    """
    Fetches the pack list from Vanilla Tweaks servers and stores it in a compatible pack list
    """
    # Get Datapacks
    datapack_metadata = fileio.dl_with_progress(DP_URL,
                                                f"[{Fore.GREEN}INFO{Fore.RESET}] Downloading datapack metadata")
    vt_to_packdb(datapack_metadata, PACK_DB, PackType.DATA)

    # Get Crafting tweaks
    tweak_metadata = fileio.dl_with_progress(CT_URL,
                                             f"[{Fore.GREEN}INFO{Fore.RESET}] Downloading crafting tweak metadata")
    vt_to_packdb(tweak_metadata, PACK_DB, PackType.CRAFTING)

    # Get Resource Packs
    resource_metadata = fileio.dl_with_progress(RP_URL,
                                                f"[{Fore.GREEN}]INFO[{Fore.RESET}] Downloading resource pack metadata")
    vt_to_packdb(resource_metadata, PACK_DB, PackType.RESOURCE)

    log("Fetch complete", LogLevel.INFO)


def get_pack_metadata(pack_id: str) -> Optional[Pack]:
    """
    Gets the metadata of a given pack.

    `pack_id` can be either the formal id or the remote name
    """
    local_list = get_local_pack_list()

    pack = local_list.get(pack_id)
    if pack:
        return pack

    for pack in local_list:
        if pack.remote_name == pack_id:
            return pack

    return None


def get_local_pack_list() -> PackSet:
    """
    Gets the local pack list, filtered by the strings in `pack_filter`
    - `pack_filter` A list of pack IDs
    """
    global pack_data
    if not PACK_DB.exists():
        log("Can't find a locally stored packdb.json. Attempting to fetch now...", LogLevel.WARN)
        fetch_pack_list()

    # This is crude caching and is probs a bad idea lol
    if not pack_data:
        with PACK_DB.open() as file:
            packs = decode_packset(file)
        pack_data = packs
    else:
        packs = pack_data

    return packs
