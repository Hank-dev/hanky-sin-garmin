"""Garmin Connect authentication.

Uses the unofficial `garminconnect` library (which authenticates via `garth`).
First run logs in with email/password and caches OAuth tokens in
GARMIN_TOKENSTORE. Subsequent runs (including headless cron jobs) resume from
those tokens and never need the password or MFA again until they expire
(the long-lived token lasts ~1 year).

NOTE: this is the unofficial route. It works against Garmin Connect's internal
API and violates Garmin's ToS in the strict sense; in practice personal-use
sync is common and rarely actioned. Your password lives in .env / the token
cache, so keep that machine private.
"""
import os
from garminconnect import Garmin
import config


def _prompt_mfa() -> str:
    return input("Garmin MFA code (check email/SMS/app): ").strip()


def get_client(interactive: bool = False) -> Garmin:
    """Return an authenticated Garmin client.

    interactive=True allows password login + MFA prompt (use for the first
    `python sync.py --login`). interactive=False only resumes cached tokens
    and is what cron should use.
    """
    tokenstore = config.GARMIN_TOKENSTORE

    # Try to resume from cached tokens first.
    if os.path.isdir(tokenstore) and os.listdir(tokenstore):
        try:
            client = Garmin()
            client.login(tokenstore)
            return client
        except Exception as e:
            if not interactive:
                raise RuntimeError(
                    f"Cached Garmin tokens invalid/expired ({e}). "
                    f"Re-run `python sync.py --login` interactively."
                )

    if not interactive:
        raise RuntimeError(
            "No Garmin tokens cached. Run `python sync.py --login` once "
            "interactively to authenticate."
        )

    if not config.GARMIN_EMAIL or not config.GARMIN_PASSWORD:
        raise RuntimeError("Set GARMIN_EMAIL and GARMIN_PASSWORD in .env for first login.")

    client = Garmin(
        email=config.GARMIN_EMAIL,
        password=config.GARMIN_PASSWORD,
        is_cn=config.GARMIN_IS_CN,
        prompt_mfa=_prompt_mfa,
    )
    client.login()
    os.makedirs(tokenstore, exist_ok=True)
    # garminconnect 0.3.x renamed the token sub-client: the old `.garth`
    # attribute is gone; tokens are persisted via the underlying `.client`.
    client.client.dump(tokenstore)
    print(f"Tokens cached to {tokenstore}. Future syncs run headless.")
    return client
