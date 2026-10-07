# Errors the services can raise. Views catch these and show a friendly message.


class AddressNotFound(Exception):
    """Nominatim couldn't find the address the user typed."""


class MapServiceBusy(Exception):
    """Every map data server failed or timed out. Try again in a minute."""
