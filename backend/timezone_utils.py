from importlib import resources
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_timezone(timezone_name: str) -> ZoneInfo:
    """Load an IANA timezone on platforms with or without a system tz database."""
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as original_error:
        try:
            zone_file = resources.files("tzdata").joinpath(
                "zoneinfo", *timezone_name.split("/")
            )
            with zone_file.open("rb") as file:
                return ZoneInfo.from_file(file, key=timezone_name)
        except (ModuleNotFoundError, FileNotFoundError, ValueError) as fallback_error:
            raise ZoneInfoNotFoundError(timezone_name) from fallback_error
