"""Command-line package manager for Minecraft datapacks. 

Usage:
  mcpkg update
  mcpkg install <packs>...
  mcpkg upgrade <packs>...
  mcpkg list [-ci] [--path=<path>]
  mcpkg search [-c] [--path=<path>] <pattern>...

  mcpkg -h | --help
  mcpkg --version | -V

Options:
  -h --help       Show this screen.
  -v --verbose    Increase verbosity.
  -V --version    Show the current version.
  -i --installed  Only list installed packages.
  -c --compact    Display output in compact, non coloured mode.
  --path=<path>   Specify the path to a world, or datapacks folder.
"""

from pathlib import Path
from typing import Any

from colorama import Fore
from docopt import docopt
from packaging import version
from pkg_resources import get_distribution

from mcpkg import config, syncdb, worldmanager, fileio
from mcpkg.constants import LogLevel, Pattern
from mcpkg.logger import log


__version__ = get_distribution("mcpkg").version
arguments = docopt(__doc__, version=f"mcpkg {__version__}")


def print_pack(pack: dict[str, Any], packname: str, compact: bool, colour: bool) -> None:
    """Print the name and description for the provided pack."""
    blue = green = ""
    if colour:
        blue, green = Fore.BLUE, Fore.GREEN

    version = pack.get("version")
    display_name = pack.get("display", "No display name available")
    description = pack.get("description", "No description available")

    print(f"{blue}{display_name}{Fore.RESET} ({green}{packname}{Fore.RESET}) v.{version}")
    if not compact:
        print(f"\t{description}")


def install(packs: list[str]):
    log("Getting pack metadata...", LogLevel.INFO)
    dl_url = syncdb.post_pack_dl_request(packs)
    log(f"Got '{dl_url}'", LogLevel.DEBUG)
    bytes = fileio.dl_with_progress(dl_url, "Downloading packs")
    pack_zips = fileio.separate_datapacks(bytes)
    for pack_zip in pack_zips:
        if not (match := Pattern.DATAPACK.match(pack_zip.stem)):
            log("Regex match failed", LogLevel.ERROR)
            raise SystemExit(-1)

        pack_id = syncdb.formalise_name(match.group("name"))
        pack_version = match.group("version")

        pack_from_sync = syncdb.get_pack_metadata(pack_id)
        if pack_from_sync:
            worldmanager.install_pack(pack_zip,
                                      Path.cwd(),
                                      pack_id,
                                      version=pack_version,
                                      display_name=pack_from_sync["display"],
                                      description=pack_from_sync["description"])
        else:
            worldmanager.install_pack(pack_zip,
                                      Path.cwd(),
                                      pack_id,
                                      version=pack_version)


def update():
    syncdb.fetch_pack_list()


def upgrade(packs: list[str]):
    pass


def list_packages(compact: bool, installed: bool, path: Path = Path.cwd()):
    if not (config.IS_TTY or compact):
        compact = True
        log("Pipe detected. Using compact layout", LogLevel.WARN)

    log("Listing packs:", LogLevel.INFO)
    pack_filter = None
    packlist = worldmanager.get_installed_packs(
        path) if installed else syncdb.get_local_pack_list(pack_filter)

    out_of_date = []
    for packname in packlist.keys():
        print_pack(packlist[packname], packname, compact, config.IS_TTY)
        if syncdb.get_pack_metadata(packname) and version.parse(syncdb.get_pack_metadata(packname)["version"]) > version.parse(packlist[packname]["version"]):
            out_of_date.append(packname)

    if len(out_of_date) != 0:
        for n in out_of_date:
            log(f"{Fore.GREEN}{n}{Fore.RESET} can be updated to {syncdb.get_pack_metadata(n)['version']}",
                LogLevel.WARN)


def search(expressions: list[str], compact: bool):
    log("Searching:", LogLevel.INFO)
    packlist = syncdb.get_local_pack_list(expressions)
    for packname in packlist.keys():
        print_pack(packlist[packname], packname, compact, config.IS_TTY)


def main() -> None:
    """Entry point for the command-line script."""
    config.verbose = arguments.get("--verbose", False)
    compact, installed = arguments["--compact"], arguments["--installed"]

    if arguments["install"]:
        install(arguments["<name>"])

    elif arguments["update"]:
        update()

    elif arguments["upgrade"]:
        upgrade()

    elif arguments["list"]:
        if path := arguments["--path"]:
            list_packages(compact, installed=True, path=path)
        else:
            list_packages(compact, installed=installed)

    elif arguments["search"]:
        search(arguments["<pattern>"], compact)