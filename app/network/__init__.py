"""Windows network probing: adapters, ICMP, DNS, routes, Wi-Fi.

Every module in this package is GUI free and can be unit tested without a live
internet connection; subprocess and socket access is isolated in small,
injectable functions.
"""

from __future__ import annotations
